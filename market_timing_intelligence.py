"""
market_timing_intelligence.py
-----------------------------
WNBA Market Timing Intelligence.

Determines whether each playable prop should be bet now, watched, or avoided
based on existing line/odds, projection edge, CLV signals, context, volatility,
and sportsbook hints. No external API calls.

Outputs:
  - Adds `market_timing_intelligence` to predictions/predictions_YYYY-MM-DD.json
  - Adds per-prop `market_timing_intelligence`
  - data/intelligence/market_timing_intelligence_YYYY-MM-DD.json
  - data/dashboard/market_timing_intelligence.json
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

FAST_BOOKS = {"pinnacle", "circa", "draftkings", "dk", "betmgm"}
SLOW_BOOKS = {"fanduel", "fd", "fanatics", "espn bet", "betrivers", "hard rock", "caesars"}


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
    return {"POINTS":"PTS","REBOUNDS":"REB","ASSISTS":"AST","THREES":"3PM","3PTM":"3PM","PTS+REB+AST":"PRA","PTS+REB":"PR","PTS+AST":"PA","REB+AST":"RA"}.get(raw, raw)


def book_name(row: Dict[str, Any]) -> str:
    return str(row.get("best_book_title") or row.get("best_book") or row.get("sportsbook") or row.get("book") or "Unknown")


def expected_clv(row: Dict[str, Any]) -> float:
    # Use existing fields when present, otherwise infer from projection edge.
    for k in ["expected_clv", "clv", "clv_edge", "projected_clv"]:
        if row.get(k) not in [None, "", "—"]:
            return f(row.get(k))
    pi = row.get("projection_intelligence_v2") or {}
    edge = f(pi.get("edge_to_line"), f(row.get("edge"), f(row.get("pred")) - f(row.get("line"))))
    stat = norm_stat(row.get("stat"))
    scale = {"PTS": 0.55, "PRA": 0.42, "PR": 0.45, "PA": 0.45, "RA": 0.55, "REB": 0.7, "AST": 0.7, "3PM": 1.2}.get(stat, 0.55)
    return edge * scale


def odds_score(row: Dict[str, Any]) -> float:
    odds = f(row.get("odds", row.get("price", row.get("best_odds", 0))))
    if not odds:
        return 50
    if odds >= 100:
        return 62 + min(18, odds / 25)
    return 55 - min(20, abs(odds + 110) / 12)


def timing_for(row: Dict[str, Any]) -> Dict[str, Any]:
    pi = row.get("projection_intelligence_v2") or {}
    mu = row.get("minutes_usage_intelligence") or {}
    muq = mu.get("quality", {}) if isinstance(mu, dict) else {}
    ctx = row.get("context_engine") or {}
    clv = expected_clv(row)
    book = book_name(row)
    book_l = book.lower()
    context_score = f(row.get("context_score"), f((ctx or {}).get("context_score"), 70))
    projection_quality = f(pi.get("projection_quality"), f(row.get("projection_quality"), 70))
    hit_prob = f(pi.get("hit_probability"), f(row.get("hit_probability_v2"), 0))
    mu_score = f(muq.get("minutes_usage_score"), f(row.get("minutes_usage_score"), 70))
    volatility = str(pi.get("volatility") or row.get("volatility") or "Medium")
    injury = str((ctx.get("injury_status") if isinstance(ctx, dict) else row.get("injury_status")) or row.get("injury_status") or "ACTIVE").upper()
    edge = abs(f(pi.get("edge_to_line"), f(row.get("pred")) - f(row.get("line"))))

    urgency = 50
    urgency += max(-18, min(22, clv * 7))
    urgency += max(-8, min(10, edge * 3))
    urgency += 8 if any(b in book_l for b in SLOW_BOOKS) else -4 if any(b in book_l for b in FAST_BOOKS) else 0
    urgency += 6 if hit_prob >= 60 else -5 if hit_prob and hit_prob < 53 else 0
    urgency -= 14 if injury in {"QUESTIONABLE", "GTD", "DOUBTFUL"} else 0
    urgency -= 8 if volatility == "High" else 3 if volatility == "Medium" else -2
    urgency += 5 if context_score >= 80 and mu_score >= 75 else -10 if context_score < 60 or mu_score < 60 else 0
    urgency = clamp(urgency)

    direction = "toward model" if clv > 0.5 else "against model" if clv < -0.5 else "stable"
    if injury in {"QUESTIONABLE", "GTD", "DOUBTFUL"}:
        action = "WAIT FOR NEWS"
    elif clv >= 1.5 and projection_quality >= 72 and context_score >= 65:
        action = "BET NOW"
    elif clv >= 0.5 and hit_prob >= 57 and volatility != "High":
        action = "BET SOON"
    elif clv < -1 or projection_quality < 55:
        action = "PASS"
    elif volatility == "High" or context_score < 62:
        action = "MONITOR"
    else:
        action = "WAIT FOR LINE"

    confidence = clamp((projection_quality * 0.28) + (context_score * 0.20) + (mu_score * 0.18) + urgency * 0.22 + (50 + clv * 8) * 0.12)
    reasons: List[str] = []
    if clv >= 1.5: reasons.append("positive expected CLV")
    if clv < -0.5: reasons.append("negative CLV risk")
    if any(b in book_l for b in SLOW_BOOKS): reasons.append("book may be slower to adjust")
    if injury in {"QUESTIONABLE", "GTD", "DOUBTFUL"}: reasons.append("wait for injury clarity")
    if volatility == "High": reasons.append("high projection volatility")
    if context_score >= 80: reasons.append("strong context support")
    if mu_score < 60: reasons.append("minutes/usage instability")
    return {
        "timing_action": action,
        "timing_confidence": round(confidence, 1),
        "urgency_score": round(urgency, 1),
        "expected_clv": round(clv, 2),
        "expected_line_direction": direction,
        "sportsbook": book,
        "book_timing_profile": "slow" if any(b in book_l for b in SLOW_BOOKS) else "fast" if any(b in book_l for b in FAST_BOOKS) else "unknown",
        "latest_action_window": "now" if action == "BET NOW" else "pre-tip after news" if action == "WAIT FOR NEWS" else "monitor until line moves",
        "reasons": reasons[:6],
    }


def slim(row: Dict[str, Any]) -> Dict[str, Any]:
    mt = row.get("market_timing_intelligence") or {}
    return {
        "player": row.get("player"), "team": row.get("team"), "game": row.get("game"),
        "stat": row.get("stat"), "signal": row.get("signal"), "line": row.get("line"),
        "odds": row.get("odds", row.get("price", row.get("best_odds"))),
        "pred": row.get("pred"), **mt
    }


def build(data: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    props = data.get("props", []) or []
    enriched = []
    for p in props:
        r = dict(p)
        mt = timing_for(r)
        r["market_timing_intelligence"] = mt
        r["timing_action"] = mt["timing_action"]
        r["timing_confidence"] = mt["timing_confidence"]
        r["expected_clv_v2"] = mt["expected_clv"]
        enriched.append(r)
    data["props"] = enriched

    counts = defaultdict(int)
    by_book = defaultdict(list)
    for r in enriched:
        mt = r.get("market_timing_intelligence") or {}
        counts[mt.get("timing_action", "UNKNOWN")] += 1
        by_book[mt.get("sportsbook", "Unknown")].append(r)

    bet_now = [r for r in enriched if (r.get("market_timing_intelligence") or {}).get("timing_action") in {"BET NOW", "BET SOON"}]
    bet_now.sort(key=lambda x: (f((x.get("market_timing_intelligence") or {}).get("timing_confidence")), f((x.get("market_timing_intelligence") or {}).get("expected_clv"))), reverse=True)
    wait = [r for r in enriched if "WAIT" in (r.get("market_timing_intelligence") or {}).get("timing_action", "") or (r.get("market_timing_intelligence") or {}).get("timing_action") == "MONITOR"]
    wait.sort(key=lambda x: f((x.get("market_timing_intelligence") or {}).get("urgency_score")), reverse=True)

    book_summary = []
    for book, rows in by_book.items():
        book_summary.append({
            "sportsbook": book,
            "count": len(rows),
            "avg_expected_clv": round(sum(f((r.get("market_timing_intelligence") or {}).get("expected_clv")) for r in rows) / max(1, len(rows)), 2),
            "bet_now_count": len([r for r in rows if (r.get("market_timing_intelligence") or {}).get("timing_action") in {"BET NOW", "BET SOON"}]),
        })
    book_summary.sort(key=lambda x: (x["bet_now_count"], x["avg_expected_clv"]), reverse=True)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "summary": {
            "props_scored": len(enriched),
            "bet_now_count": counts.get("BET NOW", 0),
            "bet_soon_count": counts.get("BET SOON", 0),
            "wait_count": counts.get("WAIT FOR LINE", 0) + counts.get("WAIT FOR NEWS", 0),
            "monitor_count": counts.get("MONITOR", 0),
            "pass_count": counts.get("PASS", 0),
            "avg_expected_clv": round(sum(f((r.get("market_timing_intelligence") or {}).get("expected_clv")) for r in enriched) / max(1, len(enriched)), 2) if enriched else None,
        },
        "action_counts": dict(counts),
        "best_timing_plays": [slim(r) for r in bet_now[:15]],
        "monitor_list": [slim(r) for r in wait[:15]],
        "sportsbook_timing": book_summary[:12],
    }
    data["market_timing_intelligence"] = report
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
    with open(os.path.join(OUT_INTEL, f"market_timing_intelligence_{args.date}.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(OUT_DASH, "market_timing_intelligence.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"✅ Market Timing Intelligence built: {report['summary']['props_scored']} props scored")


if __name__ == "__main__":
    main()
