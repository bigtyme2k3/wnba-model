"""Validation Week Commit 6: enrich processed live forecasts before validation capture.

The engine joins closing-line forecasts with opportunity, movement, entry-window, trend,
and sportsbook intelligence. It records research context only and never implies a wager.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PRED = Path("data/forecast/closing_line_predictions.json")
OPPS = Path("data/forecast/opportunity_scanner.json")
ENTRY = Path("data/market/entry_window_recommendations.json")
SIGNALS = Path("data/market/movement_classifications.json")
MOVES = Path("data/market/line_movements.json")
BOOKS = Path("data/forecast/sportsbook_leader_normalized.json")
OUT = Path("data/forecast/enriched_market_predictions.json")
DASH = Path("data/dashboard/wnba_market_enrichment_summary.json")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def rows(path: Path, *keys: str) -> list[dict[str, Any]]:
    payload = load(path)
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp(value: Any) -> float:
    n = num(value)
    return round(max(0.0, min(100.0, n if n is not None else 0.0)), 2)


def implied(price: Any) -> float | None:
    p = num(price)
    if p is None or p == 0:
        return None
    return (-p) / ((-p) + 100) if p < 0 else 100 / (p + 100)


def expected_closing_value(row: dict[str, Any]) -> dict[str, float | None]:
    current_point = num(row.get("current_point"))
    projected_point = num(row.get("projected_closing_point"))
    current_prob = implied(row.get("current_price"))
    projected_prob = implied(row.get("projected_closing_price"))
    return {
        "expected_point_move": None if current_point is None or projected_point is None else round(projected_point-current_point, 6),
        "expected_probability_move": None if current_prob is None or projected_prob is None else round(projected_prob-current_prob, 6),
    }


def quality_grade(score: float, forecast_ready: bool, sample_size: int) -> str:
    if not forecast_ready:
        return "RESEARCH"
    if sample_size < 12:
        return "RESEARCH"
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "AVOID"


def run() -> dict[str, Any]:
    generated = now()
    predictions = rows(PRED, "forecasts", "predictions")
    opp_map = {str(x.get("market_id")): x for x in rows(OPPS, "opportunities") if x.get("market_id")}
    entry_map = {str(x.get("market_id")): x for x in rows(ENTRY, "recommendations") if x.get("market_id")}
    signal_map = {str(x.get("market_id")): x for x in rows(SIGNALS, "classifications") if x.get("market_id")}
    move_map = {str(x.get("market_id")): x for x in rows(MOVES, "movements") if x.get("market_id")}
    book_payload = load(BOOKS)
    book_scores = {
        str(x.get("bookmaker")): clamp(x.get("normalized_efficiency_score"))
        for x in book_payload.get("sportsbooks", []) if isinstance(x, dict) and x.get("bookmaker")
    }

    enriched: list[dict[str, Any]] = []
    for prediction in predictions:
        mid = str(prediction.get("market_id") or "")
        if not mid:
            continue
        opp = opp_map.get(mid, {})
        entry = entry_map.get(mid, {})
        signal_row = signal_map.get(mid, {})
        move = move_map.get(mid, {})
        forecast_status = prediction.get("forecast_status") or "INSUFFICIENT_HISTORY"
        forecast_ready = forecast_status == "MODEL_READY"
        forecast_confidence = clamp(prediction.get("forecast_confidence")) if forecast_ready else 0.0
        sample_size = int(num(prediction.get("sample_size")) or 0)
        signal = opp.get("signal") or signal_row.get("classification") or "NORMAL"
        entry_action = opp.get("entry_action") or entry.get("action") or entry.get("recommendation") or "PASS"
        volatility = clamp(opp.get("volatility_score") if opp.get("volatility_score") is not None else move.get("volatility_score"))
        sportsbook_edge = book_scores.get(str(prediction.get("bookmaker")), 0.0)
        matched_clv = int(num(opp.get("matched_clv_trends")) or 0)
        matched_validated = int(num(opp.get("matched_validated_trends")) or 0)
        signal_strength = {"STEAM": 95, "SHARP": 90, "LATE_MONEY": 80, "BOOK_LEADER": 70, "NORMAL": 45, "MARKET_CORRECTION": 35, "POSSIBLE_INJURY": 25}.get(str(signal), 40)
        clv_confidence = clamp(0.55*forecast_confidence + 12*min(matched_clv, 2) + 18*min(matched_validated, 1) + 0.09*sportsbook_edge)
        derived_score = clamp(0.35*forecast_confidence + 0.20*signal_strength + 0.15*volatility + 0.15*clv_confidence + 0.15*sportsbook_edge)
        opportunity_score = clamp(opp.get("opportunity_score")) if opp else derived_score
        if not forecast_ready:
            opportunity_score = min(opportunity_score, 49.0)
        tier = opp.get("tier") or ("ELITE" if opportunity_score >= 85 else "STRONG" if opportunity_score >= 70 else "WATCH" if opportunity_score >= 55 else "LOW" if opportunity_score >= 40 else "AVOID")
        recommendation = opp.get("scanner_recommendation") or ("WATCH" if opportunity_score >= 55 else "PASS")
        if not forecast_ready and recommendation == "BET_NOW":
            recommendation = "WATCH"
        expected = expected_closing_value({**prediction, **opp})
        enriched.append({
            **prediction,
            "signal": signal,
            "entry_action": entry_action,
            "volatility_score": volatility,
            "sportsbook_edge_score": sportsbook_edge,
            "clv_confidence": clv_confidence,
            "market_quality_grade": quality_grade(opportunity_score, forecast_ready, sample_size),
            "expected_closing_value": expected,
            "expected_point_move": expected["expected_point_move"],
            "expected_probability_move": expected["expected_probability_move"],
            "matched_clv_trends": matched_clv,
            "matched_validated_trends": matched_validated,
            "opportunity_score": opportunity_score,
            "tier": tier,
            "scanner_recommendation": recommendation,
            "enrichment_source": "OPPORTUNITY_SCANNER" if opp else "DERIVED_MARKET_CONTEXT",
            "enriched_at_utc": generated,
            "warning": "Research enrichment only; no executed wager or guaranteed outcome is implied.",
        })

    enriched.sort(key=lambda x: (str(x.get("commence_time_utc") or ""), -float(x.get("opportunity_score") or 0), str(x.get("market_id") or "")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    DASH.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at_utc": generated,
        "methodology": "Joins forecast, timing, movement, trend, and sportsbook context before validation capture.",
        "predictions": enriched,
    }, indent=2), encoding="utf-8")
    summary = {
        "generated_at_utc": generated,
        "status": "READY" if enriched else "STANDBY",
        "predictions_enriched": len(enriched),
        "model_ready": sum(x.get("forecast_status") == "MODEL_READY" for x in enriched),
        "derived_context": sum(x.get("enrichment_source") == "DERIVED_MARKET_CONTEXT" for x in enriched),
        "opportunity_context": sum(x.get("enrichment_source") == "OPPORTUNITY_SCANNER" for x in enriched),
        "non_null_opportunity_scores": sum(x.get("opportunity_score") is not None for x in enriched),
        "non_null_signals": sum(bool(x.get("signal")) for x in enriched),
        "non_null_volatility": sum(x.get("volatility_score") is not None for x in enriched),
        "grade_counts": {g: sum(x.get("market_quality_grade") == g for x in enriched) for g in ["A+", "A", "B", "C", "RESEARCH", "AVOID"]},
        "top_enriched": sorted(enriched, key=lambda x: -float(x.get("opportunity_score") or 0))[:25],
        "warning": "Enrichment metrics are research features and do not represent placed wagers or guaranteed profit.",
    }
    DASH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
