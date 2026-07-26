"""QA for Validation Week Commit 5 unified dashboard."""
from __future__ import annotations

import json
from pathlib import Path

DASH = Path("data/dashboard/wnba_validation_dashboard.json")
SUMMARY = Path("data/dashboard/wnba_validation_dashboard_summary.json")
TRACKER = Path("data/dashboard/wnba_live_prediction_tracker_summary.json")
GRADER = Path("data/dashboard/wnba_live_result_grader_summary.json")
PERF = Path("data/dashboard/wnba_live_performance_analytics_summary.json")
SIGNALS = Path("data/dashboard/wnba_signal_performance_summary.json")
VALID_STATES = {"COLLECTING", "VALIDATING", "RESEARCH_READY", "MODEL_READY"}


def load(path: Path):
    assert path.exists(), f"Missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def run():
    dash = load(DASH)
    summary = load(SUMMARY)
    tracker = load(TRACKER)
    grader = load(GRADER)
    perf = load(PERF)
    signals = load(SIGNALS)

    assert dash.get("status") in VALID_STATES
    assert summary.get("status") in VALID_STATES
    assert dash.get("status") == summary.get("status") == summary.get("overall_readiness")

    readiness = dash.get("readiness") or {}
    tracked = int(tracker.get("records_total") or 0)
    graded = int(perf.get("graded_records") or grader.get("validation_status_counts", {}).get("GRADED") or 0)
    signal_count = int(signals.get("signals_analyzed") or 0)

    assert readiness.get("predictions_tracked") == tracked
    assert readiness.get("predictions_graded") == graded
    assert readiness.get("signals_ranked") == signal_count
    assert summary.get("predictions_tracked") == tracked
    assert summary.get("predictions_graded") == graded
    assert summary.get("signals_ranked") == signal_count

    score = float(readiness.get("readiness_score") or 0)
    assert 0 <= score <= 100
    assert float(summary.get("readiness_score") or 0) == score

    coverage = readiness.get("grading_coverage")
    expected = round(graded / tracked, 6) if tracked else None
    assert coverage == expected
    assert summary.get("grading_coverage") == expected

    for key in ("sportsbook_performance", "market_performance", "tier_performance", "calibration_monitor"):
        assert isinstance(dash.get(key), list), f"{key} must be a list"

    leaderboard = dash.get("signal_leaderboard") or {}
    assert isinstance(leaderboard.get("top_signals", []), list)
    assert isinstance(leaderboard.get("top_combinations", []), list)
    assert isinstance(dash.get("data_readiness_warnings"), list)

    if tracked == 0:
        assert dash.get("status") == "COLLECTING"
        assert graded == 0
    if graded > tracked:
        raise AssertionError("Graded predictions cannot exceed tracked predictions")

    result = {
        "status": "PASS",
        "overall_readiness": dash.get("status"),
        "predictions_tracked": tracked,
        "predictions_graded": graded,
        "signals_ranked": signal_count,
        "readiness_score": score,
        "warnings": len(dash.get("data_readiness_warnings", [])),
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    run()
