"""Plan safe, non-duplicative WNBA historical odds backfill batches.

Reads the existing SQLite warehouse and produces the next missing daily snapshot
requests for a requested season/date range. This lets GitHub Actions show the
exact request count and estimated credit budget before The Odds API is called.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DB = Path("data/warehouse/wnba_odds_history.sqlite")
OUT = Path("data/warehouse/wnba_odds_history_backfill_plan.json")


def utc_stamp(day: date, hour_utc: int) -> str:
    return datetime(day.year, day.month, day.day, hour_utc, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def existing_snapshot_days(db: Path) -> set[str]:
    if not db.exists():
        return set()
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT snapshot_time_utc FROM snapshots").fetchall()
    except sqlite3.Error:
        return set()
    finally:
        con.close()
    return {str(row[0])[:10] for row in rows if row and row[0]}


def build_plan(start: str, end: str, hour_utc: int, batch_size: int, db: Path = DB) -> dict[str, Any]:
    start_day = date.fromisoformat(start)
    end_day = date.fromisoformat(end)
    if end_day < start_day:
        raise ValueError("end must not precede start")
    if not 0 <= hour_utc <= 23:
        raise ValueError("hour_utc must be between 0 and 23")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    existing = existing_snapshot_days(db)
    eligible: list[str] = []
    current = start_day
    while current <= end_day:
        if 5 <= current.month <= 10:
            eligible.append(current.isoformat())
        current += timedelta(days=1)

    missing = [day for day in eligible if day not in existing]
    batch_days = missing[:batch_size]
    requested = [utc_stamp(date.fromisoformat(day), hour_utc) for day in batch_days]
    estimated_credits = len(requested) * 30

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "database": str(db),
        "range": {"start": start, "end": end, "snapshot_hour_utc": hour_utc},
        "eligible_days": len(eligible),
        "already_collected_days": len([day for day in eligible if day in existing]),
        "missing_days": len(missing),
        "batch_size_requested": batch_size,
        "batch_requests": len(requested),
        "estimated_credits": estimated_credits,
        "batch_start": batch_days[0] if batch_days else None,
        "batch_end": batch_days[-1] if batch_days else None,
        "requested_timestamps": requested,
        "remaining_after_batch": max(0, len(missing) - len(requested)),
        "status": "ready" if requested else "complete",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--hour-utc", type=int, default=22)
    parser.add_argument("--batch-size", type=int, default=7)
    parser.add_argument("--db", type=Path, default=DB)
    args = parser.parse_args()
    print(json.dumps(build_plan(args.start, args.end, args.hour_utc, args.batch_size, args.db), indent=2))


if __name__ == "__main__":
    main()
