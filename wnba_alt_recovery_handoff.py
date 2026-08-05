"""Normalize recovered player-game logs for the ALT performance grader.

Recovery providers use several equivalent field names. This bridge preserves the
source fields while adding the canonical `player` and `game_date` aliases expected
by wnba_alt_performance_tracker.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PATHS = (
    Path("data/warehouse/wnba_player_game_logs.json"),
    Path("data/dashboard/wnba_player_game_logs.json"),
)


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"records": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"records": []}


def normalize_record(row: dict[str, Any]) -> bool:
    changed = False
    player = row.get("player") or row.get("player_name") or row.get("athlete_name")
    game_date = row.get("game_date") or row.get("date") or row.get("event_date")
    if player and not row.get("player"):
        row["player"] = player
        changed = True
    if game_date and not row.get("game_date"):
        row["game_date"] = str(game_date)[:10]
        changed = True
    return changed


def main() -> None:
    canonical = load(PATHS[0])
    records = [row for row in canonical.get("records", []) if isinstance(row, dict)]
    changed = sum(normalize_record(row) for row in records)
    canonical["records"] = records

    for path in PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")

    usable = sum(bool(row.get("player") and row.get("game_date")) for row in records)
    print({"records": len(records), "normalized": changed, "canonical_player_dates": usable})


if __name__ == "__main__":
    main()
