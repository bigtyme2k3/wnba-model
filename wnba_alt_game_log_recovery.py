"""Targeted recovery planner for pending ALT records missing verified game logs."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DIAGNOSTICS = Path("data/dashboard/wnba_alt_pending_diagnostics.json")
ALT_REPORT = Path("data/dashboard/wnba_alt_performance.json")
OUTPUT = Path("data/dashboard/wnba_alt_game_log_recovery.json")
WAREHOUSE = Path("data/warehouse/wnba_alt_game_log_recovery.json")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def inspector_rows(payload: dict) -> list[dict]:
    rows = payload.get("inspector") or payload.get("records") or []
    if rows:
        return [r for r in rows if isinstance(r, dict)]
    rows = []
    for group in payload.get("by_category", []):
        if group.get("category") != "missing_verified_game_log":
            continue
        rows.extend(group.get("examples") or [])
    return [r for r in rows if isinstance(r, dict)]


def build_payload() -> dict:
    diagnostics = load(DIAGNOSTICS)
    alt = load(ALT_REPORT)
    rows = inspector_rows(diagnostics)
    targeted = [r for r in rows if str(r.get("category") or "missing_verified_game_log") == "missing_verified_game_log"]
    dates = sorted({str(r.get("date")) for r in targeted if r.get("date")})
    games = sorted({str(r.get("expected_game_id") or r.get("game")) for r in targeted if r.get("expected_game_id") or r.get("game")})
    players = sorted({str(r.get("player")) for r in targeted if r.get("player")})
    by_date = Counter(str(r.get("date") or "unknown") for r in targeted)
    summary = alt.get("summary") or {}
    commands = [f"python wnba_play_by_play_layer.py --date {d}" for d in dates]
    commands += [f"python wnba_player_game_log_warehouse.py --date {d}" for d in dates]
    commands.append("python wnba_player_game_log_archive.py merge")
    commands += [f"python wnba_alt_performance_tracker.py --date {d} --grade" for d in dates]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if dates else "nothing_to_recover",
        "before": {
            "archived": int(summary.get("archived_candidates") or summary.get("archived") or 0),
            "graded": int(summary.get("graded") or 0),
            "pending": int(summary.get("pending") or 0),
        },
        "targets": {
            "records": len(targeted),
            "dates": dates,
            "games": games,
            "players": players,
            "by_date": [{"date": d, "records": by_date[d]} for d in dates],
        },
        "recovery_commands": commands,
    }


def write(payload: dict) -> None:
    text = json.dumps(payload, indent=2) + "\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    WAREHOUSE.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-dates", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    write(payload)
    print(" ".join(payload["targets"]["dates"]) if args.print_dates else json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
