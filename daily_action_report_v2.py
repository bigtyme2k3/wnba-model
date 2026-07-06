"""
daily_action_report_v2.py
-------------------------
One clean daily operating report for the WNBA dashboard.

Consumes existing prediction/enrichment fields when available:
- projection_intelligence_v2
- wnba_context_engine
- minutes_usage_intelligence
- market_timing_intelligence
- decision_center / autonomous fields

No external API calls. Writes lightweight dashboard JSON and attaches the report
back to the daily predictions file.

Outputs:
  - data/dashboard/daily_action_report_v2.json
  - data/intelligence/daily_action_report_v2_YYYY-MM-DD.json
  - predictions/predictions_YYYY-MM-DD.json -> daily_action_report_v2
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


def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def norm_stat(v: Any) -> str:
    raw = str(v or "").upper().replace(" ", "")
    return {"POINTS":"PTS","REBOUNDS":"REB","ASSISTS":"AST","THREES":"3PM","3PTM":"3PM","FG3M":"3PM","PTS+REB+AST":"PRA","PTS+REB":"PR","PTS+AST":"PA","REB+AST":"RA"}.get(raw, raw)


def book(row: Dict[str, Any]) -> str:
    return str(row.get("best_book_title") or row.get("best_book") or row.get("sportsbook") or row.get("book") or "Unknown")


def action(row: Dict[str, Any]) -> str:
    mt = row.get("market_timing_intelligence") or {}
    dec = str(row.get("decision", row.get("action", row.get("recommendation", "")))).upper()
    timing = str(mt.get("timing_action", row.get("timing_action", ""))).upper()
    if timing in {"BET NOW", "BET SOON"}:
        return timing
    if dec in {"BET", "PLAY"}:
        return "BET NOW" if timing != "WAIT FOR NEWS" else "WAIT FOR NEWS"
    if "WAIT" in timing:
        return timing
    if timing == "MONITOR":
        return "MONITOR"
    if dec in {"PASS", "AVOID"}:
        return dec
    score = final_score(row)
    if score >= 84:
        return "BET NOW"
    if score >= 76:
        return "LEAN"
    if score >= 66:
        return "MONITOR"
    return "PASS"


def final_score(row: Dict[str, Any]) -> float:
    pi = row.get("projection_intelligence_v2") or {}
    mt = row.get("market_timing_intelligence") or {}
    mu = row.get("minutes_usage_intelligence") or {}
    muq = mu.get("quality", {}) if isinstance(mu, dict) else {}
    scores = [
        f(row.get("ups_score"), 70),
        f(pi.get("projection_quality"), f(row.get("projection_quality"), 70)),
        f(row.get("context_score"), 70),
        f(muq.get("minutes_usage_score"), f(row.get("minutes_usage_score"), 70)),
        f(mt.get("timing_confidence"), f(row.get("timing_confidence"), 70)),
        f(row.get("confidence_v2", row.get("score", 70)), 70),
    ]
    # Weighted average with small CLV boost/penalty.
    weights = [0.18, 0.22, 0.16, 0.16, 0.16, 0.12]
    score = sum(s*w for s, w in zip(scores, weights))
    score += max(-8, min(8, f(mt.get("expected_clv", row.get("expected_clv_v2", 0))) * 3))
    if str(row.get("rotation_risk_level", "")).upper() == "HIGH":
        score -= 8
    if str(pi.get("volatility", "")).upper() == "HIGH":
        score -= 5
    return round(clamp(score), 1)


def risk_level(row: Dict[str, Any]) -> str:
    pi = row.get("projection_intelligence_v2") or {}
    mt = row.get("market_timing_intelligence") or {}
    risk = 20
    if str(row.get("rotation_risk_level", "")).upper() == "HIGH": risk += 25
    if str(pi.get("volatility", "")).upper() == "HIGH": risk += 18
    if f(row.get("context_score"), 70) < 60: risk += 16
    if f(mt.get("expected_clv", row.get("expected_clv_v2", 0))) < -0.5: risk += 14
    if action(row) in {"PASS", "AVOID"}: risk += 10
    return "HIGH" if risk >= 58 else "MED" if risk >= 35 else "LOW"


def explanation(row: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    pi = row.get("projection_intelligence_v2") or {}
    mt = row.get("market_timing_intelligence") or {}
    mu = row.get("minutes_usage_intelligence") or {}
    ctx = row.get("context_engine") or {}
    if f(pi.get("hit_probability")) >= 60:
        out.append(f"Hit probability {pi.get('hit_probability')}%")
    if f(mt.get("expected_clv")) >= 1:
        out.append(f"Positive expected CLV {mt.get('expected_clv')}")
    if f(row.get("context_score"), 0) >= 80:
        out.append("Strong game context")
    if (mu.get("quality") or {}).get("recommendation") == "TRUST":
        out.append("Minutes/usage profile supports projection")
    for src in [mt.get("reasons", []), pi.get("notes", []), (mu.get("quality") or {}).get("notes", []), ctx.get("notes", []) if isinstance(ctx, dict) else []]:
        for item in src[:2]:
            if item and item not in out:
                out.append(item)
    if not out:
        out.append("Model consensus reviewed across prediction, context, timing, and role signals")
    return out[:5]


def slim(row: Dict[str, Any]) -> Dict[str, Any]:
    pi = row.get("projection_intelligence_v2") or {}
    mt = row.get("market_timing_intelligence") or {}
    mu = row.get("minutes_usage_intelligence") or {}
    return {
        "player": row.get("player"),
        "team": row.get("team"),
        "game": row.get("game"),
        "stat": norm_stat(row.get("stat")),
        "signal": row.get("signal"),
        "line": row.get("line"),
        "odds": row.get("odds", row.get("price", row.get("best_odds"))),
        "sportsbook": book(row),
        "projection": row.get("pred", row.get("projection")),
        "median": pi.get("median"),
        "floor": pi.get("floor"),
        "ceiling": pi.get("ceiling"),
        "hit_probability": pi.get("hit_probability"),
        "context_score": row.get("context_score"),
        "minutes_usage_score": row.get("minutes_usage_score"),
        "timing_action": mt.get("timing_action", row.get("timing_action")),
        "expected_clv": mt.get("expected_clv", row.get("expected_clv_v2")),
        "final_action": action(row),
        "final_score": final_score(row),
        "risk_level": risk_level(row),
        "reasons": explanation(row),
    }


def build(data: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    props = data.get("props", []) or []
    enriched = []
    for p in props:
        r = dict(p)
        r["daily_action_v2"] = {"final_action": action(r), "final_score": final_score(r), "risk_level": risk_level(r), "reasons": explanation(r)}
        enriched.append(r)
    data["props"] = enriched

    playable = [p for p in enriched if action(p) in {"BET NOW", "BET SOON", "LEAN"}]
    waits = [p for p in enriched if action(p) in {"WAIT FOR LINE", "WAIT FOR NEWS", "MONITOR"}]
    avoids = [p for p in enriched if action(p) in {"PASS", "AVOID"}]
    playable.sort(key=lambda x: final_score(x), reverse=True)
    waits.sort(key=lambda x: final_score(x), reverse=True)
    avoids.sort(key=lambda x: final_score(x))

    book_counts = Counter(book(p) for p in playable[:20])
    stat_counts = Counter(norm_stat(p.get("stat")) for p in playable[:20])
    risk_counts = Counter(risk_level(p) for p in enriched)
    action_counts = Counter(action(p) for p in enriched)

    best_book = book_counts.most_common(1)[0][0] if book_counts else "Unknown"
    best_stat = stat_counts.most_common(1)[0][0] if stat_counts else "Unknown"
    top = playable[0] if playable else (waits[0] if waits else (enriched[0] if enriched else {}))

    warnings = []
    if risk_counts.get("HIGH", 0) >= 5:
        warnings.append("Several plays carry high role, volatility, or CLV risk")
    if action_counts.get("WAIT FOR NEWS", 0) > 0:
        warnings.append("Wait for injury/news clarity on some plays")
    if not playable:
        warnings.append("No strong actionable bets after timing/context filters")
    if action_counts.get("BET NOW", 0) >= 6:
        warnings.append("Limit portfolio exposure; too many playable bets can create correlation risk")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "summary": {
            "props_reviewed": len(enriched),
            "bet_now": action_counts.get("BET NOW", 0),
            "bet_soon": action_counts.get("BET SOON", 0),
            "lean": action_counts.get("LEAN", 0),
            "monitor_or_wait": action_counts.get("MONITOR", 0) + action_counts.get("WAIT FOR LINE", 0) + action_counts.get("WAIT FOR NEWS", 0),
            "pass_or_avoid": action_counts.get("PASS", 0) + action_counts.get("AVOID", 0),
            "avg_final_score": round(sum(final_score(p) for p in enriched)/max(1,len(enriched)),1) if enriched else None,
            "best_book": best_book,
            "best_stat_group": best_stat,
            "top_action": slim(top) if top else None,
        },
        "action_counts": dict(action_counts),
        "risk_counts": dict(risk_counts),
        "what_to_bet": [slim(p) for p in playable[:10]],
        "what_to_wait_on": [slim(p) for p in waits[:10]],
        "what_to_avoid": [slim(p) for p in avoids[:10]],
        "sportsbook_summary": [{"sportsbook": k, "playable_count": v} for k, v in book_counts.most_common(10)],
        "stat_summary": [{"stat": k, "playable_count": v} for k, v in stat_counts.most_common(10)],
        "warnings": warnings[:6],
        "operating_note": "Use this report as the daily command center: bet the top actionable plays, monitor injury/line-dependent plays, and avoid low-context or negative-CLV plays.",
    }
    data["daily_action_report_v2"] = report
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
    os.makedirs(OUT_DASH, exist_ok=True)
    os.makedirs(OUT_INTEL, exist_ok=True)
    with open(os.path.join(OUT_DASH, "daily_action_report_v2.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(OUT_INTEL, f"daily_action_report_v2_{args.date}.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"✅ Daily Action Report v2 built: {report['summary']['props_reviewed']} props reviewed")


if __name__ == "__main__":
    main()
