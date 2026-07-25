"""QA for Sprint 15 Commit 2 line-movement artifacts."""
from __future__ import annotations

import json
from pathlib import Path

MOVEMENTS = Path("data/market/line_movements.json")
BOOKS = Path("data/market/sportsbook_movements.json")
VOLATILITY = Path("data/market/market_volatility.json")
SUMMARY = Path("data/dashboard/wnba_line_movement_summary.json")


def load(path: Path):
    if not path.exists():
        raise AssertionError(f"missing output: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    movements = load(MOVEMENTS).get("movements", [])
    comparisons = load(BOOKS).get("comparisons", [])
    volatility = load(VOLATILITY).get("markets", [])
    summary = load(SUMMARY)

    assert isinstance(movements, list)
    assert isinstance(comparisons, list)
    assert isinstance(volatility, list)
    assert summary["markets_analyzed"] == len(movements)
    assert summary["sportsbook_comparisons"] == len(comparisons)
    assert len(volatility) == len(movements)

    market_ids = [x["market_id"] for x in movements]
    assert len(market_ids) == len(set(market_ids)), "duplicate market movement rows"

    valid_directions = {"STRONG_UP", "UP", "NEUTRAL", "DOWN", "STRONG_DOWN"}
    for row in movements:
        assert row["direction"] in valid_directions
        assert row["observation_count"] >= 1
        assert row["movement_count"] >= 0
        assert row["movement_count"] <= max(0, row["observation_count"] - 1)
        assert 0 <= row["volatility_score"] <= 100
        assert row["largest_point_move"] >= 0
        assert row["largest_price_move"] >= 0
        if row["first_movement_time_utc"] and row["last_movement_time_utc"]:
            assert row["first_movement_time_utc"] <= row["last_movement_time_utc"]

    scores = [x["volatility_score"] for x in volatility]
    assert scores == sorted(scores, reverse=True), "volatility output not sorted"

    for row in comparisons:
        assert set(row) >= {"draftkings", "fanduel", "event_id", "market", "outcome_key"}
        assert row["first_book_to_move"] in {None, "draftkings", "fanduel"}
        if row["movement_lag_minutes"] is not None:
            assert row["movement_lag_minutes"] >= 0

    expected_status = "READY" if movements else "STANDBY"
    assert summary["status"] == expected_status
    print(json.dumps({
        "status": "PASS",
        "markets": len(movements),
        "with_movement": summary["markets_with_movement"],
        "comparisons": len(comparisons),
        "high_volatility": summary["high_volatility_markets"],
    }, indent=2))


if __name__ == "__main__":
    main()
