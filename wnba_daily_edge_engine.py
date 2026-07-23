from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

DASH = Path("data/dashboard")
WARE = Path("data/warehouse")
OUTS = [DASH / "wnba_daily_edges.json", WARE / "wnba_daily_edges.json"]


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
        vals: list[float] = []
        for item in raw:
            if isinstance(item, dict):
                value = num(item.get("value") or item.get("stat_value") or item.get(str(row.get("stat") or "").lower()))
            else:
                value = num(item)
            if value is not None:
                vals.append(value)
        if vals:
            return vals[:10]
    return []


def is_hit(value: float, line: float, side: str) -> bool:
    return value < line if side == "UNDER" else value > line


def component_scores(row: dict[str, Any]) -> tuple[dict[str, float], list[str], dict[str, bool]]:
    line = num(row.get("line") or row.get("consensus_line") or row.get("threshold"))
    projection = num(row.get("projection") or row.get("pred") or row.get("projected_value"))
    side = str(row.get("signal") or row.get("side") or "OVER").upper()
    odds = row.get("best_over_price") if side == "OVER" else row.get("best_under_price")
    odds = odds if odds not in (None, "") else row.get("odds") or row.get("price")
    values = history_values(row)
    available = {
        "projection": line is not None and projection is not None,
        "recent_form": line is not None and bool(values),
        "season_history": False,
        "clv": False,
        "roi": False,
        "market_value": False,
        "sample_strength": bool(values) or num(row.get("season_games") or row.get("sample_size")) is not None,
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
    l5_rate = sum(is_hit(v, line, side) for v in l5) / len(l5) if line is not None and l5 else None
    l10_rate = sum(is_hit(v, line, side) for v in l10) / len(l10) if line is not None and l10 else None
    trend_score = 50.0
    if l5_rate is not None or l10_rate is not None:
        blended = ((l5_rate if l5_rate is not None else 0.5) * 0.6) + ((l10_rate if l10_rate is not None else 0.5) * 0.4)
        trend_score = clamp(blended * 100)
        reasons.append(f"Recent hit rate L5 {round((l5_rate or 0)*100)}%, L10 {round((l10_rate or 0)*100)}%")

    season_rate = num(row.get("season_pct") or row.get("season_hit_rate") or row.get("historical_probability"))
    available["season_history"] = season_rate is not None
    season_score = clamp((season_rate if season_rate is not None else 0.5) * 100)
    if season_rate is not None:
        reasons.append(f"Season/historical hit rate {season_rate:.1%}")

    clv = num(row.get("avg_clv") or row.get("clv") or row.get("closing_line_value"))
    available["clv"] = clv is not None
    clv_score = 50.0 if clv is None else clamp(50 + clv * 12)
    if clv is not None:
        reasons.append(f"Historical CLV {clv:+.2f}")

    roi = num(row.get("roi") or row.get("historical_roi"))
    available["roi"] = roi is not None
    roi_score = 50.0 if roi is None else clamp(50 + roi * (100 if abs(roi) <= 2 else 1))
    if roi is not None:
        reasons.append(f"Historical ROI {roi:.1%}" if abs(roi) <= 2 else f"Historical ROI {roi:+.1f}")

    market_prob = implied_probability(odds)
    model_prob = None
    if available["projection"] or available["recent_form"] or available["season_history"]:
        model_prob = clamp((projection_score * 0.45 + trend_score * 0.35 + season_score * 0.20) / 100, 0.01, 0.99)
    value_score = 50.0
    if market_prob is not None and model_prob is not None:
        probability_edge = model_prob - market_prob
        value_score = clamp(50 + probability_edge * 220)
        available["market_value"] = True
        reasons.append(f"Model probability edge {probability_edge:+.1%}")

    sample = max(len(l10), int(num(row.get("season_games") or row.get("sample_size")) or 0))
    sample_score = clamp(20 + math.sqrt(sample) * 12) if sample else 20.0

    return {
        "projection": round(projection_score, 2),
        "recent_form": round(trend_score, 2),
        "season_history": round(season_score, 2),
        "clv": round(clv_score, 2),
        "roi": round(roi_score, 2),
        "market_value": round(value_score, 2),
        "sample_strength": round(sample_score, 2),
    }, reasons, available


def score_row(row: dict[str, Any]) -> dict[str, Any]:
    components, reasons, available = component_scores(row)
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
    side = str(row.get("signal") or row.get("side") or "OVER").upper()
    missing = [key for key, present in available.items() if key != "sample_strength" and not present]
    return {
        "player": row.get("player"),
        "team": row.get("team"),
        "game": row.get("game"),
        "market": row.get("stat") or row.get("market") or row.get("market_key"),
        "side": side,
        "line": num(row.get("line") or row.get("consensus_line") or row.get("threshold")),
        "sportsbook": row.get("best_book") or row.get("book") or row.get("sportsbook") or (row.get("best_over_book") if side == "OVER" else row.get("best_under_book")),
        "odds": row.get("odds") or row.get("price") or (row.get("best_over_price") if side == "OVER" else row.get("best_under_price")),
        "projection": num(row.get("projection") or row.get("pred") or row.get("projected_value")),
        "edge_score": round(score, 2),
        "confidence": confidence,
        "components": components,
        "evidence_available": available,
        "evidence_count": evidence_count,
        "missing_evidence": missing,
        "evidence": reasons[:7],
        "market_type": "alternate" if row.get("threshold") is not None or row.get("line_type") == "alternate" else "standard",
        "source": row.get("source") or "current_player_props",
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
    master = load(DASH / "wnba_master.json", {})
    props = list_rows(master, "props")
    alt = load(DASH / "wnba_alt_market_warehouse.json", {})
    alt_rows = list_rows(alt, "rows")
    candidates = props + alt_rows
    scored = [score_row(row) for row in candidates]
    scored = [row for row in scored if row.get("player") and row.get("market") and row.get("line") is not None]

    unique: dict[tuple[str, str, str, float, str], dict[str, Any]] = {}
    for row in scored:
        key = (norm(row.get("player")), norm(row.get("market")), row.get("side", ""), float(row.get("line")), norm(row.get("sportsbook")))
        if key not in unique or row["edge_score"] > unique[key]["edge_score"]:
            unique[key] = row
    scored = sorted(unique.values(), key=lambda r: (r["edge_score"], r["components"]["sample_strength"]), reverse=True)

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
        "status": "ok" if scored else "empty",
        "summary": {
            "source_props": len(props),
            "source_alt_markets": len(alt_rows),
            "candidates_scored": len(scored),
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
            "high_confidence_gate": "score >= 82, sample_strength >= 55, and at least four non-neutral evidence components",
        },
        "top_edges": scored[:100],
        "methodology": {
            "transparent_components": True,
            "weights": weights if False else {
                "projection": 0.26,
                "recent_form": 0.18,
                "season_history": 0.13,
                "clv": 0.13,
                "roi": 0.10,
                "market_value": 0.14,
                "sample_strength": 0.06,
            },
            "warning": "Edge scores rank evidence; they do not guarantee profit. Calibration is required before high-conviction use.",
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print(json.dumps({"summary": report["summary"], "qa": report["qa"]}, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
