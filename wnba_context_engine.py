"""
wnba_context_engine.py
----------------------
WNBA-first context layer for improving prop projections.

This module does not call external APIs. It reads the existing predictions JSON,
derives minutes/usage/pace/matchup/blowout/rest context from fields already
available in the row, and writes a dashboard-ready context report.

Outputs:
  - Adds `wnba_context_engine` to predictions/predictions_YYYY-MM-DD.json
  - Adds per-prop `context_engine` and `context_score`
  - data/intelligence/wnba_context_engine_YYYY-MM-DD.json
  - data/dashboard/wnba_context_engine.json
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
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


def grade(score: float) -> str:
    if score >= 92:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 76:
        return "B+"
    if score >= 68:
        return "B"
    if score >= 58:
        return "C"
    return "D"


def safe_upper(v: Any) -> str:
    return str(v or "").upper().strip()


def minutes_engine(row: Dict[str, Any]) -> Dict[str, Any]:
    base = f(row.get("projected_minutes"), 0)
    l5_min = f(row.get("last5_minutes", row.get("minutes_l5", 0)))
    season_min = f(row.get("season_minutes", row.get("avg_minutes", 0)))
    starter = str(row.get("starter", row.get("role", ""))).lower() in {"starter", "start", "true", "yes"}
    injury = safe_upper(row.get("injury_status", "ACTIVE"))
    if base <= 0:
        base = l5_min or season_min or (30 if starter else 20)
    trend_adj = 0
    if l5_min and season_min:
        trend_adj = max(-4, min(4, (l5_min - season_min) * 0.45))
    role_adj = 2 if starter else -1 if row.get("role") else 0
    injury_adj = -18 if injury == "OUT" else -10 if injury == "DOUBTFUL" else -5 if injury in {"QUESTIONABLE", "GTD"} else -1 if injury == "PROBABLE" else 0
    blowout = f(row.get("blowout_probability", row.get("blowout_risk", 0)))
    if blowout > 1:
        blowout = blowout / 100
    blowout_adj = -4 * blowout
    projected = max(0, base + trend_adj + role_adj + injury_adj + blowout_adj)
    floor = max(0, projected - (6 if projected >= 28 else 4))
    ceiling = projected + (5 if projected >= 28 else 4)
    confidence = 70
    if base:
        confidence += 8
    if l5_min:
        confidence += 5
    if injury in {"QUESTIONABLE", "GTD", "DOUBTFUL", "OUT"}:
        confidence -= 25
    if blowout >= 0.25:
        confidence -= 8
    return {
        "projected": round(projected, 1),
        "floor": round(floor, 1),
        "ceiling": round(ceiling, 1),
        "confidence": round(clamp(confidence), 1),
        "trend_adjustment": round(trend_adj, 1),
        "role_adjustment": round(role_adj, 1),
        "injury_adjustment": round(injury_adj, 1),
        "blowout_adjustment": round(blowout_adj, 1),
    }


def usage_engine(row: Dict[str, Any]) -> Dict[str, Any]:
    usage = f(row.get("usage", row.get("usage_rate", 0)))
    l5_usage = f(row.get("last5_usage", row.get("usage_l5", 0)))
    if usage <= 0:
        stat = safe_upper(row.get("stat"))
        usage = 24 if stat in {"PTS", "PRA", "PA"} else 18
    trend = 0
    if l5_usage:
        trend = max(-5, min(5, (l5_usage - usage) * 0.5))
    injury_boost = f(row.get("teammate_usage_boost", row.get("injury_usage_boost", 0)))
    role_boost = f(row.get("role_usage_boost", 0))
    projected = usage + trend + injury_boost + role_boost
    confidence = 68 + (6 if l5_usage else 0) + (5 if injury_boost else 0)
    return {
        "projected_usage": round(projected, 1),
        "baseline_usage": round(usage, 1),
        "usage_change": round(projected - usage, 1),
        "confidence": round(clamp(confidence), 1),
        "injury_usage_boost": round(injury_boost, 1),
    }


def pace_engine(row: Dict[str, Any]) -> Dict[str, Any]:
    team_pace = f(row.get("team_pace", row.get("pace", 0)))
    opp_pace = f(row.get("opp_pace", 0))
    if team_pace <= 0 and opp_pace <= 0:
        expected = 80.0
        confidence = 54
    elif opp_pace <= 0:
        expected = team_pace
        confidence = 62
    elif team_pace <= 0:
        expected = opp_pace
        confidence = 62
    else:
        expected = (team_pace * 0.55) + (opp_pace * 0.45)
        confidence = 74
    rest = f(row.get("rest_days", 1))
    if rest >= 2:
        expected += 0.7
    elif rest <= 0:
        expected -= 1.2
    pace_adv = expected - 80
    return {"expected_possessions": round(expected, 1), "pace_advantage": round(pace_adv, 1), "confidence": round(clamp(confidence), 1)}


def matchup_engine(row: Dict[str, Any]) -> Dict[str, Any]:
    opp_rank = f(row.get("opp_rank", row.get("defense_rank", 8)), 8)
    # Higher rank is assumed easier in prior modules.
    score = 50 + (opp_rank - 6) * 5
    position_rank = f(row.get("position_defense_rank", 0))
    if position_rank:
        score = (score * 0.65) + ((50 + (position_rank - 6) * 5) * 0.35)
    stat = safe_upper(row.get("stat"))
    if stat in {"REB", "RA", "PR"} and f(row.get("opp_rebound_rank", 0)):
        score = (score * 0.7) + ((50 + (f(row.get("opp_rebound_rank")) - 6) * 5) * 0.3)
    if stat in {"AST", "PA", "RA"} and f(row.get("opp_ast_rank", 0)):
        score = (score * 0.7) + ((50 + (f(row.get("opp_ast_rank")) - 6) * 5) * 0.3)
    return {"matchup_score": round(clamp(score), 1), "grade": grade(clamp(score)), "opp_rank": opp_rank, "confidence": 65 if opp_rank else 45}


def rest_fatigue_engine(row: Dict[str, Any]) -> Dict[str, Any]:
    rest = f(row.get("rest_days", 1), 1)
    b2b = str(row.get("back_to_back", "")).lower() in {"true", "yes", "1"} or rest <= 0
    travel = f(row.get("travel_miles", 0))
    score = 72
    if rest >= 2:
        score += 10
    elif rest <= 0:
        score -= 18
    if travel >= 1000:
        score -= 8
    elif travel >= 500:
        score -= 4
    if b2b:
        score -= 8
    return {"rest_days": rest, "back_to_back": b2b, "travel_miles": travel, "fatigue_score": round(clamp(score), 1), "grade": grade(clamp(score))}


def blowout_engine(row: Dict[str, Any]) -> Dict[str, Any]:
    spread = abs(f(row.get("spread", row.get("game_spread", 0))))
    raw = f(row.get("blowout_probability", row.get("blowout_risk", 0)))
    if raw > 1:
        raw = raw / 100
    if raw <= 0:
        raw = min(0.45, spread / 28) if spread else 0.14
    risk_score = raw * 100
    impact = "HIGH" if risk_score >= 32 else "MED" if risk_score >= 20 else "LOW"
    return {"probability": round(risk_score, 1), "impact": impact, "rotation_risk": impact, "minutes_penalty": round(-4 * raw, 1)}


def context_for_prop(row: Dict[str, Any]) -> Dict[str, Any]:
    minutes = minutes_engine(row)
    usage = usage_engine(row)
    pace = pace_engine(row)
    matchup = matchup_engine(row)
    rest = rest_fatigue_engine(row)
    blowout = blowout_engine(row)
    injury = safe_upper(row.get("injury_status", "ACTIVE"))
    injury_score = 100
    if injury == "OUT":
        injury_score = 0
    elif injury == "DOUBTFUL":
        injury_score = 30
    elif injury in {"QUESTIONABLE", "GTD"}:
        injury_score = 58
    elif injury == "PROBABLE":
        injury_score = 82
    score = (
        minutes["confidence"] * 0.22
        + usage["confidence"] * 0.15
        + pace["confidence"] * 0.10
        + matchup["matchup_score"] * 0.18
        + rest["fatigue_score"] * 0.13
        + (100 - blowout["probability"]) * 0.12
        + injury_score * 0.10
    )
    notes: List[str] = []
    if minutes["injury_adjustment"] < 0:
        notes.append("Injury status reduces minutes confidence")
    if usage["usage_change"] >= 2:
        notes.append("Usage projects above baseline")
    if matchup["matchup_score"] >= 75:
        notes.append("Favorable defensive matchup")
    elif matchup["matchup_score"] <= 45:
        notes.append("Difficult defensive matchup")
    if blowout["impact"] == "HIGH":
        notes.append("Blowout risk may reduce fourth-quarter minutes")
    if rest["back_to_back"]:
        notes.append("Back-to-back fatigue risk")
    return {
        "context_score": round(clamp(score), 1),
        "context_grade": grade(clamp(score)),
        "minutes": minutes,
        "usage": usage,
        "pace": pace,
        "matchup": matchup,
        "rest_fatigue": rest,
        "blowout": blowout,
        "injury_status": injury or "ACTIVE",
        "notes": notes[:6],
    }


def build(data: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    props = data.get("props", []) or []
    enriched = []
    for p in props:
        row = dict(p)
        ctx = context_for_prop(row)
        row["context_engine"] = ctx
        row["context_score"] = ctx["context_score"]
        row["context_grade"] = ctx["context_grade"]
        # Lightly adjust existing UPS when context is extreme; do not overwrite original.
        if row.get("ups_score") is not None:
            adj = (ctx["context_score"] - 70) * 0.12
            row["context_adjusted_ups"] = round(clamp(f(row.get("ups_score")) + adj), 1)
        enriched.append(row)
    data["props"] = enriched

    top_context = sorted(enriched, key=lambda x: f(x.get("context_score")), reverse=True)[:15]
    weak_context = sorted(enriched, key=lambda x: f(x.get("context_score")))[:12]
    by_stat = defaultdict(list)
    by_game = defaultdict(list)
    for p in enriched:
        by_stat[safe_upper(p.get("stat")) or "UNKNOWN"].append(f(p.get("context_score")))
        by_game[str(p.get("game") or "Unknown")].append(f(p.get("context_score")))

    def avg(vals: List[float]) -> float:
        return round(sum(vals) / max(1, len(vals)), 1)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "summary": {
            "props_scored": len(enriched),
            "avg_context_score": avg([f(p.get("context_score")) for p in enriched]) if enriched else None,
            "high_context_count": len([p for p in enriched if f(p.get("context_score")) >= 80]),
            "low_context_count": len([p for p in enriched if f(p.get("context_score")) < 60]),
        },
        "top_context": [slim(p) for p in top_context],
        "weak_context": [slim(p) for p in weak_context],
        "stat_context": [{"stat": k, "avg_context_score": avg(v), "count": len(v)} for k, v in sorted(by_stat.items())],
        "game_context": [{"game": k, "avg_context_score": avg(v), "count": len(v)} for k, v in sorted(by_game.items(), key=lambda kv: avg(kv[1]), reverse=True)],
    }
    data["wnba_context_engine"] = report
    return report


def slim(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "player": p.get("player"),
        "team": p.get("team"),
        "game": p.get("game"),
        "stat": p.get("stat"),
        "line": p.get("line"),
        "signal": p.get("signal"),
        "pred": p.get("pred"),
        "context_score": p.get("context_score"),
        "context_grade": p.get("context_grade"),
        "context_adjusted_ups": p.get("context_adjusted_ups"),
        "ups_score": p.get("ups_score"),
        "notes": (p.get("context_engine") or {}).get("notes", []),
        "minutes": (p.get("context_engine") or {}).get("minutes", {}),
        "usage": (p.get("context_engine") or {}).get("usage", {}),
        "matchup": (p.get("context_engine") or {}).get("matchup", {}),
        "blowout": (p.get("context_engine") or {}).get("blowout", {}),
    }


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
    with open(os.path.join(OUT_INTEL, f"wnba_context_engine_{args.date}.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(OUT_DASH, "wnba_context_engine.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"✅ WNBA Context Engine built: {report['summary']['props_scored']} props scored")


if __name__ == "__main__":
    main()
