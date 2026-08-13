"""Targeted recovery planner for pending ALT records missing verified game logs.

Recovery is paired with the monotonic strict grader: existing final outcomes are
immutable and only unresolved rows may be promoted after verified game matching.

Blank recovery scope is historical-only. Current/future slate rows are deferred
so the backlog worker does not spend most of its time trying to grade games that
have not finished yet. A manual --date remains an explicit override.

The recovery plan is deliberately ordered oldest-first so verified historical
results are reconciled deterministically before newer pending observations.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from active_slate_date import resolve_target_date

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


def row_date(row: dict) -> str:
    return str(row.get("date") or "")[:10]


def build_payload(requested_date: str | None = None) -> dict:
    diagnostics = load(DIAGNOSTICS)
    alt = load(ALT_REPORT)
    rows = inspector_rows(diagnostics)
    missing = [r for r in rows if str(r.get("category") or "missing_verified_game_log") == "missing_verified_game_log"]

    active_date = resolve_target_date()
    deferred: list[dict] = []
    if requested_date:
        targeted = [r for r in missing if row_date(r) == requested_date]
    else:
        targeted = [r for r in missing if row_date(r) and row_date(r) < active_date]
        deferred = [r for r in missing if row_date(r) and row_date(r) >= active_date]

    dates = sorted({row_date(r) for r in targeted if row_date(r)})
    games = sorted({str(r.get("expected_game_id") or r.get("game")) for r in targeted if r.get("expected_game_id") or r.get("game")})
    players = sorted({str(r.get("player")) for r in targeted if r.get("player")})
    by_date = Counter(row_date(r) or "unknown" for r in targeted)
    deferred_by_date = Counter(row_date(r) or "unknown" for r in deferred)
    summary = alt.get("summary") or {}
    commands = []
    for d in dates:
        commands += [
            f"python wnba_play_by_play_layer.py --date {d}",
            f"python wnba_player_game_log_warehouse.py --date {d}",
            f"python wnba_alt_performance_tracker.py --date {d} --grade",
        ]
    commands.append("python wnba_player_game_log_archive.py merge")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_date": requested_date,
        "active_slate_date": active_date,
        "scope_policy": "explicit_single_date" if requested_date else "completed_history_only_oldest_first",
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
        "deferred_active_or_future": {
            "records": len(deferred),
            "dates": sorted(d for d in deferred_by_date if d != "unknown"),
            "by_date": [{"date": d, "records": deferred_by_date[d]} for d in sorted(deferred_by_date) if d != "unknown"],
            "reason": "automatic backlog recovery only processes dates before the active Eastern slate date",
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
    parser.add_argument("--date", help="Recover only one YYYY-MM-DD date")
    args = parser.parse_args()
    payload = build_payload(args.date)
    write(payload)
    print(" ".join(payload["targets"]["dates"]) if args.print_dates else json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
