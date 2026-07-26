"""Validation Week Commit 3: aggregate graded live prediction performance.

All profit and ROI figures are simulated research results from preserved model states.
They do not represent executed wagers or realized returns.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable

RESULTS = Path("data/validation/live_prediction_results.json")
OUT = Path("data/validation/live_performance_analytics.json")
DASH = Path("data/dashboard/wnba_live_performance_analytics_summary.json")


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def record_time(row: dict[str, Any]) -> datetime | None:
    return parse(row.get("graded_at_utc") or row.get("commence_time_utc") or row.get("captured_at_utc"))


def metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(r.get("grade") == "WIN" for r in rows)
    losses = sum(r.get("grade") == "LOSS" for r in rows)
    pushes = sum(r.get("grade") == "PUSH" for r in rows)
    decided = wins + losses
    profit = round(sum(num(r.get("profit_units")) or 0 for r in rows), 6)
    staked = decided + pushes
    errors = [num(r.get("closing_line_absolute_error")) for r in rows]
    errors = [x for x in errors if x is not None]
    confidences = [num(r.get("forecast_confidence")) for r in rows]
    confidences = [x for x in confidences if x is not None]
    return {
        "records": len(rows),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "decided": decided,
        "hit_rate": round(wins / decided, 6) if decided else None,
        "profit_units": profit,
        "roi_per_record": round(profit / staked, 6) if staked else None,
        "average_closing_line_error": round(mean(errors), 6) if errors else None,
        "within_half_point_rate": round(sum(x <= 0.5 for x in errors) / len(errors), 6) if errors else None,
        "within_one_point_rate": round(sum(x <= 1.0 for x in errors) / len(errors), 6) if errors else None,
        "average_forecast_confidence": round(mean(confidences), 6) if confidences else None,
    }


def grouped(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = str(row.get(key) or "UNKNOWN")
        buckets[value].append(row)
    output = [{key: value, **metric(items)} for value, items in buckets.items()]
    output.sort(key=lambda x: (-x["records"], str(x[key])))
    return output


def rolling(rows: list[dict[str, Any]], current: datetime) -> dict[str, Any]:
    windows = {"last_7_days": 7, "last_30_days": 30, "season_to_date": None}
    out: dict[str, Any] = {}
    for name, days in windows.items():
        subset = rows if days is None else [r for r in rows if (record_time(r) and record_time(r) >= current - timedelta(days=days))]
        out[name] = metric(subset)
    return out


def calibration(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bins = [(0, 49), (50, 59), (60, 69), (70, 79), (80, 89), (90, 100)]
    out = []
    for lo, hi in bins:
        subset = []
        for row in rows:
            c = num(row.get("forecast_confidence"))
            if c is not None and lo <= c <= hi:
                subset.append(row)
        if not subset:
            continue
        item = metric(subset)
        item.update({"confidence_bucket": f"{lo}-{hi}", "bucket_min": lo, "bucket_max": hi})
        out.append(item)
    return out


def run() -> dict[str, Any]:
    current = now_dt()
    raw = load(RESULTS).get("records", [])
    records = raw if isinstance(raw, list) else []
    graded = [r for r in records if isinstance(r, dict) and r.get("validation_status") == "GRADED" and r.get("grade") in {"WIN", "LOSS", "PUSH"}]

    analytics = {
        "generated_at_utc": iso(current),
        "methodology": "Aggregates graded model-state captures by time window, market, sportsbook, tier, recommendation, signal, entry action, and confidence bucket.",
        "overall": metric(graded),
        "rolling_windows": rolling(graded, current),
        "by_market": grouped(graded, "market"),
        "by_sportsbook": grouped(graded, "bookmaker"),
        "by_tier": grouped(graded, "tier"),
        "by_recommendation": grouped(graded, "scanner_recommendation"),
        "by_signal": grouped(graded, "signal"),
        "by_entry_action": grouped(graded, "entry_action"),
        "calibration": calibration(graded),
        "records": graded,
        "warning": "Profit units and ROI are simulated research metrics from captured model states, not executed bets or realized profit.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    DASH.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(analytics, indent=2), encoding="utf-8")

    overall = analytics["overall"]
    summary = {
        "generated_at_utc": analytics["generated_at_utc"],
        "status": "READY" if graded else "STANDBY",
        "records_total": len(records),
        "graded_records": len(graded),
        "overall": overall,
        "rolling_windows": analytics["rolling_windows"],
        "markets_analyzed": len(analytics["by_market"]),
        "sportsbooks_analyzed": len(analytics["by_sportsbook"]),
        "tiers_analyzed": len(analytics["by_tier"]),
        "signals_analyzed": len(analytics["by_signal"]),
        "calibration_buckets": len(analytics["calibration"]),
        "best_market": max(analytics["by_market"], key=lambda x: (x.get("roi_per_record") if x.get("roi_per_record") is not None else -999, x["records"]), default=None),
        "best_sportsbook": max(analytics["by_sportsbook"], key=lambda x: (x.get("roi_per_record") if x.get("roi_per_record") is not None else -999, x["records"]), default=None),
        "warning": analytics["warning"],
    }
    DASH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
