"""
decision_center.py
------------------
Builds a concise Betting Decision Center from the existing enriched prediction JSON.

No API calls. No model retraining. This module is designed to run after:
  - unified_prediction_score.py
  - market_heatmap.py
  - game_command_center.py
  - slip_optimizer.py

It adds `decision_center` to predictions/predictions_YYYY-MM-DD.json and exports
an external JSON copy to data/intelligence/decision_center_YYYY-MM-DD.json.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

PRED_DIR = "predictions"
OUT_DIR = "data/intelligence"


def f(v, default=0.0):
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return default
        return float(v)
    except Exception:
        return default


def is_actionable(p):
    return (
        f(p.get("ups_score")) >= 80
        and f(p.get("readiness_score")) >= 70
        and str(p.get("injury_status", "ACTIVE")).upper() not in {"OUT", "DOUBTFUL"}
        and p.get("line") not in [None, "", "—"]
    )


def trap_reason(p):
    reasons = []
    if f(p.get("ups_score")) < 62:
        reasons.append("Low UPS")
    if f(p.get("readiness_score")) < 65:
        reasons.append("Low readiness")
    if str(p.get("injury_status", "ACTIVE")).upper() in {"OUT", "DOUBTFUL", "QUESTIONABLE", "GTD"}:
        reasons.append(f"Injury: {p.get('injury_status')}")
    if f(p.get("ev_pct")) < -2:
        reasons.append("Negative EV")
    if f(p.get("model_agreement", {}).get("agree_count")) <= 2:
        reasons.append("Weak model agreement")
    return reasons[:4]


def slim(p):
    keep = [
        "player", "team", "opp", "game", "stat", "line", "pred", "edge", "signal",
        "best_book", "best_book_title", "over_price", "under_price", "ev_pct",
        "ups_score", "ups_grade", "ups_badges", "readiness_score", "readiness",
        "model_agreement", "confidence_v2", "injury_status", "prediction_breakdown",
        "last5_hit", "last10_hit", "opp_rank",
    ]
    return {k: p.get(k) for k in keep if k in p}


def build(data):
    props = data.get("props", []) or []
    heat = data.get("market_heatmap", {}) or {}
    game_centers = data.get("game_command_center", []) or []
    slips = (data.get("slip_optimizer", {}) or {}).get("slips", []) or []

    actionable = [p for p in props if is_actionable(p)]
    top = sorted(actionable, key=lambda p: (f(p.get("ups_score")), f(p.get("ev_pct"))), reverse=True)
    best_bet = top[0] if top else None
    high_ev = sorted([p for p in actionable if f(p.get("ev_pct")) > 0], key=lambda p: f(p.get("ev_pct")), reverse=True)[:10]
    safest = sorted(actionable, key=lambda p: (f(p.get("readiness_score")), f(p.get("ups_score"))), reverse=True)[:10]
    traps = []
    for p in props:
        reasons = trap_reason(p)
        if reasons:
            item = slim(p)
            item["trap_reasons"] = reasons
            traps.append(item)
    traps = sorted(traps, key=lambda p: (f(p.get("ups_score")), f(p.get("readiness_score"))))[:12]

    market_counts = Counter(str(p.get("stat", "UNKNOWN")).upper() for p in actionable)
    book_counts = Counter(str(p.get("best_book_title") or p.get("best_book") or "Unknown") for p in actionable)
    signal_counts = Counter(str(p.get("signal", "UNKNOWN")).upper() for p in actionable)
    game_counts = Counter(str(p.get("game", "Unknown")) for p in actionable)

    best_market = heat.get("summary", {}).get("best_market") or (market_counts.most_common(1)[0][0] if market_counts else "—")
    best_book = heat.get("summary", {}).get("best_book") or (book_counts.most_common(1)[0][0] if book_counts else "—")
    best_game = heat.get("summary", {}).get("best_game") or (game_counts.most_common(1)[0][0] if game_counts else "—")

    game_actions = []
    for g in game_centers:
        game_actions.append({
            "game": g.get("game"),
            "command_score": g.get("command_score"),
            "best_bets": g.get("market_summary", {}).get("best_bets", 0),
            "props": g.get("market_summary", {}).get("props", 0),
            "top_props": [slim(x) for x in (g.get("top_props") or [])[:3]],
        })
    game_actions.sort(key=lambda x: f(x.get("command_score")), reverse=True)

    recommended_exposure = "LOW"
    if len(top) >= 8 and f(top[0].get("ups_score")) >= 90:
        recommended_exposure = "MEDIUM"
    if len(top) >= 12 and f(top[0].get("ups_score")) >= 94 and len(high_ev) >= 5:
        recommended_exposure = "AGGRESSIVE"

    bullets = []
    if best_bet:
        bullets.append(f"Best bet: {best_bet.get('player')} {best_bet.get('stat')} {best_bet.get('signal')} with UPS {best_bet.get('ups_score')}.")
    bullets.append(f"{len(actionable)} actionable props passed UPS/readiness filters.")
    bullets.append(f"Strongest market: {best_market}. Best book concentration: {best_book}.")
    if traps:
        bullets.append(f"{len(traps)} traps or low-readiness props flagged.")
    if slips:
        bullets.append(f"{len(slips)} optimized slips available for review.")

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "actionable_count": len(actionable),
            "trap_count": len(traps),
            "best_market": best_market,
            "best_book": best_book,
            "best_game": best_game,
            "recommended_exposure": recommended_exposure,
            "avg_ups_actionable": round(sum(f(p.get("ups_score")) for p in actionable) / max(1, len(actionable)), 1),
            "top_signal": signal_counts.most_common(1)[0][0] if signal_counts else "—",
        },
        "briefing": bullets[:7],
        "best_bet": slim(best_bet) if best_bet else None,
        "top_ups": [slim(p) for p in top[:12]],
        "high_ev": [slim(p) for p in high_ev[:12]],
        "safest": [slim(p) for p in safest[:8]],
        "traps": traps,
        "market_focus": [{"market": k, "count": v} for k, v in market_counts.most_common(8)],
        "book_focus": [{"book": k, "count": v} for k, v in book_counts.most_common(8)],
        "game_focus": game_actions[:6],
        "slip_focus": slips[:4],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Missing predictions file: {path}")
    with open(path) as fobj:
        data = json.load(fobj)
    center = build(data)
    data["decision_center"] = center
    with open(path, "w") as fobj:
        json.dump(data, fobj, indent=2)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"decision_center_{args.date}.json"), "w") as fobj:
        json.dump(center, fobj, indent=2)
    print(f"✅ Decision Center built: {center['summary']['actionable_count']} actionable, {center['summary']['trap_count']} traps")


if __name__ == "__main__":
    main()
