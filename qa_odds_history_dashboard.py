"""Acceptance checks for the WNBA odds-history dashboard builder."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import wnba_odds_history_dashboard as dashboard
import wnba_odds_history_warehouse as warehouse


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp) / "test.sqlite"
        con = warehouse.connect(db)
        payload = {
            "timestamp": "2024-07-01T21:55:38Z",
            "data": [{
                "id": "game-1", "sport_key": "basketball_wnba",
                "commence_time": "2024-07-01T23:00:00Z",
                "home_team": "Home", "away_team": "Away",
                "bookmakers": [
                    {"key": "draftkings", "title": "DraftKings", "markets": [
                        {"key": "spreads", "outcomes": [{"name": "Home", "point": -3.5, "price": -110}, {"name": "Away", "point": 3.5, "price": -110}]},
                        {"key": "totals", "outcomes": [{"name": "Over", "point": 161.5, "price": -110}, {"name": "Under", "point": 161.5, "price": -110}]},
                        {"key": "h2h", "outcomes": [{"name": "Home", "price": -155}, {"name": "Away", "price": 135}]},
                    ]},
                    {"key": "fanduel", "title": "FanDuel", "markets": [
                        {"key": "spreads", "outcomes": [{"name": "Home", "point": -4.0, "price": -108}, {"name": "Away", "point": 4.0, "price": -112}]},
                    ]},
                ],
            }],
        }
        warehouse.ingest(con, "2024-07-01T22:00:00Z", payload, {"last": 30, "used": 30, "remaining": 470})
        con.close()
        original_out, original_warehouse_out = dashboard.OUT, dashboard.WAREHOUSE_OUT
        dashboard.OUT = Path(temp) / "dashboard.json"
        dashboard.WAREHOUSE_OUT = Path(temp) / "warehouse.json"
        report = dashboard.build(db)
        dashboard.OUT, dashboard.WAREHOUSE_OUT = original_out, original_warehouse_out
        assert report["status"] == "ok"
        assert report["summary"]["games"] == 1
        assert report["summary"]["odds_rows"] == 2
        assert len(report["bookmaker_coverage"]) == 2
        assert report["market_coverage"]["spreads"] == 2
        assert report["market_coverage"]["totals"] == 1
        assert report["summary"]["api_requests_remaining"] == 470
        assert report["notes"]["movement_ready"] is False
        assert dashboard.Path(temp, "dashboard.json").exists()
    print("PASS odds history dashboard QA")


if __name__ == "__main__":
    main()
