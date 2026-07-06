"""
projection_intelligence_v2.py
-----------------------------
WNBA Projection Intelligence v2.

Goal: turn raw projections into richer probability-style projection bands using
existing model output plus the WNBA Context Engine. No external API calls.

Outputs:
  - Adds `projection_intelligence_v2` to predictions/predictions_YYYY-MM-DD.json
  - Adds per-prop `projection_intelligence_v2`
  - data/intelligence/projection_intelligence_v2_YYYY-MM-DD.json
  - data/dashboard/projection_intelligence_v2.json
"""

from __future__ import annotations

import argparse
import json
import math
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


def stat_sigma(stat: str, line: float) -> float:
    stat = norm_stat(stat)
    base = {
        "PTS": 5.2, "REB": 2.6, "AST": 2.3, "3PM": 1.15,
        "PRA": 7.2, "PR": 6.0, "PA": 5.7, "RA": 4.0,
        "STL": 1.0, "BLK": 1.0
    }.get(stat, 3.5)
    if line:
        base = max(base * 0.75, min(base * 1.35, line * 0.28))
    return max(0.7, base)


def normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def volatility_bucket(sd: float, line: float, context_score: float) -> str:
    rel = sd / max(1, abs(line))
    if context_score < 58 or rel > 0.45:
        return "High"
    if context_score < 72 or rel > 0.30:
        return "Medium"
    return "Low"


def projected_line_adjustment(row: Dict[str, Any]) -> float:
    ctx = row.get("context_engine") or {}
    context_score = f(row.get("context_score", ctx.get("context_score", 70)), 70)
    pace = ctx.get("pace", {}) if isinstance(ctx, dict) else {}
    usage = ctx.get("usage", {}) if isinstance(ctx, dict) else {}
    matchup = ctx.get("matchup", {}) if isinstance(ctx, dict) else {}
    minutes = ctx.get("minutes", {}) if isinstance(ctx, dict) else {}
    blowout = ctx.get("blowout", {}) if isinstance(ctx, dict) else {}
    stat = norm_stat(row.get("stat"))
    adj = 0.0
    adj += (context_score - 70) * 0.025
    adj += f(pace.get("pace_advantage")) * (0.12 if stat in {"PTS", "PRA", "PR", "PA"} else 0.07)
    adj += f(usage.get("usage_change")) * (0.16 if stat in {"PTS", "PRA", "PA"} else 0.08)
    adj += (f(matchup.get("matchup_score"), 50) - 50) * 0.018
    adj += f(minutes.get("trend_adjustment")) * 0.09
    adj += f(blowout.get("minutes_penalty")) * 0.10
    return adj


def intelligence_for_prop(row: Dict[str, Any]) -> Dict[str, Any]:
    pred = f(row.get("pred", row.get("projection", 0)))
    line = f(row.get("line"))
    stat = norm_stat(row.get("stat"))
    ctx = row.get("context_engine") or {}
    context_score = f(row.get("context_score", ctx.get("context_score", 70)), 70) if isinstance(ctx, dict) else f(row.get("context_score"), 70)
    if pred <= 0:
        pred = line or 0
    adj = projected_line_adjustment(row)
    median = max(0, pred + adj)
    sd = stat_sigma(stat, line or median)
    # Context confidence tightens distribution; poor context widens it.
    sd *= 1 + max(-0.18, min(0.35, (70 - context_score) / 100))
    floor = max(0, median - 1.15 * sd)
    ceiling = median + 1.55 * sd
    p_over = normal_cdf((median - line) / sd) if line else None
    signal = str(row.get("signal") or row.get("recommendation") or "").upper()
    hit_prob = None
    if p_over is not None:
        if signal == "OVER":
            hit_prob = p_over
        elif signal == "UNDER":
            hit_prob = 1 - p_over
        else:
            hit_prob = max(p_over, 1 - p_over)
    edge = median - line if line else f(row.get("edge"))
    quality = clamp(50 + abs(edge) * 8 + (context_score - 70) * 0.35 + (f(row.get("ups_score"), 70) - 70) * 0.22)
    vol = volatility_bucket(sd, line or median, context_score)
    if vol == "High": quality -= 8
    elif vol == "Low": quality += 4
    quality = clamp(quality)
    return {
        "median": round(median, 2),
        "mean": round((median + pred) / 2, 2),
        "floor": round(floor, 2),
        "ceiling": round(ceiling, 2),
        "standard_deviation": round(sd, 2),
        "line": line,
        "edge_to_line": round(edge, 2),
        "prob_over": round(p_over * 100, 1) if p_over is not None else None,
        "hit_probability": round(hit_prob * 100, 1) if hit_prob is not None else None,
        "volatility": vol,
        "projection_quality": round(quality, 1),
        "projection_grade": grade(quality),
        "context_score": round(context_score, 1),
        "context_adjustment": round(adj, 2),
        "recommended_side": "OVER" if p_over is not None and p_over >= 0.54 else "UNDER" if p_over is not None and p_over <= 0.46 else "NO EDGE",
        "notes": notes(row, quality, vol, edge, context_score),
    }


