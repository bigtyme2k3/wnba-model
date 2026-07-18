"""Acceptance tests for the WNBA odds-history trend engine."""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import wnba_odds_history_trend_engine as trend
import wnba_odds_history_warehouse as warehouse


def seed(path: Path) -> None:
    con = warehouse.connect(path)
    game = {
        "id": "g1", "sport_key": "basketball_wnba", "commence_time": "2024-07-02T23:00:00Z",
        "home_team": "Home", "away_team": "Away",
    }
    first = {
        "timestamp": "2024-07-02T18:00:00Z",
        "data": [{**game, "bookmakers": [
            {"key": "draftkings", "title": "DraftKings", "last_update": "2024-07-02T18:00:00Z", "markets": [
                {"key": "spreads", "outcomes": [{"name": "Home", "point": -3.5, "price": -110}, {"name": "Away", "point": 3.5, "price": -110}]},
                {"key": "totals", "outcomes": [{"name": "Over", "point": 160.5, "price": -110}, {"name": "Under", "point": 160.5, "price": -110}]},
                {"key": "h2h", "outcomes": [{"name": "Home", "price": -160}, {"name": "Away", "price": 135}]},
            ]},
            {"key": "fanduel", "title": "FanDuel", "last_update": "2024-07-02T18:00:00Z", "markets": [
                {"key": "spreads", "outcomes": [{"name": "Home", "point": -4.0, "price": -110}, {"name": "Away", "point": 4.0, "price": -110}]},
                {"key": "totals", "outcomes": [{"name": "Over", "point": 161.0, "price": -110}, {"name": "Under", "point": 161.0, "price": -110}]},
                {"key": "h2h", "outcomes": [{"name": "Home", "price": -170}, {"name": "Away", "price": 140}]},
            ]}
        ]}]
    }
    second = json.loads(json.dumps(first))
    second["timestamp"] = "2024-07-02T22:00:00Z"
    second["data"][0]["bookmakers"][0]["markets"][0]["outcomes"][0]["point"] = -4.5
    second["data"][0]["bookmakers"][0]["markets"][1]["outcomes"][0]["point"] = 162.0
    second["data"][0]["bookmakers"][1]["markets"][0]["outcomes"][0]["point"] = -5.0
    second["data"][0]["bookmakers"][1]["markets"][1]["outcomes"][0]["point"] = 162.5
    warehouse.ingest(con, first["timestamp"], first, {"last": 30, "used": 30, "remaining": 970})
    warehouse.ingest(con, second["timestamp"], second, {"last": 30, "used": 60, "remaining": 940})
    con.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.sqlite"
        seed(db)
        old_w, old_d = trend.WAREHOUSE_OUT, trend.DASHBOARD_OUT
        trend.WAREHOUSE_OUT = Path(tmp) / "warehouse.json"
        trend.DASHBOARD_OUT = Path(tmp) / "dashboard.json"
        try:
            payload = trend.build(db)
        finally:
            trend.WAREHOUSE_OUT, trend.DASHBOARD_OUT = old_w, old_d
        assert payload["summary"]["games"] == 1
        assert payload["summary"]["series_with_multiple_snapshots"] == 2
        gaps = payload["market_disagreement"]["all_games"][0]
        assert gaps["spread_gap"] == -0.5
        assert gaps["total_gap"] == 0.5
        series = payload["line_movement"]["all_game_book_series"]
        dk = next(x for x in series if x["bookmaker_key"] == "draftkings")
        assert dk["spread_move"] == -1.0
        assert dk["total_move"] == 1.5
        assert payload["outcome_analytics"]["status"] == "waiting_for_final_scores"
        assert trend.DASHBOARD_OUT == old_d
    print("PASS qa_odds_history_trend_engine")


if __name__ == "__main__":
    main()
