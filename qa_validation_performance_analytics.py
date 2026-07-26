"""QA for Validation Week Commit 3 performance analytics."""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path("data/validation/live_performance_analytics.json")
DASH = Path("data/dashboard/wnba_live_performance_analytics_summary.json")


def load(path: Path):
    if not path.exists():
        raise AssertionError(f"Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_metric(row: dict) -> None:
    assert row.get("records", 0) >= 0
    assert row.get("wins", 0) >= 0
    assert row.get("losses", 0) >= 0
    assert row.get("pushes", 0) >= 0
    assert row.get("decided", 0) == row.get("wins", 0) + row.get("losses", 0)
    for key in ("hit_rate", "within_half_point_rate", "within_one_point_rate"):
        value = row.get(key)
        assert value is None or 0 <= value <= 1
    assert row.get("average_closing_line_error") is None or row["average_closing_line_error"] >= 0


def main() -> None:
    data = load(DATA)
    dash = load(DASH)
    records = data.get("records", [])
    assert isinstance(records, list)
    ids = [str(x.get("capture_id")) for x in records]
    assert len(ids) == len(set(ids)), "Duplicate graded capture IDs"
    assert all(x.get("validation_status") == "GRADED" for x in records)
    assert all(x.get("grade") in {"WIN", "LOSS", "PUSH"} for x in records)

    check_metric(data.get("overall", {}))
    assert data["overall"]["records"] == len(records)
    for section in ("by_market", "by_sportsbook", "by_tier", "by_recommendation", "by_signal", "by_entry_action", "calibration"):
        rows = data.get(section, [])
        assert isinstance(rows, list)
        for row in rows:
            check_metric(row)
    for row in data.get("rolling_windows", {}).values():
        check_metric(row)

    assert dash.get("status") in {"READY", "STANDBY"}
    assert dash.get("graded_records") == len(records)
    assert dash.get("overall") == data.get("overall")
    assert dash.get("markets_analyzed") == len(data.get("by_market", []))
    assert dash.get("sportsbooks_analyzed") == len(data.get("by_sportsbook", []))
    assert dash.get("tiers_analyzed") == len(data.get("by_tier", []))
    assert dash.get("signals_analyzed") == len(data.get("by_signal", []))
    assert dash.get("calibration_buckets") == len(data.get("calibration", []))
    if records:
        assert dash["status"] == "READY"
    else:
        assert dash["status"] == "STANDBY"
    print(json.dumps({"status": "PASS", "graded_records": len(records), "markets": len(data.get("by_market", [])), "sportsbooks": len(data.get("by_sportsbook", [])), "calibration_buckets": len(data.get("calibration", []))}, indent=2))


if __name__ == "__main__":
    main()
