from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from wnba_projection_contract import canonical_stat, projection_ceiling, validate_projection

DASH = Path("data/dashboard")
WARE = Path("data/warehouse")
EDGES = DASH / "wnba_daily_edges.json"
OUTS = [DASH / "wnba_ensemble_intelligence.json", WARE / "wnba_ensemble_intelligence.json"]
BAD_SOURCE_STATUSES = {"error", "failed", "failure", "fetch_failed", "invalid", "missing", "stale", "standby", "unavailable"}

WEIGHTS = {
    "projection": 0.25,
    "recent_form": 0.16,
    "season_history": 0.11,
    "market_value": 0.16,
    "clv": 0.14,
    "roi": 0.09,
    "sample_strength": 0.09,
}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def value_or(value: Any, default: float) -> float:
    parsed = num(value)
    return parsed if parsed is not None else default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def grade(score: float, evidence_count: int) -> tuple[str, str]:
    if score >= 90 and evidence_count >= 5:
        return "A+", "ELITE"
    if score >= 84 and evidence_count >= 4:
        return "A", "VERY_HIGH"
    if score >= 77 and evidence_count >= 4:
        return "B+", "HIGH"
    if score >= 68 and evidence_count >= 3:
        return "B", "MODERATE"
    if score >= 58:
        return "C", "LEAN"
    return "D", "PASS"


def score_candidate(row: dict[str, Any], target: str) -> dict[str, Any]:
    comps = row.get("components") if isinstance(row.get("components"), dict) else {}
    component_values = {
        "projection": value_or(comps.get("projection"), 50.0),
        "recent_form": value_or(comps.get("recent_form"), 50.0),
        "season_history": value_or(comps.get("season_history"), 50.0),
        "market_value": value_or(comps.get("market_value"), 50.0),
        "clv": value_or(comps.get("clv"), 50.0),
        "roi": value_or(comps.get("roi"), 50.0),
        "sample_strength": value_or(comps.get("sample_strength"), 20.0),
    }
    available = row.get("evidence_available") if isinstance(row.get("evidence_available"), dict) else {}
    evidence_count = sum(
        bool(available.get(key, component_values[key] != 50.0))
        for key in ("projection", "recent_form", "season_history", "market_value", "clv", "roi")
    )
    raw = sum(component_values[key] * WEIGHTS[key] for key in WEIGHTS)
    score = clamp(raw - max(0, 4 - evidence_count) * 3.5)
    letter, confidence = grade(score, evidence_count)
    stat = canonical_stat(row.get("market") or row.get("stat"))
    projection, _ = validate_projection(stat, row.get("projection"))
    breakdown = {
        key: {
            "score": round(component_values[key], 2),
            "weight": WEIGHTS[key],
            "contribution": round(component_values[key] * WEIGHTS[key], 2),
        }
        for key in WEIGHTS
    }
    return {
        "target_date": target,
        "player": row.get("player"),
        "team": row.get("team"),
        "game": row.get("game"),
        "market": stat,
        "side": row.get("side"),
        "line": row.get("line"),
        "sportsbook": row.get("sportsbook"),
        "odds": row.get("odds"),
        "projection": projection,
        "projection_source_field": row.get("projection_source_field") or "projection",
        "projection_validated": True,
        "projection_ceiling": projection_ceiling(stat),
        "market_type": row.get("market_type", "standard"),
        "model_probability": row.get("model_probability"),
        "ensemble_score": round(score, 2),
        "grade": letter,
        "ensemble_confidence": confidence,
        "evidence_count": evidence_count,
        "component_breakdown": breakdown,
        "reasons": list(row.get("evidence") or [])[:6],
        "source_edge_score": row.get("edge_score"),
        "source_confidence": row.get("confidence"),
    }


def build(target: str | None = None) -> dict[str, Any]:
    edges = load(EDGES, {})
    source_target = str(edges.get("target_date") or "")[:10] if isinstance(edges, dict) else ""
    requested_target = target or source_target or str(date.today())
    source_status = str(edges.get("status") or "missing").strip().lower() if isinstance(edges, dict) else "missing"
    rows = edges.get("top_edges", []) if isinstance(edges, dict) else []
    rows = [row for row in rows if isinstance(row, dict)]

    source_state = "ready"
    source_reason = None
    if source_target != requested_target:
        source_state = "stale"
        source_reason = f"daily_edges_target_mismatch:{source_target or 'missing'}!={requested_target}"
    elif source_status in BAD_SOURCE_STATUSES:
        source_state = source_status if source_status in {"stale", "invalid"} else "stale"
        source_reason = f"daily_edges_status:{source_status}"
    elif source_status == "confirmed_empty_slate":
        source_state = "confirmed_empty_slate"
    elif source_status != "ok":
        source_state = "invalid"
        source_reason = f"daily_edges_unrecognized_status:{source_status}"

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if source_state == "ready":
        for row in rows:
            stat = canonical_stat(row.get("market") or row.get("stat"))
            projection, reason = validate_projection(stat, row.get("projection"))
            row_target = str(row.get("target_date") or source_target)[:10]
            if row_target != requested_target:
                rejected.append({"player": row.get("player"), "stat": stat, "value": row.get("projection"), "reason": "off_target_row"})
            elif projection is None:
                rejected.append({"player": row.get("player"), "stat": stat, "value": row.get("projection"), "reason": reason})
            else:
                accepted.append({**row, "market": stat, "projection": projection})

    scored = [score_candidate(row, requested_target) for row in accepted]
    scored.sort(key=lambda row: (row["ensemble_score"], row["evidence_count"]), reverse=True)
    if source_state == "confirmed_empty_slate":
        status = "confirmed_empty_slate"
    elif source_state != "ready":
        status = source_state
    elif scored:
        status = "ok"
    else:
        status = "invalid"

    report = {
        "sprint": 9,
        "phase": "ensemble-intelligence-engine",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": requested_target,
        "status": status,
        "source_contract": {
            "source": str(EDGES),
            "source_target_date": source_target or None,
            "source_status": source_status,
            "state": source_state,
            "reason": source_reason,
        },
        "summary": {
            "candidates_loaded": len(rows),
            "candidates_ranked": len(scored),
            "invalid_projection_rows_rejected": len(rejected),
            "a_plus": sum(row["grade"] == "A+" for row in scored),
            "a": sum(row["grade"] == "A" for row in scored),
            "b_plus": sum(row["grade"] == "B+" for row in scored),
            "high_or_better": sum(row["ensemble_confidence"] in {"ELITE", "VERY_HIGH", "HIGH"} for row in scored),
            "top_score": scored[0]["ensemble_score"] if scored else None,
        },
        "qa": {
            "projection_integrity": {
                "contract": "wnba_projection_contract.py",
                "invalid_rows_rejected": len(rejected),
                "rejection_sample": rejected[:20],
                "all_published_projections_validated": all(row.get("projection_validated") is True for row in scored),
            }
        },
        "top_10": scored[:10],
        "elite_plays": [row for row in scored if row["grade"] == "A+"][:20],
        "ranked_edges": scored[:100],
        "methodology": {
            "weights": WEIGHTS,
            "explainable": True,
            "calibration_aware": False,
            "historical_reconstruction_used": False,
            "legacy_master_props_used": False,
            "invalid_projection_policy": "quarantine; never rank",
            "warning": "Ensemble grades rank agreement across current model evidence. They are not guarantees and remain subject to forward validation.",
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print(json.dumps({"status": status, "summary": report["summary"], "source_contract": report["source_contract"]}, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    args = parser.parse_args()
    build(args.date or None)


if __name__ == "__main__":
    main()
