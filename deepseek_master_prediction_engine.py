"""
deepseek_master_prediction_engine.py
------------------------------------
Safe integration of DeepSeek's Master Prediction Engine and Ensemble Engine ideas.

This does NOT replace daily_runner.py, postprocess_predictions.py, or any current
production prediction logic. It reads the existing daily predictions file and
creates an independent master-decision JSON for comparison.

Outputs:
  - data/dashboard/deepseek_master_predictions.json
  - data/intelligence/deepseek_master_predictions_YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List

PRED_DIR = "predictions"
OUT_DASH = "data/dashboard"
OUT_INTEL = "data/intelligence"


def f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return default
        return float(v)
    except Exception:
        return default


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def norm_stat(v: Any) -> str:
    raw = str(v or "").upper().replace(" ", "")
    return {
        "POINTS": "PTS", "REBOUNDS": "REB", "ASSISTS": "AST",
        "THREES": "3PM", "3PTM": "3PM", "FG3M": "3PM",
        "PTS+REB+AST": "PRA", "PTS+REB": "PR", "PTS+AST": "PA", "REB+AST": "RA",
    }.get(raw, raw)


def action(row: Dict[str, Any]) -> str:
    da = row.get("daily_action_v2") or {}
    mt = row.get("market_timing_intelligence") or {}
    return str(
        da.get("final_action")
        or mt.get("timing_action")
        or row.get("final_action")
        or row.get("timing_action")
        or row.get("decision")
        or row.get("action")
        or ""
    ).upper()


def base_score(row: Dict[str, Any]) -> float:
    da = row.get("daily_action_v2") or {}
    pi = row.get("projection_intelligence_v2") or {}
    mt = row.get("market_timing_intelligence") or {}
    mu = row.get("minutes_usage_intelligence") or {}
    muq = mu.get("quality", {}) if isinstance(mu, dict) else {}
    vals = [
        f(da.get("final_score"), 0),
        f(row.get("ups_score"), 0),
        f(pi.get("projection_quality"), 0),
        f(row.get("context_score"), 0),
        f(muq.get("minutes_usage_score"), f(row.get("minutes_usage_score"), 0)),
        f(mt.get("timing_confidence"), f(row.get("timing_confidence"), 0)),
        f(row.get("confidence_v2", row.get("score", 0)), 0),
    ]
    vals = [v for v in vals if v > 0]
    return round(sum(vals) / max(1, len(vals)), 1)


def projection_agent(row: Dict[str, Any]) -> Dict[str, Any]:
    pi = row.get("projection_intelligence_v2") or {}
    score = f(pi.get("projection_quality"), f(row.get("projection_quality"), base_score(row)))
    edge = f(pi.get("edge_to_line"), f(row.get("pred")) - f(row.get("line")))
    return {"agent": "projection", "score": clamp(score + min(8, max(-8, edge * 2))), "reason": "projection quality and edge"}


def market_agent(row: Dict[str, Any]) -> Dict[str, Any]:
    mt = row.get("market_timing_intelligence") or {}
    clv = f(mt.get("expected_clv"), f(row.get("expected_clv_v2"), 0))
    timing = str(mt.get("timing_action", "")).upper()
    score = f(mt.get("timing_confidence"), 65) + max(-12, min(12, clv * 5))
    if timing in {"BET NOW", "BET SOON"}:
        score += 6
    elif timing in {"PASS", "WAIT FOR NEWS"}:
        score -= 8
    return {"agent": "market", "score": clamp(score), "reason": "timing, CLV, and book signal"}


def role_agent(row: Dict[str, Any]) -> Dict[str, Any]:
    mu = row.get("minutes_usage_intelligence") or {}
    q = mu.get("quality", {}) if isinstance(mu, dict) else {}
    r = mu.get("rotation_risk", {}) if isinstance(mu, dict) else {}
    score = f(q.get("minutes_usage_score"), f(row.get("minutes_usage_score"), 68))
    if str(r.get("rotation_risk_level", row.get("rotation_risk_level", ""))).upper() == "HIGH":
        score -= 12
    return {"agent": "role", "score": clamp(score), "reason": "minutes, usage, and rotation risk"}


def context_agent(row: Dict[str, Any]) -> Dict[str, Any]:
    score = f(row.get("context_score"), 68)
    ctx = row.get("context_engine") or {}
    if isinstance(ctx, dict):
        if ctx.get("injury_status") in {"QUESTIONABLE", "GTD", "DOUBTFUL"}:
            score -= 10
        if f((ctx.get("blowout") or {}).get("probability"), 0) >= 30:
            score -= 8
    return {"agent": "context", "score": clamp(score), "reason": "game context and risk"}


def risk_agent(row: Dict[str, Any]) -> Dict[str, Any]:
    pi = row.get("projection_intelligence_v2") or {}
    score = 72
    if str(pi.get("volatility", "")).upper() == "HIGH":
        score -= 15
    if str(row.get("rotation_risk_level", "")).upper() == "HIGH":
        score -= 15
    if action(row) in {"PASS", "AVOID"}:
        score -= 18
    return {"agent": "risk", "score": clamp(score), "reason": "volatility and downside filters"}


def ensemble(row: Dict[str, Any]) -> Dict[str, Any]:
    votes = [projection_agent(row), market_agent(row), role_agent(row), context_agent(row), risk_agent(row)]
    weights = {"projection": 0.28, "market": 0.22, "role": 0.18, "context": 0.17, "risk": 0.15}
    total = sum(v["score"] * weights.get(v["agent"], 0.1) for v in votes)
    agreement = 100 - (max(v["score"] for v in votes) - min(v["score"] for v in votes))
    total = clamp(total * 0.85 + agreement * 0.15)
    return {"score": round(total, 1), "agreement": round(clamp(agreement), 1), "votes": votes}


def rating(score: float) -> str:
    if score >= 86:
        return "ELITE"
    if score >= 78:
        return "STRONG"
    if score >= 70:
        return "PLAYABLE"
    if score >= 60:
        return "WATCH"
    return "PASS"


def recommendation(row: Dict[str, Any], ens: Dict[str, Any]) -> str:
    current = action(row)
    score = f(ens.get("score"), 0)
    if current in {"BET NOW", "BET SOON"} and score >= 74:
        return "APPROVE"
    if score >= 84:
        return "APPROVE"
    if score >= 72:
        return "CONSIDER"
    if score >= 62:
        return "WATCH"
    return "REJECT"


def slim(row: Dict[str, Any]) -> Dict[str, Any]:
    ens = ensemble(row)
    return {
        "player": row.get("player"),
        "team": row.get("team"),
        "game": row.get("game"),
        "stat": norm_stat(row.get("stat")),
        "signal": row.get("signal"),
        "line": row.get("line"),
        "odds": row.get("odds", row.get("price", row.get("best_odds"))),
        "sportsbook": row.get("best_book_title") or row.get("best_book") or row.get("sportsbook") or row.get("book"),
        "current_action": action(row),
        "master_score": ens["score"],
        "agent_agreement": ens["agreement"],
        "master_rating": rating(ens["score"]),
        "master_recommendation": recommendation(row, ens),
        "agent_votes": ens["votes"],
    }


def build(data: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    props = data.get("props", []) or []
    predictions = [slim(p) for p in props]
    predictions.sort(key=lambda x: x["master_score"], reverse=True)
    counts = Counter(p["master_recommendation"] for p in predictions)
    ratings = Counter(p["master_rating"] for p in predictions)
    by_stat = defaultdict(list)
    for p in predictions:
        by_stat[p["stat"]].append(p)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "source": "DeepSeek Master Prediction/Ensemble concept integrated safely by ChatGPT",
        "summary": {
            "props_reviewed": len(props),
            "approved": counts.get("APPROVE", 0),
            "consider": counts.get("CONSIDER", 0),
            "watch": counts.get("WATCH", 0),
            "reject": counts.get("REJECT", 0),
            "avg_master_score": round(sum(p["master_score"] for p in predictions) / max(1, len(predictions)), 1) if predictions else None,
        },
        "recommendation_counts": dict(counts),
        "rating_counts": dict(ratings),
        "top_master_predictions": predictions[:25],
        "stat_summary": [
            {"stat": stat, "count": len(rows), "avg_master_score": round(sum(r["master_score"] for r in rows) / max(1, len(rows)), 1)}
            for stat, rows in sorted(by_stat.items())
        ],
    }
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    pred_path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(pred_path):
        raise SystemExit(f"Missing predictions file: {pred_path}")
    with open(pred_path) as fobj:
        data = json.load(fobj)
    report = build(data, args.date)
    os.makedirs(OUT_DASH, exist_ok=True)
    os.makedirs(OUT_INTEL, exist_ok=True)
    with open(os.path.join(OUT_DASH, "deepseek_master_predictions.json"), "w") as fobj:
        json.dump(report, fobj, indent=2)
    with open(os.path.join(OUT_INTEL, f"deepseek_master_predictions_{args.date}.json"), "w") as fobj:
        json.dump(report, fobj, indent=2)
    print(f"✅ DeepSeek Master Prediction Engine built: {report['summary']['props_reviewed']} props reviewed")


if __name__ == "__main__":
    main()