def notes(row: Dict[str, Any], quality: float, vol: str, edge: float, context_score: float) -> List[str]:
    out = []
    if quality >= 85: out.append("Strong projection quality")
    if abs(edge) >= 2: out.append("Meaningful edge versus line")
    elif abs(edge) < 0.6: out.append("Thin edge versus line")
    if context_score >= 80: out.append("Strong game context")
    if context_score < 60: out.append("Weak context; reduce trust")
    if vol == "High": out.append("High volatility projection")
    ctx = row.get("context_engine") or {}
    if isinstance(ctx, dict):
        for n in ctx.get("notes", [])[:2]:
            if n not in out: out.append(n)
    return out[:6]


def slim(row: Dict[str, Any]) -> Dict[str, Any]:
    pi = row.get("projection_intelligence_v2") or {}
    return {
        "player": row.get("player"), "team": row.get("team"), "game": row.get("game"),
        "stat": row.get("stat"), "signal": row.get("signal"), "sportsbook": row.get("best_book_title") or row.get("best_book"),
        "line": row.get("line"), "original_projection": row.get("pred"),
        **pi
    }


def build(data: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    props = data.get("props", []) or []
    enriched = []
    for p in props:
        r = dict(p)
        pi = intelligence_for_prop(r)
        r["projection_intelligence_v2"] = pi
        r["projection_quality"] = pi["projection_quality"]
        r["projection_grade"] = pi["projection_grade"]
        r["hit_probability_v2"] = pi["hit_probability"]
        r["median_projection_v2"] = pi["median"]
        r["floor_projection_v2"] = pi["floor"]
        r["ceiling_projection_v2"] = pi["ceiling"]
        enriched.append(r)
    data["props"] = enriched
    top = sorted(enriched, key=lambda x: (f((x.get("projection_intelligence_v2") or {}).get("projection_quality")), f((x.get("projection_intelligence_v2") or {}).get("hit_probability"))), reverse=True)[:20]
    low = sorted(enriched, key=lambda x: f((x.get("projection_intelligence_v2") or {}).get("projection_quality")))[:12]
    by_stat = defaultdict(list)
    for r in enriched:
        by_stat[norm_stat(r.get("stat"))].append(r)
    stat_summary = []
    for stat, rows in by_stat.items():
        stat_summary.append({
            "stat": stat,
            "count": len(rows),
            "avg_quality": round(sum(f((r.get("projection_intelligence_v2") or {}).get("projection_quality")) for r in rows)/len(rows),1),
            "avg_hit_probability": round(sum(f((r.get("projection_intelligence_v2") or {}).get("hit_probability")) for r in rows)/len(rows),1),
        })
    stat_summary.sort(key=lambda x: x["avg_quality"], reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "summary": {
            "props_scored": len(enriched),
            "avg_projection_quality": round(sum(f((r.get("projection_intelligence_v2") or {}).get("projection_quality")) for r in enriched)/max(1,len(enriched)),1) if enriched else None,
            "a_grade_count": len([r for r in enriched if str(r.get("projection_grade","")).startswith("A")]),
            "high_hit_probability_count": len([r for r in enriched if f(r.get("hit_probability_v2")) >= 60]),
            "high_volatility_count": len([r for r in enriched if (r.get("projection_intelligence_v2") or {}).get("volatility") == "High"]),
        },
        "top_projection_quality": [slim(r) for r in top],
        "projection_risk_watch": [slim(r) for r in low],
        "stat_summary": stat_summary,
    }
    data["projection_intelligence_v2"] = report
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
    with open(os.path.join(OUT_INTEL, f"projection_intelligence_v2_{args.date}.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(OUT_DASH, "projection_intelligence_v2.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"✅ Projection Intelligence v2 built: {report['summary']['props_scored']} props scored")


if __name__ == "__main__":
    main()
