from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from wnba_projection_contract import (
    canonical_stat,
    first_plausible_projection,
    projection_ceiling,
    validate_projection,
)

DASH = Path("data/dashboard")
WARE = Path("data/warehouse")
M02 = DASH / "wnba_s19_m02_predictions.json"
ALT = DASH / "wnba_alt_market_warehouse.json"
OUTS = [DASH / "wnba_daily_edges.json", WARE / "wnba_daily_edges.json"]
BAD_SOURCE_STATUSES = {"error", "failed", "failure", "fetch_failed", "invalid", "missing", "stale", "standby", "unavailable"}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def first_number(row: dict[str, Any], *keys: str) -> float | None:
    return num(first_value(row, *keys))


def american_decimal(odds: Any) -> float | None:
    value = num(odds)
    if value is None or value == 0:
        return None
    return 1 + 100 / -value if value < 0 else 1 + value / 100


def implied_probability(odds: Any) -> float | None:
    dec = american_decimal(odds)
    return None if dec is None else 1 / dec


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def list_rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def history_values(row: dict[str, Any]) -> list[float]:
    for key in ("last10", "recent_values", "history", "game_log", "game_logs", "last5_vals"):
        raw = row.get(key)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = []
        if not isinstance(raw, list):
            continue
        values: list[float] = []
        for item in raw:
            if isinstance(item, dict):
                value = first_number(item, "value", "stat_value", str(row.get("stat") or "").lower())
            else:
                value = num(item)
            value, _ = validate_projection(row.get("stat") or row.get("market"), value)
            if value is not None:
                values.append(value)
        if values:
            return values[:10]
    return []


def is_hit(value: float, line: float, side: str) -> bool:
    return value < line if side == "UNDER" else value > line


