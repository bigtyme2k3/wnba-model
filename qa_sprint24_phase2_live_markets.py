"""QA for Sprint 24 Phase 2 live market integration."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

CATALOG = Path("data/warehouse/sprint24_phase2_live_market_catalog.json")
DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
SCANNER = Path("data/dashboard/wnba_live_scanner_summary.json")
LINES = Path("data/raw/line_shopping_today.csv")


def run() -> dict:
    catalog = json.loads(CATALOG.read_text())
    scanner = json.loads(SCANNER.read_text())
    con = sqlite3.connect(DB)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    recent_events = con.execute(
        """SELECT COUNT(DISTINCT w.event_id) FROM wagers w
        JOIN snapshots s ON s.snapshot_id=w.snapshot_id
        JOIN events e ON e.event_id=w.event_id
        WHERE s.endpoint_type='live_line_shopping' AND s.returned_at_utc>=?
          AND e.commence_time_utc>?""",
        (cutoff, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
    ).fetchone()[0]
    recent_books = {r[0] for r in con.execute(
        """SELECT DISTINCT w.bookmaker_key FROM wagers w JOIN snapshots s ON s.snapshot_id=w.snapshot_id
        WHERE s.endpoint_type='live_line_shopping' AND s.returned_at_utc>=?""", (cutoff,)
    )}
    recent_props = con.execute(
        """SELECT COUNT(*) FROM wagers w JOIN snapshots s ON s.snapshot_id=w.snapshot_id
        WHERE s.endpoint_type='live_line_shopping' AND s.returned_at_utc>=?
          AND w.market_key LIKE 'player_%'""", (cutoff,)
    ).fetchone()[0]
    con.close()

    tests = {
        "catalog_pass": catalog.get("status") == "PASS",
        "line_file_present": LINES.exists() and LINES.stat().st_size > 0,
        "events_ingested": int(catalog.get("events_ingested", 0)) > 0,
        "wagers_ingested": int(catalog.get("wagers_ingested", 0)) > 0,
        "recent_upcoming_events": recent_events > 0,
        "allowed_books_only": bool(recent_books) and recent_books.issubset({"draftkings", "fanduel"}),
        "scanner_ready": scanner.get("status") == "READY" and int(scanner.get("markets_available", 0)) > 0,
        "production_unchanged": catalog.get("production_recommendations_changed") is False,
    }
    result = {
        "status": "PASS" if all(tests.values()) else "FAIL",
        "tests": tests,
        "diagnostics": {
            "recent_upcoming_events": recent_events,
            "recent_books": sorted(recent_books),
            "recent_player_prop_rows": recent_props,
            "scanner_markets_available": scanner.get("markets_available", 0),
            "scanner_live_markets": scanner.get("live_markets", 0),
        },
        "failed": [k for k, v in tests.items() if not v],
    }
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    run()
