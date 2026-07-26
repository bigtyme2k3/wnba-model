"""QA for Validation Week Commit 1 live prediction tracker."""
from __future__ import annotations

import json
from pathlib import Path

TRACKER = Path("data/validation/live_prediction_tracker.json")
SUMMARY = Path("data/dashboard/wnba_live_prediction_tracker_summary.json")


def load(path: Path):
    assert path.exists(), f"Missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    tracker = load(TRACKER)
    summary = load(SUMMARY)
    records = tracker.get("records", [])
    assert isinstance(records, list)
    keys = [(r.get("market_id"), r.get("captured_at_utc")) for r in records]
    assert len(keys) == len(set(keys)), "Duplicate market/timestamp captures"
    for r in records:
        assert r.get("market_id")
        assert r.get("captured_at_utc")
        assert r.get("validation_status") in {"OPEN", "CLOSED", "GRADED", "VOID"}
        assert r.get("scanner_recommendation") in {"BET_NOW", "WATCH", "PASS", None}
        score = r.get("opportunity_score")
        if score is not None:
            assert 0 <= float(score) <= 100
        confidence = r.get("forecast_confidence")
        if confidence is not None:
            assert 0 <= float(confidence) <= 100
    assert summary.get("records_total") == len(records)
    assert summary.get("open_records") == sum(r.get("validation_status") == "OPEN" for r in records)
    assert summary.get("status") in {"READY", "STANDBY", "NO_CHANGE"}
    added = int(summary.get("records_added") or 0)
    assert added <= len(records)
    print(json.dumps({
        "status": "PASS",
        "records": len(records),
        "records_added": added,
        "open_records": summary.get("open_records"),
        "events_captured": summary.get("events_captured"),
    }, indent=2))


if __name__ == "__main__":
    main()
