"""Validation Week Commit 5: unified WNBA validation dashboard.

Aggregates tracker, grader, performance and signal analytics into one evidence-readiness view.
All profit and ROI values are simulated research metrics from captured model states.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACKER = Path("data/dashboard/wnba_live_prediction_tracker_summary.json")
GRADER = Path("data/dashboard/wnba_live_result_grader_summary.json")
PERF = Path("data/dashboard/wnba_live_performance_analytics_summary.json")
SIGNALS = Path("data/dashboard/wnba_signal_performance_summary.json")
BRIEF = Path("data/dashboard/wnba_daily_intelligence_brief.json")
PREDICTOR = Path("data/dashboard/wnba_closing_line_predictor_summary.json")
OUT = Path("data/dashboard/wnba_validation_dashboard.json")
SUMMARY = Path("data/dashboard/wnba_validation_dashboard_summary.json")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def readiness_state(tracked: int, graded: int, signals: int, calibration: int) -> tuple[str, float]:
    grading_rate = graded / tracked if tracked else 0.0
    score = 0.0
    score += min(30.0, tracked / 100 * 30.0)
    score += min(30.0, graded / 100 * 30.0)
    score += min(20.0, grading_rate * 20.0)
    score += min(10.0, signals / 10 * 10.0)
    score += min(10.0, calibration / 5 * 10.0)
    score = round(score, 2)
    if tracked < 20 or graded < 10:
        state = "COLLECTING"
    elif graded < 50 or grading_rate < 0.5:
        state = "VALIDATING"
    elif graded < 150 or signals < 3:
        state = "RESEARCH_READY"
    else:
        state = "MODEL_READY"
    return state, score


def run() -> dict[str, Any]:
    generated = now()
    tracker = load(TRACKER)
    grader = load(GRADER)
    perf = load(PERF)
    signals = load(SIGNALS)
    brief = load(BRIEF)
    predictor = load(PREDICTOR)

    tracked = int(tracker.get("records_total") or 0)
    open_records = int(tracker.get("open_records") or 0)
    graded = int(perf.get("graded_records") or grader.get("validation_status_counts", {}).get("GRADED") or 0)
    signals_ranked = int(signals.get("signals_analyzed") or 0)
    calibration = int(perf.get("calibration_buckets") or 0)
    state, readiness_score = readiness_state(tracked, graded, signals_ranked, calibration)
    grading_coverage = round(graded / tracked, 6) if tracked else None

    overall = perf.get("overall") or {}
    rolling = perf.get("rolling_windows") or {}
    dashboard = {
        "generated_at_utc": generated,
        "status": state,
        "readiness": {
            "overall_readiness": state,
            "readiness_score": readiness_score,
            "predictions_tracked": tracked,
            "predictions_graded": graded,
            "open_predictions": open_records,
            "grading_coverage": grading_coverage,
            "signals_ranked": signals_ranked,
            "calibration_buckets": calibration,
        },
        "live_validation": {
            "tracker_status": tracker.get("status", "MISSING"),
            "grader_status": grader.get("status", "MISSING"),
            "performance_status": perf.get("status", "MISSING"),
            "signal_status": signals.get("status", "MISSING"),
            "current_brief_status": brief.get("status", "MISSING"),
            "live_markets": (brief.get("slate") or {}).get("live_markets", 0),
            "events": (brief.get("slate") or {}).get("events", 0),
        },
        "forecast_performance": {
            "hit_rate": overall.get("hit_rate"),
            "simulated_profit_units": overall.get("profit_units", 0),
            "simulated_roi_per_record": overall.get("roi_per_record"),
            "average_closing_line_error": overall.get("average_closing_line_error"),
            "within_half_point_rate": overall.get("within_half_point_rate"),
            "within_one_point_rate": overall.get("within_one_point_rate"),
            "average_forecast_confidence": overall.get("average_forecast_confidence"),
            "predictor_status": predictor.get("status"),
            "walk_forward_predictions": predictor.get("walk_forward_predictions", 0),
        },
        "rolling_performance": rolling,
        "signal_leaderboard": {
            "best_signal": signals.get("best_signal"),
            "best_combination": signals.get("best_combination"),
            "top_signals": signals.get("top_signals", []),
            "top_combinations": signals.get("top_combinations", []),
            "qualified_signals": signals.get("qualified_signals", 0),
            "qualified_combinations": signals.get("qualified_combinations", 0),
        },
        "sportsbook_performance": perf.get("by_sportsbook", []),
        "market_performance": perf.get("by_market", []),
        "tier_performance": perf.get("by_tier", []),
        "calibration_monitor": perf.get("calibration", []),
        "data_readiness_warnings": [],
        "warning": "Validation metrics are simulated from captured model states and do not represent executed wagers or realized profit.",
    }

    warnings = dashboard["data_readiness_warnings"]
    if tracked == 0:
        warnings.append("No live prediction captures have been stored yet.")
    if tracked and graded == 0:
        warnings.append("Predictions are captured but no completed games have been graded yet.")
    if graded < 30:
        warnings.append("Sample size is too small for reliable performance conclusions.")
    if signals_ranked == 0:
        warnings.append("Signal rankings will appear after graded records accumulate.")
    if calibration == 0:
        warnings.append("Calibration monitoring is waiting for graded confidence samples.")

    summary = {
        "generated_at_utc": generated,
        "status": state,
        "predictions_tracked": tracked,
        "predictions_graded": graded,
        "open_predictions": open_records,
        "grading_coverage": grading_coverage,
        "signals_ranked": signals_ranked,
        "forecast_accuracy": overall.get("within_one_point_rate"),
        "hit_rate": overall.get("hit_rate"),
        "simulated_profit_units": overall.get("profit_units", 0),
        "overall_readiness": state,
        "readiness_score": readiness_score,
        "best_signal": signals.get("best_signal"),
        "best_combination": signals.get("best_combination"),
        "warnings": warnings,
        "warning": dashboard["warning"],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
