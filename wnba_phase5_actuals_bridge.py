"""Build the legacy Phase 5 boxscore input from current canonical player-result sources.

Phase 5 originally read only data/raw/boxscores_wehoop.csv. The live-results stack now
stores cumulative player game logs in JSON and may emit dated CSV files. This bridge
normalizes those sources into the stable CSV contract expected by the learning engine.
"""
from __future__ import annotations

import csv
import glob
import json
import math
from pathlib import Path
from typing import Any

OUT = Path("data/raw/boxscores_wehoop.csv")
CANONICAL = Path("data/warehouse/wnba_player_game_logs.json")
FIELDS = ["game_date", "player", "team", "opponent", "opponent_abbr", "pts", "reb", "ast", "threes", "stl", "blk", "tov"]


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def first(row: dict[str, Any], *names: str) -> Any:
    lower = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        value = lower.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def flatten_canonical(row: dict[str, Any]) -> dict[str, Any] | None:
    player = str(row.get("player") or "").strip()
    game_date = str(row.get("game_date") or "")[:10]
    if not player or not game_date:
        return None
    scoring = row.get("scoring") if isinstance(row.get("scoring"), dict) else {}
    box = row.get("boxscore") if isinstance(row.get("boxscore"), dict) else {}
    return {
        "game_date": game_date,
        "player": player,
        "team": row.get("team"),
        "opponent": row.get("opponent"),
        "opponent_abbr": row.get("opponent_abbr"),
        "pts": scoring.get("total_pts"),
        "reb": box.get("reb"),
        "ast": box.get("ast"),
        "threes": scoring.get("three_pm"),
        "stl": box.get("stl"),
        "blk": box.get("blk"),
        "tov": box.get("tov"),
    }


def flatten_csv(row: dict[str, Any]) -> dict[str, Any] | None:
    player = str(first(row, "player", "player_name", "athlete", "athlete_display_name") or "").strip()
    game_date = str(first(row, "game_date", "date", "game_date_utc") or "")[:10]
    if not player or not game_date:
        return None
    return {
        "game_date": game_date,
        "player": player,
        "team": first(row, "team", "team_name", "team_abbreviation", "team_abbr"),
        "opponent": first(row, "opponent", "opp", "opponent_name"),
        "opponent_abbr": first(row, "opponent_abbr", "opp_abbr", "opponent_abbreviation"),
        "pts": first(row, "pts", "points"),
        "reb": first(row, "reb", "rebounds", "total_rebounds"),
        "ast": first(row, "ast", "assists"),
        "threes": first(row, "threes", "3pm", "fg3m", "three_points_made"),
        "stl": first(row, "stl", "steals"),
        "blk": first(row, "blk", "blocks"),
        "tov": first(row, "tov", "turnovers"),
    }


def quality(row: dict[str, Any]) -> int:
    return sum(num(row.get(field)) is not None for field in ("pts", "reb", "ast", "threes", "stl", "blk", "tov"))


def build() -> dict[str, Any]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    source_rows = 0

    if CANONICAL.exists():
        try:
            payload = json.load(CANONICAL.open(encoding="utf-8"))
            for raw in payload.get("records", []):
                if not isinstance(raw, dict):
                    continue
                row = flatten_canonical(raw)
                if not row:
                    continue
                source_rows += 1
                key = (row["game_date"], norm(row["player"]))
                if key not in merged or quality(row) >= quality(merged[key]):
                    merged[key] = row
        except Exception as exc:
            print(f"Canonical player-log warning: {exc}")

    patterns = (
        "data/raw/boxscore_player_stats_*.csv",
        "data/raw/wehoop_player_box_*.csv",
        "data/raw/player_results_*.csv",
    )
    for pattern in patterns:
        for path in glob.glob(pattern):
            try:
                with open(path, encoding="utf-8", newline="") as handle:
                    for raw in csv.DictReader(handle):
                        row = flatten_csv(raw)
                        if not row:
                            continue
                        source_rows += 1
                        key = (row["game_date"], norm(row["player"]))
                        if key not in merged or quality(row) > quality(merged[key]):
                            merged[key] = row
            except Exception as exc:
                print(f"Raw player-result warning {path}: {exc}")

    rows = [row for row in merged.values() if quality(row) >= 3]
    rows.sort(key=lambda r: (r["game_date"], norm(r["player"])))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "source_rows_seen": source_rows,
        "normalized_actual_rows": len(rows),
        "first_date": rows[0]["game_date"] if rows else None,
        "last_date": rows[-1]["game_date"] if rows else None,
        "output": str(OUT),
    }
    print(json.dumps(summary, indent=2))
    if not rows:
        raise SystemExit("No usable player actuals were available for Phase 5 grading.")
    return summary


if __name__ == "__main__":
    build()
