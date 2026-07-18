"""Attach final WNBA scores to the compact Odds API SQLite warehouse.

Odds API and ESPN game ids differ, so results are matched using normalized teams
and the game date. A one-day date tolerance is allowed because Odds API stores
UTC dates while ESPN's current-season feed uses the local game date.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("data/warehouse/wnba_odds_history.sqlite")
RAW_DIR = Path("data/raw")
WAREHOUSE_OUT = Path("data/warehouse/wnba_odds_history_results.json")
DASHBOARD_OUT = Path("data/dashboard/wnba_odds_history_results.json")

ALIASES = {
    "dream": "atlanta dream", "atlanta": "atlanta dream",
    "sky": "chicago sky", "chicago": "chicago sky",
    "sun": "connecticut sun", "connecticut": "connecticut sun",
    "wings": "dallas wings", "dallas": "dallas wings",
    "fever": "indiana fever", "indiana": "indiana fever",
    "aces": "las vegas aces", "las vegas": "las vegas aces",
    "sparks": "los angeles sparks", "la sparks": "los angeles sparks",
    "los angeles": "los angeles sparks",
    "lynx": "minnesota lynx", "minnesota": "minnesota lynx",
    "liberty": "new york liberty", "ny liberty": "new york liberty",
    "new york": "new york liberty",
    "mercury": "phoenix mercury", "phoenix": "phoenix mercury",
    "storm": "seattle storm", "seattle": "seattle storm",
    "mystics": "washington mystics", "washington": "washington mystics",
    "valkyries": "golden state valkyries", "golden state": "golden state valkyries",
    "tempo": "toronto tempo", "toronto": "toronto tempo",
    "fire": "portland fire", "portland": "portland fire",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def norm_team(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return ALIASES.get(text, text)


def team_value(row: dict[str, str]) -> str:
    name = str(row.get("team_name") or "").strip()
    location = str(row.get("team_location") or "").strip()
    abbreviation = str(row.get("team_abbreviation") or row.get("team_abbr") or "").strip()
    if location and name:
        combined = f"{location} {name}".strip()
        if norm_team(combined) != combined.lower() or norm_team(name) == name.lower():
            return combined
    return name or location or abbreviation


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


def nearby_dates(value: str) -> list[str]:
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return [value[:10]]
    return [(parsed + timedelta(days=offset)).isoformat() for offset in (0, -1, 1)]


def build_result(source_game_id: str, game_date: str, home: dict[str, str], away: dict[str, str], source: str) -> dict[str, Any] | None:
    home_score, away_score = score_value(home), score_value(away)
    home_team, away_team = team_value(home), team_value(away)
    if home_score is None or away_score is None or not game_date or not home_team or not away_team:
        return None
    return {
        "source_game_id": source_game_id,
        "game_date": game_date,
        "home_team": home_team,
        "away_team": away_team,
        "home_team_key": norm_team(home_team),
        "away_team_key": norm_team(away_team),
        "home_score": home_score,
        "away_score": away_score,
        "source": source,
    }


def load_boxscore_results(raw_dir: Path) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for path in sorted(raw_dir.glob("wehoop_team_box_*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                game_id = str(row.get("game_id") or "").strip()
                if game_id:
                    grouped[game_id].append(row)

    results: list[dict[str, Any]] = []
    for source_game_id, rows in grouped.items():
        game_date = next((date_value(r) for r in rows if date_value(r)), "")
        home = next((r for r in rows if str(r.get("home_away") or "").lower() == "home"), None)
        away = next((r for r in rows if str(r.get("home_away") or "").lower() == "away"), None)
        if home and away:
            result = build_result(source_game_id, game_date, home, away, "wehoop_or_espn_team_box")
            if result:
                results.append(result)
            continue

        # ESPN current-season boxscore team rows can omit homeAway. Preserve both
        # orientations; the exact warehouse matchup determines the correct one.
        scored = [r for r in rows if score_value(r) is not None and team_value(r)]
        if len(scored) == 2:
            first = build_result(source_game_id, game_date, scored[0], scored[1], "espn_team_box_inferred")
            second = build_result(source_game_id, game_date, scored[1], scored[0], "espn_team_box_inferred")
            if first:
                results.append(first)
            if second:
                results.append(second)
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

    matched, unmatched, ambiguous = [], [], []
    query = "SELECT game_id,game_date_utc,home_team,away_team,completed FROM games ORDER BY commence_time_utc"
    for game in con.execute(query):
        home_key, away_key = norm_team(game["home_team"]), norm_team(game["away_team"])
        candidates_by_id: dict[str, dict[str, Any]] = {}
        for candidate_date in nearby_dates(str(game["game_date_utc"])):
            for candidate in index.get((candidate_date, home_key, away_key), []):
                candidates_by_id[candidate["source_game_id"]] = candidate
        candidates = list(candidates_by_id.values())
        if len(candidates) == 1:
            result = candidates[0]
            con.execute(
                "UPDATE games SET completed=1,home_score=?,away_score=?,updated_at_utc=? WHERE game_id=?",
                (result["home_score"], result["away_score"], now_utc(), game["game_id"]),
            )
            matched.append({
                "game_id": game["game_id"], "game_date": game["game_date_utc"],
                "away_team": game["away_team"], "home_team": game["home_team"],
                "away_score": result["away_score"], "home_score": result["home_score"],
                "source_game_id": result["source_game_id"], "source": result["source"],
                "source_game_date": result["game_date"],
            })
        elif len(candidates) > 1:
            ambiguous.append({"game_id": game["game_id"], "candidate_count": len(candidates)})
        elif not game["completed"]:
            unmatched.append({"game_id": game["game_id"], "game_date": game["game_date_utc"],
                              "away_team": game["away_team"], "home_team": game["home_team"]})
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    completed = con.execute(
        "SELECT COUNT(*) FROM games WHERE completed=1 AND home_score IS NOT NULL AND away_score IS NOT NULL"
    ).fetchone()[0]
    payload = {
        "generated_at_utc": now_utc(), "database": str(db_path), "status": "ok",
        "summary": {
            "warehouse_games": total, "games_with_results": completed,
            "games_without_results": total - completed, "matched_this_run": len(matched),
            "unmatched_this_run": len(unmatched), "ambiguous_this_run": len(ambiguous),
            "source_result_games": len({row["source_game_id"] for row in source_rows}),
            "source_result_orientations": len(source_rows),
            "result_coverage_pct": round(completed * 100 / total, 2) if total else 0.0,
        },
        "matched": matched, "unmatched": unmatched, "ambiguous": ambiguous,
        "matching_policy": "normalized teams + game date with UTC/local +/-1 day tolerance",
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
