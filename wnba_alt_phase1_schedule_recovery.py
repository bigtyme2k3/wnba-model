#!/usr/bin/env python3
"""Phase 1 deterministic ALT archive recovery.

Safe recovery rules:
- Only recover rows classified by the schedule audit as exact_date or unique_schedule_alias.
- Only use completed games.
- If the audited game is completed but the player is absent from its box score, treat that as a
  player/game mismatch unless the player appears in exactly one other completed game on the same
  official date.
- Never synthesize stats for postponed/cancelled games.
- Never grade a player who did not appear in the selected completed game.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "data/dashboard/wnba_alt_schedule_audit.json"
REPORT = ROOT / "data/dashboard/wnba_alt_phase1_schedule_recovery.json"

SAFE_CLASSES = {"exact_date", "unique_schedule_alias"}


def load_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, payload: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def main():
    audit = load_json(AUDIT, {})
    rows = audit.get("rows") or []

    safe = [r for r in rows if r.get("classification") in SAFE_CLASSES]
    invalid_schedule = []
    dnp_or_player_mismatch = []

    for row in safe:
        candidates = row.get("candidate_games") or []
        completed = [g for g in candidates if g.get("completed") is True]
        if not completed:
            invalid_schedule.append({
                "row_key": row.get("row_key"),
                "player": row.get("player"),
                "game": row.get("game"),
                "archive_date": row.get("date"),
                "classification": row.get("classification"),
                "reason": "no completed official game candidate; do not grade",
            })
            continue

        # This script intentionally does not invent a result when the player is not present in
        # the selected game's box score. That case belongs in the explicit DNP/player-mismatch
        # queue produced by the recovery workflow.
        if row.get("player_missing_from_selected_game"):
            dnp_or_player_mismatch.append({
                "row_key": row.get("row_key"),
                "player": row.get("player"),
                "game": row.get("game"),
                "archive_date": row.get("date"),
                "suggested_date": row.get("suggested_date"),
                "classification": row.get("classification"),
                "reason": "player absent from selected completed game; treat as DNP/player-game mismatch, not missing stat",
            })

    existing = load_json(REPORT, {})
    existing["invalid_schedule_rows"] = invalid_schedule
    existing["dnp_or_player_mismatch_rows"] = dnp_or_player_mismatch
    existing["policy"] = {
        "postponed_games": "never grade on postponed/cancelled event",
        "player_absent": "never synthesize stats; classify as DNP/player-game mismatch",
        "safe_classes": sorted(SAFE_CLASSES),
    }
    save_json(REPORT, existing)

    print(json.dumps({
        "safe_audit_rows": len(safe),
        "invalid_schedule_rows": len(invalid_schedule),
        "dnp_or_player_mismatch_rows": len(dnp_or_player_mismatch),
        "policy": existing["policy"],
    }))


if __name__ == "__main__":
    main()