def canonical_candidate(
    row: dict[str, Any],
    target: str,
    source_kind: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    stat = canonical_stat(first_value(row, "stat", "market", "market_key", "prop_type"))
    line = first_number(row, "line", "consensus_line", "threshold", "best_line")
    fields = ("model_projection",) if source_kind == "m02" else (
        "model_projection", "projection", "pred", "projected_value", "proj"
    )
    projection, source_field, rejected = first_plausible_projection(row, stat, fields)
    player = row.get("player") or row.get("player_name")
    if not stat or not player or line is None or projection is None:
        reason = "missing_identity_or_line"
        if projection is None:
            reason = rejected[0]["reason"] if rejected else "missing_projection"
        return None, {
            "player": player,
            "game": row.get("game"),
            "stat": stat,
            "line": line,
            "source_kind": source_kind,
            "reason": reason,
            "projection_rejections": rejected,
        }

    side = str(first_value(row, "recommendation", "signal", "side") or "PASS").upper()
    if side not in {"OVER", "UNDER", "PASS"}:
        side = "PASS"
    odds = first_value(row, "odds", "price", "american_odds")
    sportsbook = first_value(row, "sportsbook", "best_book", "book")
    if side == "OVER":
        odds = odds if odds not in (None, "") else row.get("best_over_price")
        sportsbook = sportsbook or row.get("best_over_book")
    elif side == "UNDER":
        odds = odds if odds not in (None, "") else row.get("best_under_price")
        sportsbook = sportsbook or row.get("best_under_book")

    item = dict(row)
    item.update({
        "target_date": target,
        "player": player,
        "stat": stat,
        "market": stat,
        "side": side,
        "signal": side,
        "line": line,
        "projection": projection,
        "projection_source_field": source_field,
        "projection_validated": True,
        "projection_ceiling": projection_ceiling(stat),
        "odds": odds,
        "sportsbook": sportsbook,
        "market_type": "alternate" if source_kind == "alt" else "standard",
        "source": row.get("prediction_source") or row.get("source") or (
            "sprint19_m02_predictions" if source_kind == "m02" else "alt_market_warehouse"
        ),
    })
    return item, None


def source_candidates(target: str) -> tuple[list[tuple[dict[str, Any], str]], dict[str, Any]]:
    m02 = load(M02, {})
    source_target = str(m02.get("target_date") or "")[:10] if isinstance(m02, dict) else ""
    source_status = str(m02.get("status") or "missing").strip().lower() if isinstance(m02, dict) else "missing"
    empty_slate = bool(m02.get("empty_slate")) if isinstance(m02, dict) else False
    state = "ready"
    reason = None
    if source_target != target:
        state = "stale"
        reason = f"m02_target_mismatch:{source_target or 'missing'}!={target}"
    elif source_status != "ready":
        state = "stale" if source_status in BAD_SOURCE_STATUSES else "invalid"
        reason = f"m02_status:{source_status}"

    standard = list_rows(m02, "player_props") if state == "ready" else []
    if state == "ready" and empty_slate:
        if standard:
            state = "invalid"
            reason = f"m02_empty_slate_with_rows:{len(standard)}"
        standard = []
    off_target = [
        row for row in standard
        if str(row.get("target_date") or source_target)[:10] != target
    ]
    if off_target:
        state = "invalid"
        reason = f"m02_off_target_rows:{len(off_target)}"
        standard = []

    alt = load(ALT, {})
    alt_target = str(alt.get("target_date") or "")[:10] if isinstance(alt, dict) else ""
    alt_status = str(alt.get("status") or "missing").strip().lower() if isinstance(alt, dict) else "missing"
    alt_rows = []
    alt_off_target: list[dict[str, Any]] = []
    if state == "ready" and not empty_slate and alt_target == target and alt_status not in BAD_SOURCE_STATUSES:
        alt_rows = list_rows(alt, "rows")
        alt_off_target = [
            row for row in alt_rows
            if str(row.get("target_date") or row.get("date") or alt_target)[:10] != target
        ]
        if alt_off_target:
            state = "invalid"
            reason = f"alt_off_target_rows:{len(alt_off_target)}"
            standard = []
            alt_rows = []

    rows = [(row, "m02") for row in standard] + [(row, "alt") for row in alt_rows]
    return rows, {
        "state": state,
        "reason": reason,
        "source": str(M02),
        "source_target_date": source_target or None,
        "source_status": source_status,
        "empty_slate": empty_slate,
        "standard_rows": len(standard),
        "off_target_rows": len(off_target),
        "alt_source": str(ALT),
        "alt_target_date": alt_target or None,
        "alt_status": alt_status,
        "alt_rows": len(alt_rows),
        "alt_off_target_rows": len(alt_off_target),
    }


def component_scores(
    row: dict[str, Any],
) -> tuple[dict[str, float], list[str], dict[str, bool], float | None]:
    line = num(row.get("line"))
    projection = num(row.get("projection"))
    side = str(row.get("side") or "PASS").upper()
    odds = row.get("odds")
    values = history_values(row)
    directional = side in {"OVER", "UNDER"}
    available = {
        "projection": directional and line is not None and projection is not None,
        "recent_form": directional and line is not None and bool(values),
        "season_history": False,
        "clv": False,
        "roi": False,
        "market_value": False,
        "sample_strength": bool(values) or first_number(row, "season_games", "sample_size") is not None,
    }

    projection_score = 50.0
    reasons: list[str] = []
    if available["projection"]:
        edge = projection - line if side == "OVER" else line - projection
        scale = max(1.0, abs(line) * 0.12)
        projection_score = clamp(50 + 35 * edge / scale)
        reasons.append(f"Projection edge {edge:+.2f} versus line")

    l5 = values[:5]
    l10 = values[:10]
    l5_rate = sum(is_hit(v, line, side) for v in l5) / len(l5) if directional and line is not None and l5 else None
    l10_rate = sum(is_hit(v, line, side) for v in l10) / len(l10) if directional and line is not None and l10 else None
    trend_score = 50.0
    if l5_rate is not None or l10_rate is not None:
        blended = ((l5_rate if l5_rate is not None else 0.5) * 0.6) + ((l10_rate if l10_rate is not None else 0.5) * 0.4)
        trend_score = clamp(blended * 100)
        reasons.append(f"Recent hit rate L5 {round((l5_rate or 0)*100)}%, L10 {round((l10_rate or 0)*100)}%")

    season_rate = first_number(row, "season_pct", "season_hit_rate", "historical_probability")
    available["season_history"] = season_rate is not None
    season_score = clamp((season_rate if season_rate is not None else 0.5) * 100)
    if season_rate is not None:
        reasons.append(f"Season/historical hit rate {season_rate:.1%}")

    clv = first_number(row, "avg_clv", "clv", "closing_line_value")
    available["clv"] = clv is not None
    clv_score = 50.0 if clv is None else clamp(50 + clv * 12)
    if clv is not None:
        reasons.append(f"Historical CLV {clv:+.2f}")

    roi = first_number(row, "roi", "historical_roi")
    available["roi"] = roi is not None
    roi_score = 50.0 if roi is None else clamp(50 + roi * (100 if abs(roi) <= 2 else 1))
    if roi is not None:
        reasons.append(f"Historical ROI {roi:.1%}" if abs(roi) <= 2 else f"Historical ROI {roi:+.1f}")

    market_prob = implied_probability(odds)
    model_prob = None
    if directional and (available["projection"] or available["recent_form"] or available["season_history"]):
        model_prob = clamp((projection_score * 0.45 + trend_score * 0.35 + season_score * 0.20) / 100, 0.01, 0.99)
    value_score = 50.0
    if market_prob is not None and model_prob is not None:
        probability_edge = model_prob - market_prob
        value_score = clamp(50 + probability_edge * 220)
        available["market_value"] = True
        reasons.append(f"Model probability edge {probability_edge:+.1%}")

    sample = max(len(l10), int(first_number(row, "season_games", "sample_size") or 0))
    sample_score = clamp(20 + math.sqrt(sample) * 12) if sample else 20.0

    return {
        "projection": round(projection_score, 2),
        "recent_form": round(trend_score, 2),
        "season_history": round(season_score, 2),
        "clv": round(clv_score, 2),
        "roi": round(roi_score, 2),
        "market_value": round(value_score, 2),
        "sample_strength": round(sample_score, 2),
    }, reasons, available, model_prob


def score_row(row: dict[str, Any]) -> dict[str, Any]:
    components, reasons, available, model_prob = component_scores(row)
    weights = {
        "projection": 0.26,
        "recent_form": 0.18,
        "season_history": 0.13,
        "clv": 0.13,
        "roi": 0.10,
        "market_value": 0.14,
        "sample_strength": 0.06,
    }
    raw = sum(components[key] * weights[key] for key in weights)
    evidence_count = sum(available[key] for key in ("projection", "recent_form", "season_history", "clv", "roi", "market_value"))
    score = clamp(raw - max(0, 2 - evidence_count) * 8)
    confidence = "HIGH" if score >= 82 and components["sample_strength"] >= 55 and evidence_count >= 4 else "MODERATE" if score >= 68 and evidence_count >= 2 else "LOW"
    side = str(row.get("side") or "PASS").upper()
    missing = [key for key, present in available.items() if key != "sample_strength" and not present]
    return {
        "target_date": row.get("target_date"),
        "player": row.get("player"),
        "team": row.get("team"),
        "game": row.get("game"),
        "market": row.get("stat") or row.get("market"),
        "side": side,
        "line": num(row.get("line")),
        "sportsbook": row.get("sportsbook"),
        "odds": num(row.get("odds")),
        "projection": num(row.get("projection")),
        "projection_source_field": row.get("projection_source_field"),
        "projection_validated": True,
        "projection_ceiling": row.get("projection_ceiling"),
        "model_probability": round(model_prob, 4) if model_prob is not None else None,
        "edge_score": round(score, 2),
        "confidence": confidence,
        "components": components,
        "evidence_available": available,
        "evidence_count": evidence_count,
        "missing_evidence": missing,
        "evidence": reasons[:7],
        "market_type": row.get("market_type", "standard"),
        "source": row.get("source") or "sprint19_m02_predictions",
    }


def score_band(score: float) -> str:
    if score >= 82:
        return "82-100"
    if score >= 75:
        return "75-81.99"
    if score >= 68:
        return "68-74.99"
    if score >= 60:
        return "60-67.99"
    return "below-60"


def build(target: str) -> dict[str, Any]:
    source_rows, source = source_candidates(target)
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row, source_kind in source_rows:
        candidate, rejection = canonical_candidate(row, target, source_kind)
        if candidate is not None:
            candidates.append(candidate)
        elif rejection is not None:
            rejected.append(rejection)

    scored = [score_row(row) for row in candidates]
    unique: dict[tuple[str, str, str, float, str], dict[str, Any]] = {}
    for row in scored:
        key = (norm(row.get("player")), norm(row.get("market")), row.get("side", ""), float(row.get("line")), norm(row.get("sportsbook")))
        if key not in unique or row["edge_score"] > unique[key]["edge_score"]:
            unique[key] = row
    scored = sorted(unique.values(), key=lambda row: (row["edge_score"], row["components"]["sample_strength"]), reverse=True)

    if source["state"] != "ready":
        status = source["state"]
    elif source["empty_slate"]:
        status = "confirmed_empty_slate"
    elif scored:
        status = "ok"
    else:
        status = "invalid"

    band_counts = Counter(score_band(row["edge_score"]) for row in scored)
    confidence_counts = Counter(row["confidence"] for row in scored)
    type_counts = Counter(row["market_type"] for row in scored)
    coverage = {key: sum(bool(row["evidence_available"].get(key)) for row in scored) for key in ("projection", "recent_form", "season_history", "clv", "roi", "market_value")}
    missing_counts = Counter(item for row in scored for item in row["missing_evidence"])
    component_averages = {
        key: round(sum(row["components"][key] for row in scored) / len(scored), 2) if scored else None
        for key in ("projection", "recent_form", "season_history", "clv", "roi", "market_value", "sample_strength")
    }

    report = {
        "sprint": 6,
        "phase": "6.1-edge-qa-dashboard",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": status,
        "source_contract": source,
        "summary": {
            "source_props": source["standard_rows"],
            "source_alt_markets": source["alt_rows"],
            "candidates_loaded": len(source_rows),
            "candidates_scored": len(scored),
            "invalid_projection_rows_rejected": len(rejected),
            "high_confidence": confidence_counts.get("HIGH", 0),
            "moderate_confidence": confidence_counts.get("MODERATE", 0),
            "low_confidence": confidence_counts.get("LOW", 0),
            "top_score": scored[0]["edge_score"] if scored else None,
            "standard_candidates": type_counts.get("standard", 0),
            "alternate_candidates": type_counts.get("alternate", 0),
        },
        "qa": {
            "score_distribution": dict(band_counts),
            "confidence_distribution": dict(confidence_counts),
            "market_type_distribution": dict(type_counts),
            "evidence_coverage_counts": coverage,
            "evidence_coverage_rates": {key: round(value / len(scored), 4) if scored else 0 for key, value in coverage.items()},
            "missing_evidence_counts": dict(missing_counts),
            "component_averages": component_averages,
            "projection_integrity": {
                "contract": "wnba_projection_contract.py",
                "invalid_rows_rejected": len(rejected),
                "rejection_sample": rejected[:20],
                "all_published_projections_validated": all(row.get("projection_validated") is True for row in scored),
            },
            "high_confidence_gate": "score >= 82, sample_strength >= 55, and at least four non-neutral evidence components",
        },
        "top_edges": scored[:100],
        "methodology": {
            "transparent_components": True,
            "weights": {
                "projection": 0.26,
                "recent_form": 0.18,
                "season_history": 0.13,
                "clv": 0.13,
                "roi": 0.10,
                "market_value": 0.14,
                "sample_strength": 0.06,
            },
            "canonical_standard_source": str(M02),
            "legacy_master_props_used": False,
            "invalid_projection_policy": "quarantine; never score, simulate, or rank",
            "warning": "Edge scores rank evidence; they do not guarantee profit. Calibration is required before high-conviction use.",
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print(json.dumps({"status": status, "summary": report["summary"], "source_contract": source}, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
