"""
minutes_usage_intelligence.py
-----------------------------
WNBA Minutes & Usage Intelligence.

Why this exists:
Most prop misses are caused by minutes/role/usage changes. This engine creates a
separate diagnostic layer focused only on minutes, usage, role stability,
teammate impact, and rotation risk. It consumes the existing predictions file and
context/projection intelligence fields when available. No API calls.

Outputs:
  - Adds `minutes_usage_intelligence` to predictions/predictions_YYYY-MM-DD.json
  - Adds per-prop `minutes_usage_intelligence`
  - data/intelligence/minutes_usage_intelligence_YYYY-MM-DD.json
  - data/dashboard/minutes_usage_intelligence.json
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List

PRED_DIR = "predictions"
OUT_INTEL = "data/intelligence"
OUT_DASH = "data/dashboard"


def f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return default
        return float(v)
    except Exception:
        return default


def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def norm_stat(v: Any) -> str:
    raw = str(v or "").upper().replace(" ", "")
    return {
        "POINTS": "PTS", "REBOUNDS": "REB", "ASSISTS": "AST", "THREES": "3PM",
        "3PTM": "3PM", "FG3M": "3PM", "PTS+REB+AST": "PRA", "PTS+REB": "PR",
        "PTS+AST": "PA", "REB+AST": "RA"
    }.get(raw, raw)


def grade(score: float) -> str:
    if score >= 92: return "A+"
    if score >= 85: return "A"
    if score >= 77: return "B+"
    if score >= 68: return "B"
    if score >= 58: return "C"
    return "D"


def role_bucket(minutes: float) -> str:
    if minutes >= 32: return "Core Starter"
    if minutes >= 26: return "Starter / Heavy Rotation"
    if minutes >= 20: return "Rotation"
    if minutes >= 12: return "Bench"
    return "Fringe"


def minutes_signal(row: Dict[str, Any]) -> Dict[str, Any]:
    ctx = row.get("context_engine") or {}
    ctx_min = ctx.get("minutes", {}) if isinstance(ctx, dict) else {}
    projected = f(ctx_min.get("projected"), f(row.get("projected_minutes"), f(row.get("avg_minutes"), 0)))
    floor = f(ctx_min.get("floor"), max(0, projected - 5))
    ceiling = f(ctx_min.get("ceiling"), projected + 5)
    conf = f(ctx_min.get("confidence"), 62 if projected else 40)
    trend_adj = f(ctx_min.get("trend_adjustment"))
    role_adj = f(ctx_min.get("role_adjustment"))
    injury_adj = f(ctx_min.get("injury_adjustment"))
    blowout_adj = f(ctx_min.get("blowout_adjustment"))
    range_width = max(0, ceiling - floor)
    stability = clamp(100 - range_width * 5 + conf * 0.15)
    if injury_adj < 0:
        stability -= 12
    if blowout_adj < -1:
        stability -= 8
    return {
        "projected_minutes": round(projected, 1),
        "floor_minutes": round(floor, 1),
        "ceiling_minutes": round(ceiling, 1),
        "minutes_confidence": round(clamp(conf), 1),
        "minutes_stability": round(clamp(stability), 1),
        "role_bucket": role_bucket(projected),
        "trend_adjustment": round(trend_adj, 1),
        "role_adjustment": round(role_adj, 1),
        "injury_adjustment": round(injury_adj, 1),
        "blowout_adjustment": round(blowout_adj, 1),
        "minutes_range": round(range_width, 1),
    }


def usage_signal(row: Dict[str, Any]) -> Dict[str, Any]:
    ctx = row.get("context_engine") or {}
    usage_ctx = ctx.get("usage", {}) if isinstance(ctx, dict) else {}
    projected = f(usage_ctx.get("projected_usage"), f(row.get("usage_rate"), f(row.get("usage"), 0)))
    baseline = f(usage_ctx.get("baseline_usage"), projected)
    change = f(usage_ctx.get("usage_change"), projected - baseline)
    conf = f(usage_ctx.get("confidence"), 58 if projected else 42)
    stat = norm_stat(row.get("stat"))
    stat_sensitivity = {
        "PTS": 1.00, "PRA": 0.95, "PA": 0.90, "PR": 0.82,
        "AST": 0.78, "RA": 0.55, "REB": 0.45, "3PM": 0.88,
    }.get(stat, 0.65)
    usage_impact = change * stat_sensitivity
    stability = clamp(conf + 12 - abs(change) * 2.2)
    if abs(change) >= 4:
        stability -= 8
    return {
        "projected_usage": round(projected, 1),
        "baseline_usage": round(baseline, 1),
        "usage_change": round(change, 1),
        "usage_confidence": round(clamp(conf), 1),
        "usage_stability": round(clamp(stability), 1),
        "stat_sensitivity": round(stat_sensitivity, 2),
        "usage_impact": round(usage_impact, 2),
    }


def rotation_risk(row: Dict[str, Any], m: Dict[str, Any], u: Dict[str, Any]) -> Dict[str, Any]:
    ctx = row.get("context_engine") or {}
    blowout = ctx.get("blowout", {}) if isinstance(ctx, dict) else {}
    rest = ctx.get("rest_fatigue", {}) if isinstance(ctx, dict) else {}
    injury = str((ctx.get("injury_status") if isinstance(ctx, dict) else row.get("injury_status")) or row.get("injury_status") or "ACTIVE").upper()
    risk = 18
    reasons: List[str] = []
    if m["minutes_range"] >= 10:
        risk += 18; reasons.append("wide minutes range")
    if m["projected_minutes"] < 20:
        risk += 10; reasons.append("non-core rotation role")
    if injury in {"QUESTIONABLE", "GTD"}:
        risk += 22; reasons.append("injury uncertainty")
    elif injury in {"DOUBTFUL", "OUT"}:
        risk += 45; reasons.append("player availability risk")
    if f(blowout.get("probability")) >= 30:
        risk += 18; reasons.append("high blowout risk")
    elif f(blowout.get("probability")) >= 20:
        risk += 9; reasons.append("moderate blowout risk")
    if rest.get("back_to_back"):
        risk += 10; reasons.append("back-to-back fatigue")
    if abs(u["usage_change"]) >= 4:
        risk += 9; reasons.append("large usage change")
    level = "HIGH" if risk >= 65 else "MED" if risk >= 38 else "LOW"
    return {"rotation_risk_score": round(clamp(risk), 1), "rotation_risk_level": level, "risk_reasons": reasons[:5]}


def quality(row: Dict[str, Any], m: Dict[str, Any], u: Dict[str, Any], r: Dict[str, Any]) -> Dict[str, Any]:
    ctx_score = f(row.get("context_score"), 70)
    pi = row.get("projection_intelligence_v2") or {}
    proj_quality = f(pi.get("projection_quality"), f(row.get("projection_quality"), 70))
    score = (
        m["minutes_confidence"] * 0.25
        + m["minutes_stability"] * 0.22
        + u["usage_confidence"] * 0.16
        + u["usage_stability"] * 0.14
        + ctx_score * 0.12
        + proj_quality * 0.11
        - r["rotation_risk_score"] * 0.22
    ) + 20
    score = clamp(score)
    action = "TRUST" if score >= 82 and r["rotation_risk_level"] == "LOW" else "USE" if score >= 70 else "WATCH" if score >= 58 else "REDUCE"
    notes = []
    if m["projected_minutes"] >= 30: notes.append("core minutes projection")
    if m["minutes_stability"] < 60: notes.append("minutes instability")
    if abs(u["usage_change"]) >= 3: notes.append("usage role changing")
    if r["rotation_risk_level"] == "HIGH": notes.append("high rotation risk")
    if score >= 82: notes.append("minutes/usage profile supports projection")
    return {"minutes_usage_score": round(score, 1), "minutes_usage_grade": grade(score), "recommendation": action, "notes": notes[:5]}


def analyze_prop(row: Dict[str, Any]) -> Dict[str, Any]:
    m = minutes_signal(row)
    u = usage_signal(row)
    r = rotation_risk(row, m, u)
    q = quality(row, m, u, r)
    return {"minutes": m, "usage": u, "rotation_risk": r, "quality": q}


def slim(row: Dict[str, Any]) -> Dict[str, Any]:
    mu = row.get("minutes_usage_intelligence") or {}
    q = mu.get("quality", {})
    m = mu.get("minutes", {})
    u = mu.get("usage", {})
    r = mu.get("rotation_risk", {})
    return {
        "player": row.get("player"), "team": row.get("team"), "game": row.get("game"),
        "stat": row.get("stat"), "signal": row.get("signal"), "line": row.get("line"),
        "pred": row.get("pred"), "minutes_usage_score": q.get("minutes_usage_score"),
        "minutes_usage_grade": q.get("minutes_usage_grade"), "recommendation": q.get("recommendation"),
        "projected_minutes": m.get("projected_minutes"), "minutes_range": m.get("minutes_range"),
        "role_bucket": m.get("role_bucket"), "projected_usage": u.get("projected_usage"),
        "usage_change": u.get("usage_change"), "rotation_risk_level": r.get("rotation_risk_level"),
        "risk_reasons": r.get("risk_reasons", []), "notes": q.get("notes", []),
    }


def build(data: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    props = data.get("props", []) or []
    enriched = []
    for p in props:
        r = dict(p)
        mu = analyze_prop(r)
        r["minutes_usage_intelligence"] = mu
        r["minutes_usage_score"] = mu["quality"]["minutes_usage_score"]
        r["minutes_usage_grade"] = mu["quality"]["minutes_usage_grade"]
        r["rotation_risk_level"] = mu["rotation_risk"]["rotation_risk_level"]
        enriched.append(r)
    data["props"] = enriched

    top = sorted(enriched, key=lambda x: f(x.get("minutes_usage_score")), reverse=True)[:20]
    risk = sorted(enriched, key=lambda x: f((x.get("minutes_usage_intelligence") or {}).get("rotation_risk", {}).get("rotation_risk_score")), reverse=True)[:15]
    by_player = defaultdict(list)
    by_stat = defaultdict(list)
    for r in enriched:
        by_player[str(r.get("player") or "Unknown")].append(r)
        by_stat[norm_stat(r.get("stat"))].append(r)

    def avg(rows: List[Dict[str, Any]], field: str) -> float:
        return round(sum(f(x.get(field)) for x in rows)/max(1,len(rows)), 1)

    player_summary = []
    for player, rows in by_player.items():
        player_summary.append({
            "player": player,
            "count": len(rows),
            "avg_minutes_usage_score": avg(rows, "minutes_usage_score"),
            "max_rotation_risk": max(f((x.get("minutes_usage_intelligence") or {}).get("rotation_risk", {}).get("rotation_risk_score")) for x in rows),
        })
    player_summary.sort(key=lambda x: x["avg_minutes_usage_score"], reverse=True)

    stat_summary = []
    for stat, rows in by_stat.items():
        stat_summary.append({"stat": stat, "count": len(rows), "avg_minutes_usage_score": avg(rows, "minutes_usage_score")})
    stat_summary.sort(key=lambda x: x["avg_minutes_usage_score"], reverse=True)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "summary": {
            "props_scored": len(enriched),
            "avg_minutes_usage_score": round(sum(f(x.get("minutes_usage_score")) for x in enriched)/max(1,len(enriched)),1) if enriched else None,
            "trust_count": len([x for x in enriched if (x.get("minutes_usage_intelligence") or {}).get("quality", {}).get("recommendation") == "TRUST"]),
            "reduce_count": len([x for x in enriched if (x.get("minutes_usage_intelligence") or {}).get("quality", {}).get("recommendation") == "REDUCE"]),
            "high_rotation_risk_count": len([x for x in enriched if x.get("rotation_risk_level") == "HIGH"]),
        },
        "top_minutes_usage": [slim(x) for x in top],
        "rotation_risk_watch": [slim(x) for x in risk],
        "player_summary": player_summary[:30],
        "stat_summary": stat_summary,
    }
    data["minutes_usage_intelligence"] = report
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Missing predictions file: {path}")
    with open(path) as fh:
        data = json.load(fh)
    report = build(data, args.date)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
    os.makedirs(OUT_INTEL, exist_ok=True)
    os.makedirs(OUT_DASH, exist_ok=True)
    with open(os.path.join(OUT_INTEL, f"minutes_usage_intelligence_{args.date}.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(OUT_DASH, "minutes_usage_intelligence.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"✅ Minutes & Usage Intelligence built: {report['summary']['props_scored']} props scored")


if __name__ == "__main__":
    main()
