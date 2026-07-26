"""QA for Validation Week Commit 2 live result grading."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("data/validation/live_prediction_results.json")
DASH = Path("data/dashboard/wnba_live_result_grader_summary.json")
VALID_STATUS = {"OPEN", "CLOSING_CAPTURED", "GRADED", "UNSUPPORTED", "UNRESOLVED"}
VALID_GRADE = {None, "WIN", "LOSS", "PUSH"}


def load(path: Path):
    assert path.exists(), f"Missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    payload = load(OUT)
    summary = load(DASH)
    rows = payload.get("records", [])
    assert isinstance(rows, list)

    ids = [x.get("capture_id") for x in rows]
    assert len(ids) == len(set(ids)), "Duplicate capture IDs"

    for row in rows:
        status = row.get("validation_status")
        grade = row.get("grade")
        assert status in VALID_STATUS, f"Invalid validation status: {status}"
        assert grade in VALID_GRADE, f"Invalid grade: {grade}"
        if status == "GRADED":
            assert grade in {"WIN", "LOSS", "PUSH"}
            assert row.get("final_home_score") is not None
            assert row.get("final_away_score") is not None
            assert row.get("profit_units") is not None
        if status == "CLOSING_CAPTURED":
            assert row.get("actual_closing_price") is not None or row.get("actual_closing_line") is not None
        error = row.get("closing_line_absolute_error")
        assert error is None or float(error) >= 0

    status_counts = {k: sum(x.get("validation_status") == k for x in rows) for k in VALID_STATUS}
    grade_counts = {k: sum(x.get("grade") == k for x in rows) for k in ["WIN", "LOSS", "PUSH"]}
    assert summary.get("records_total") == len(rows)
    for key, value in status_counts.items():
        assert summary.get("validation_status_counts", {}).get(key) == value
    for key, value in grade_counts.items():
        assert summary.get("grade_counts", {}).get(key) == value
    assert summary.get("status") == ("READY" if rows else "STANDBY")

    print(json.dumps({
        "status": "PASS",
        "records": len(rows),
        "graded": status_counts["GRADED"],
        "closing_captured": status_counts["CLOSING_CAPTURED"],
        "open": status_counts["OPEN"],
        "unsupported": status_counts["UNSUPPORTED"],
    }, indent=2))


if __name__ == "__main__":
    main()
