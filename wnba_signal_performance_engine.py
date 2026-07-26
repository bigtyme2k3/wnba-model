"""Validation Week Commit 4: evaluate live signal performance and combinations.

Consumes graded live prediction records and measures how individual signals and
selected signal combinations perform. Results are research simulations only and
do not represent executed wagers or realized profit.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

SOURCE = Path("data/validation/live_prediction_results.json")
OUT = Path("data/validation/signal_performance.json")
DASH = Path("data/dashboard/wnba_signal_performance_summary.json")

MIN_GRADE_SAMPLE = 10
MIN_COMBO_SAMPLE = 8


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def normalize_signal(value: Any) -> str | None:
    text = str(value or "").strip().upper().replace(" ", "_")
    if not text or text in {"NONE", "NULL", "NORMAL"}:
        return None
    return text


def record_signals(row: dict[str, Any]) -> list[str]:
    signals: set[str] = set()

    market_signal = normalize_signal(row.get("signal"))
    if market_signal:
        signals.add(f"SIGNAL:{market_signal}")

    entry = normalize_signal(row.get("entry_action"))
    if entry:
        signals.add(f"ENTRY:{entry}")

    recommendation = normalize_signal(row.get("scanner_recommendation"))
    if recommendation:
        signals.add(f"SCANNER:{recommendation}")

    tier = normalize_signal(row.get("tier"))
    if tier:
        signals.add(f"TIER:{tier}")

    bookmaker = normalize_signal(row.get("bookmaker"))
    if bookmaker:
        signals.add(f"BOOK:{bookmaker}")

    market = normalize_signal(row.get("market"))
    if market:
        signals.add(f"MARKET:{market}")

    if int(row.get("matched_clv_trends") or 0) > 0:
        signals.add("TREND:CLV_MATCH")
    if int(row.get("matched_validated_trends") or 0) > 0:
        signals.add("TREND:OUTCOME_VALIDATED")

    confidence = num(row.get("forecast_confidence"))
    if confidence is not None:
        bucket = "90_PLUS" if confidence >= 90 else "80_89" if confidence >= 80 else "70_79" if confidence >= 70 else "60_69" if confidence >= 60 else "50_59" if confidence >= 50 else "UNDER_50"
        signals.add(f"CONFIDENCE:{bucket}")

    return sorted(signals)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(r.get("grade") == "WIN" for r in rows)
    losses = sum(r.get("grade") == "LOSS" for r in rows)
    pushes = sum(r.get("grade") == "PUSH" for r in rows)
    decided = wins + losses
    profit = round(sum(float(r.get("profit_units") or 0) for r in rows), 6)
    errors = [num(r.get("closing_line_absolute_error")) for r in rows]
    errors = [x for x in errors if x is not None]
    clv = []
    for r in rows:
        captured = num(r.get("current_line"))
        closing = num(r.get("actual_closing_line"))
        if captured is not None and closing is not None:
            clv.append(abs(closing - captured))
    records = len(rows)
    return {
        "records": records,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "decided": decided,
        "hit_rate": round(wins / decided, 6) if decided else None,
        "profit_units": profit,
        "roi_per_record": round(profit / records, 6) if records else None,
        "average_closing_line_error": round(sum(errors) / len(errors), 6) if errors else None,
        "within_half_point_rate": round(sum(x <= 0.5 for x in errors) / len(errors), 6) if errors else None,
        "within_one_point_rate": round(sum(x <= 1.0 for x in errors) / len(errors), 6) if errors else None,
        "average_absolute_clv": round(sum(clv) / len(clv), 6) if clv else None,
        "average_forecast_confidence": round(sum(float(r.get("forecast_confidence")) for r in rows if num(r.get("forecast_confidence")) is not None) / sum(1 for r in rows if num(r.get("forecast_confidence")) is not None), 6) if any(num(r.get("forecast_confidence")) is not None for r in rows) else None,
    }


def research_grade(metrics: dict[str, Any], combo: bool = False) -> str:
    sample = int(metrics.get("records") or 0)
    minimum = MIN_COMBO_SAMPLE if combo else MIN_GRADE_SAMPLE
    hit = metrics.get("hit_rate")
    roi = metrics.get("roi_per_record")
    if sample < minimum or hit is None or roi is None:
        return "RESEARCH"
    if sample >= 50 and hit >= 0.60 and roi >= 0.08:
        return "A+"
    if sample >= 30 and hit >= 0.56 and roi >= 0.04:
        return "A"
    if sample >= 20 and hit >= 0.53 and roi > 0:
        return "B"
    if hit >= 0.50 and roi >= -0.02:
        return "C"
    return "AVOID"


def score(metrics: dict[str, Any], combo: bool = False) -> float:
    sample = int(metrics.get("records") or 0)
    hit = metrics.get("hit_rate") or 0
    roi = metrics.get("roi_per_record") or 0
    accuracy = metrics.get("within_one_point_rate") or 0
    reliability = min(1.0, sample / (40 if combo else 60))
    raw = 100 * (0.35 * hit + 0.30 * max(0.0, min(1.0, roi + 0.5)) + 0.20 * accuracy + 0.15 * reliability)
    return round(max(0.0, min(100.0, raw)), 2)


def run() -> dict[str, Any]:
    generated = now()
    payload = load(SOURCE)
    records = payload.get("records", [])
    records = records if isinstance(records, list) else []
    graded = [r for r in records if isinstance(r, dict) and r.get("validation_status") == "GRADED" and r.get("grade") in {"WIN", "LOSS", "PUSH"}]

    signal_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    combo_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in graded:
        signals = record_signals(row)
        for signal in signals:
            signal_rows[signal].append(row)
        core = [s for s in signals if s.startswith(("SIGNAL:", "ENTRY:", "SCANNER:", "TREND:", "CONFIDENCE:"))]
        for size in (2, 3):
            for combo in combinations(core, size):
                combo_rows[" + ".join(combo)].append(row)

    signal_results = []
    for name, rows in signal_rows.items():
        metrics = summarize(rows)
        signal_results.append({"signal": name, **metrics, "signal_score": score(metrics), "grade": research_grade(metrics)})

    combo_results = []
    for name, rows in combo_rows.items():
        metrics = summarize(rows)
        combo_results.append({"combination": name, **metrics, "signal_score": score(metrics, combo=True), "grade": research_grade(metrics, combo=True)})

    signal_results.sort(key=lambda x: (-x["signal_score"], -x["records"], x["signal"]))
    combo_results.sort(key=lambda x: (-x["signal_score"], -x["records"], x["combination"]))

    qualified_signals = [x for x in signal_results if x["grade"] not in {"RESEARCH", "AVOID"}]
    qualified_combos = [x for x in combo_results if x["grade"] not in {"RESEARCH", "AVOID"}]

    output = {
        "generated_at_utc": generated,
        "methodology": "Observed live validation performance by model signal and signal combination. Simulated research results only.",
        "minimum_samples": {"signal_grade": MIN_GRADE_SAMPLE, "combination_grade": MIN_COMBO_SAMPLE},
        "graded_records": len(graded),
        "signals": signal_results,
        "combinations": combo_results,
    }
    summary = {
        "generated_at_utc": generated,
        "status": "READY" if graded else "STANDBY",
        "graded_records": len(graded),
        "signals_analyzed": len(signal_results),
        "signal_combinations": len(combo_results),
        "qualified_signals": len(qualified_signals),
        "qualified_combinations": len(qualified_combos),
        "best_signal": signal_results[0] if signal_results else None,
        "best_combination": combo_results[0] if combo_results else None,
        "top_signals": signal_results[:20],
        "top_combinations": combo_results[:20],
        "warning": "Metrics are simulated from captured model states and do not represent executed wagers or realized profit.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    DASH.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    DASH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
