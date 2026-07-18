"""Attach final WNBA scores to the compact Odds API SQLite warehouse.

The importer reads Sportsdataverse/wehoop team-box CSVs already used by the
project. Odds API and ESPN game ids are different, so games are matched by UTC
calendar date plus normalized home/away team names. No Odds API credits are used.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("data/warehouse/wnba_odds_history.sqlite")
RAW_DIR = Path("data/raw")
WAREHOUSE_OUT = Path("data/warehouse/wnba_odds_history_results.json")
DASHBOARD_OUT = Path("data/dashboard/wnba_odds_history_results.json")

ALIASES = {
    "la sparks": "los angeles sparks",
    "los angeles": "los angeles sparks",
    "ny liberty": "new york liberty",
    "new york": "new york liberty",
    "washington": "washington mystics",
    "connecticut": "connecticut sun",
    "indiana": "indiana fever",
    "chicago": "chicago sky",
    "atlanta": "atlanta dream",
    "seattle": "seattle storm",
    "phoenix": "phoenix mercury",
    "minnesota": "minnesota lynx",
    "dallas": "dallas wings",
    "las vegas": "las vegas aces",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def norm_team(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return ALIASES.get(text, text)


def score_value(row: dict[str, str]) -> int | None:
    for key in ("points", "pts", "score", "team_score"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                return int(round(float(value)))
            except (TypeError, ValueError):
                pass
    return None


def date_value(row: dict[str, str]) -> str:
    for key in ("game_date", "date", "game_date_time", "start_time"):
        value = str(row.get(key) or "").strip()
        if value:
            return value[:10]
    return ""


def load_boxscore_results(raw_dir: Path) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    files = sorted(raw_dir.glob("wehoop_team_box_*.csv"))
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                game_id = str(row.get("game_id") or "").strip()
                if game_id:
                    grouped[game_id].append(row)

    results: list[dict[str, Any]] = []
    for source_game_id, rows in grouped.items():
        home = next((r for r in rows if str(r.get("home_away") or "").lower() == "home"), None)
        away = next((r for r in rows if str(r.get("home_away") or "").lower() == "away"), None)
        if not home or not away:
            continue
        home_score, away_score = score_value(home), score_value(away)
        if home_score is None or away_score is None:
            continue
        home_team = home.get("team_name") or home.get("team_location") or home.get("team_abbreviation")
        away_team = away.get("team_name") or away.get("team_location") or away.get("team_abbreviation")
        game_date = date_value(home) or date_value(away)
        if not game_date or not home_team or not away_team:
            continue
        results.append({
            "source_game_id": source_game_id,
            "game_date": game_date,
            "home_team": str(home_team),
            "away_team": str(away_team),
            "home_team_key": norm_team(home_team),
            "away_team_key": norm_team(away_team),
            "home_score": home_score,
            "away_score": away_score,
            "overtime": False,
            "source": "sportsdataverse_wehoop_team_box",
        })
    return results


def attach(db_path: Path, raw_dir: Path) -> dict[str, Any]:
    if not db_path.exists():
        raise SystemExit(f"Odds warehouse not found: {db_path}")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    source_rows = load_boxscore_results(raw_dir)
    index: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        index[(row["game_date"], row["home_team_key"], row["away_team_key"])].append(row)

    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for game in con.execute("SELECT game_id,game_date_utc,home_team,away_team,completed FROM games ORDER BY commence_time_utc"):
        key = (str(game["game_date_utc"]), norm_team(game["home_team"]), norm_team(game["away_team"]))
        candidates = index.get(key, [])
        if len(candidates) == 1:
            result = candidates[0]
            con.execute(
                """UPDATE games SET completed=1,home_score=?,away_score=?,updated_at_utc=? WHERE game_id=?""",
                (result["home_score"], result["away_score"], now_utc(), game["game_id"]),
            )
            matched.append({
                "game_id": game["game_id"], "game_date": game["game_date_utc"],
                "away_team": game["away_team"], "home_team": game["home_team"],
                "away_score": result["away_score"], "home_score": result["home_score"],
                "source_game_id": result["source_game_id"], "source": result["source"],
            })
        elif len(candidates) > 1:
            ambiguous.append({"game_id": game["game_id"], "key": key, "candidate_count": len(candidates)})
        elif not game["completed"]:
            unmatched.append({"game_id": game["game_id"], "game_date": game["game_date_utc"],
                              "away_team": game["away_team"], "home_team": game["home_team"]})
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    completed = con.execute("SELECT COUNT(*) FROM games WHERE completed=1 AND home_score IS NOT NULL AND away_score IS NOT NULL").fetchone()[0]
    payload = {
        "generated_at_utc": now_utc(), "database": str(db_path), "status": "ok",
        "summary": {
            "warehouse_games": total, "games_with_results": completed,
            "games_without_results": total - completed, "matched_this_run": len(matched),
            "unmatched_this_run": len(unmatched), "ambiguous_this_run": len(ambiguous),
            "source_result_games": len(source_rows),
            "result_coverage_pct": round(completed * 100 / total, 2) if total else 0.0,
        },
        "matched": matched, "unmatched": unmatched, "ambiguous": ambiguous,
        "matching_policy": "exact normalized game_date + home_team + away_team",
    }
    for path in (WAREHOUSE_OUT, DASHBOARD_OUT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()
    attach(args.db, args.raw_dir)


if __name__ == "__main__":
    main()
