"""Acceptance tests for the compact WNBA odds-history warehouse."""
from __future__ import annotations

import tempfile
from pathlib import Path

import wnba_odds_history_warehouse as wh


def sample_payload():
    return {
        "timestamp": "2024-07-01T22:00:00Z",
        "previous_timestamp": "2024-07-01T21:55:00Z",
        "next_timestamp": "2024-07-01T22:05:00Z",
        "data": [{
            "id": "game-1",
            "sport_key": "basketball_wnba",
            "commence_time": "2024-07-02T00:00:00Z",
            "home_team": "Home Team",
            "away_team": "Away Team",
            "bookmakers": [{
                "key": "fanduel",
                "title": "FanDuel",
                "last_update": "2024-07-01T21:59:00Z",
                "markets": [
                    {"key": "h2h", "outcomes": [{"name": "Home Team", "price": -150}, {"name": "Away Team", "price": 130}]},
                    {"key": "spreads", "outcomes": [{"name": "Home Team", "point": -3.5, "price": -110}, {"name": "Away Team", "point": 3.5, "price": -110}]},
                    {"key": "totals", "outcomes": [{"name": "Over", "point": 161.5, "price": -108}, {"name": "Under", "point": 161.5, "price": -112}]},
                ],
            }],
        }],
    }


def test_ingest_and_deduplicate():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "warehouse.sqlite"
        con = wh.connect(db)
        usage = {"last": 30, "used": 30, "remaining": 970}
        wh.ingest(con, "2024-07-01T22:00:00Z", sample_payload(), usage)
        wh.ingest(con, "2024-07-01T22:00:00Z", sample_payload(), usage)
        assert con.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM odds").fetchone()[0] == 1
        row = con.execute("SELECT * FROM odds").fetchone()
        assert row["home_spread"] == -3.5
        assert row["total"] == 161.5
        assert row["home_moneyline"] == -150
        assert con.execute("SELECT COUNT(*) FROM closing_odds").fetchone()[0] == 1


def test_book_filter_and_timestamp_range():
    assert wh.BOOKMAKERS == "draftkings,fanduel"
    values = list(wh.stamps("2024-04-30", "2024-05-02", 22))
    assert values == ["2024-05-01T22:00:00Z", "2024-05-02T22:00:00Z"]


def main():
    tests = [test_ingest_and_deduplicate, test_book_filter_and_timestamp_range]
    failed = 0
    for test in tests:
        try:
            test()
            print("PASS", test.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL", test.__name__, exc)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
