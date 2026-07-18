"""Execute a previously generated historical odds backfill plan."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import wnba_odds_history_warehouse as warehouse

PLAN = Path("data/warehouse/wnba_odds_history_backfill_plan.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--db", type=Path, default=warehouse.DEFAULT_DB)
    parser.add_argument("--max-requests", type=int, required=True)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--api-key", default=os.getenv("ODDS_API_KEY"))
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("ODDS_API_KEY is required.")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    requested = [str(x) for x in plan.get("requested_timestamps", [])]
    if len(requested) > args.max_requests:
        raise SystemExit(f"Plan has {len(requested)} requests; cap is {args.max_requests}.")

    con = warehouse.connect(args.db)
    existing_days = {
        str(row[0])[:10]
        for row in con.execute("SELECT snapshot_time_utc FROM snapshots").fetchall()
        if row and row[0]
    }
    requested = [stamp for stamp in requested if stamp[:10] not in existing_days]
    run = {
        "planned": int(plan.get("batch_requests", 0)),
        "requested": len(requested),
        "skipped_existing": int(plan.get("batch_requests", 0)) - len(requested),
        "successful": 0,
        "failed": 0,
        "games_seen": 0,
        "odds_rows_seen": 0,
    }
    for stamp in requested:
        try:
            payload, usage = warehouse.request_snapshot(args.api_key, stamp)
            counts = warehouse.ingest(con, stamp, payload, usage)
            run["successful"] += 1
            run["games_seen"] += counts["games_seen"]
            run["odds_rows_seen"] += counts["odds_rows_seen"]
            print(f"OK {stamp}: {counts}; credits={usage}")
        except Exception as exc:
            run["failed"] += 1
            print(f"ERROR {stamp}: {exc}", file=sys.stderr)
        time.sleep(args.sleep)

    result = warehouse.summary(con, args.db, {"status": "planned_backfill_complete", "run": run})
    print(json.dumps(result, indent=2))
    if run["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
