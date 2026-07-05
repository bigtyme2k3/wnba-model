"""
slip_optimizer.py
-----------------
Builds optimized betting-slip suggestions from today's ranked best bets.

This is a decision-support feature, not bankroll tracking. It creates:
  - best single
  - safest 2-leg
  - highest EV 2-leg
  - safest 3-leg
  - aggressive 3-leg

Outputs:
  data/tracking/slip_optimizer.json
  Injects `slip_optimizer` into predictions/predictions_YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
from datetime import date, datetime, timezone

PREDICTIONS_DIR = "predictions"
OUT_PATH = "data/tracking/slip_optimizer.json"


def prediction_path(target_date: str) -> str:
    exact = os.path.join(PREDICTIONS_DIR, f"predictions_{target_date}.json")
    if os.path.exists(exact):
        return exact
    raise FileNotFoundError(f"Missing predictions file: {exact}")


def decimal_odds(american):
    try:
        a = float(american)
    except Exception:
        a = -110.0
    return 1 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def american_from_decimal(decimal):
    d = max(1.01, float(decimal))
    if d >= 2.0:
        return int(round((d - 1.0) * 100))
    return int(round(-100.0 / (d - 1.0)))


def safe_num(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def leg_key(bet):
    return f"{bet.get('type','')}|{bet.get('game','')}|{bet.get('player','')}|{bet.get('play','')}"


def correlation_penalty(combo):
    games = [str(b.get("game", "")) for b in combo]
    players = [str(b.get("player", "")) for b in combo if b.get("player")]
    types = [str(b.get("type", "")) for b in combo]
    penalty = 1.0
    if len(set(games)) < len(games):
        penalty *= 0.92
    if players and len(set(players)) < len(players):
        penalty *= 0.80
    if types.count("PROP") >= 2 and len(set(games)) < len(games):
        penalty *= 0.93
    return round(penalty, 3)


def combo_ev(prob, dec):
    return round(prob * (dec - 1.0) - (1.0 - prob), 4)


def combo_reason(combo, penalty):
    books = sorted(set(str(b.get("best_book_title") or b.get("best_book") or "book") for b in combo if b.get("best_book") or b.get("best_book_title")))
    avg_score = sum(safe_num(b.get("score"), 50) for b in combo) / max(1, len(combo))
    avg_ev = sum(safe_num(b.get("ev_pct"), 0) for b in combo) / max(1, len(combo))
    parts = [f"avg score {avg_score:.0f}", f"avg EV {avg_ev:.1f}%"]
    if books:
        parts.append("best books: " + ", ".join(books[:3]))
    if penalty < 1:
        parts.append("correlation penalty applied")
    return " · ".join(parts)


def make_slip(combo, label, risk):
    dec = 1.0
    prob = 1.0
    legs = []
    for b in combo:
        odds = b.get("best_odds") or b.get("odds") or -110
        dec *= decimal_odds(odds)
        prob *= safe_num(b.get("model_prob"), 0.52)
        legs.append({
            "type": b.get("type"),
            "play": b.get("play"),
            "game": b.get("game"),
            "player": b.get("player"),
            "stat": b.get("stat"),
            "book": b.get("best_book_title") or b.get("best_book"),
            "line": b.get("best_line") or b.get("market_line") or b.get("line"),
            "odds": odds,
            "ev_pct": b.get("ev_pct"),
            "score": b.get("score"),
            "grade": b.get("grade"),
        })
    penalty = correlation_penalty(combo)
    adj_prob = round(prob * penalty, 4)
    ev = combo_ev(adj_prob, dec)
    return {
        "label": label,
        "risk": risk,
        "legs": len(combo),
        "plays": legs,
        "combined_decimal": round(dec, 3),
        "combined_american": american_from_decimal(dec),
        "model_prob": adj_prob,
        "model_prob_pct": round(adj_prob * 100, 1),
        "ev": ev,
        "ev_pct": round(ev * 100, 1),
        "correlation_penalty": penalty,
        "avg_score": round(sum(safe_num(b.get("score"), 50) for b in combo) / max(1, len(combo)), 1),
        "reason": combo_reason(combo, penalty),
    }


def eligible_bets(best_bets):
    seen = set()
    out = []
    for b in best_bets or []:
        if b.get("grade") == "PASS":
            continue
        if safe_num(b.get("ev"), 0) <= 0:
            continue
        if safe_num(b.get("model_prob"), 0) <= 0.505:
            continue
        k = leg_key(b)
        if k in seen:
            continue
        seen.add(k)
        out.append(b)
    out.sort(key=lambda b: (-safe_num(b.get("score"), 0), -safe_num(b.get("ev"), 0), -safe_num(b.get("model_prob"), 0)))
    return out[:18]


def choose_slips(best_bets):
    bets = eligible_bets(best_bets)
    slips = []
    if not bets:
        return {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "eligible_bets": 0, "slips": []}

    slips.append(make_slip([bets[0]], "Best Single", "LOW"))

    combos2 = [make_slip(c, "candidate", "MED") for c in itertools.combinations(bets[:12], 2)]
    combos3 = [make_slip(c, "candidate", "HIGH") for c in itertools.combinations(bets[:10], 3)]
    combos2_ev = [s for s in combos2 if s["ev"] > 0]
    combos3_ev = [s for s in combos3 if s["ev"] > 0]

    if combos2:
        safest2 = max(combos2, key=lambda s: (s["model_prob"], s["avg_score"], s["ev"]))
        safest2.update({"label": "Safest 2-Leg", "risk": "MED"})
        slips.append(safest2)
    if combos2_ev:
        best2 = max(combos2_ev, key=lambda s: (s["ev"], s["avg_score"]))
        best2.update({"label": "Highest EV 2-Leg", "risk": "MED"})
        slips.append(best2)
    if combos3:
        safest3 = max(combos3, key=lambda s: (s["model_prob"], s["avg_score"], s["ev"]))
        safest3.update({"label": "Safest 3-Leg", "risk": "HIGH"})
        slips.append(safest3)
    if combos3_ev:
        aggr3 = max(combos3_ev, key=lambda s: (s["ev"], s["combined_decimal"], s["avg_score"]))
        aggr3.update({"label": "Aggressive 3-Leg", "risk": "HIGH"})
        slips.append(aggr3)

    # Deduplicate identical leg sets while preserving order.
    unique = []
    seen_sets = set()
    for s in slips:
        sig = tuple(sorted(p.get("play", "") for p in s.get("plays", [])))
        if sig in seen_sets:
            continue
        seen_sets.add(sig)
        unique.append(s)

    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "eligible_bets": len(bets), "slips": unique[:6]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out", default=OUT_PATH)
    args = parser.parse_args()

    path = prediction_path(args.date)
    with open(path) as f:
        data = json.load(f)

    payload = choose_slips(data.get("best_bets", []))
    data["slip_optimizer"] = payload

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Slip optimizer complete: {len(payload.get('slips', []))} slips | eligible bets {payload.get('eligible_bets', 0)}")


if __name__ == "__main__":
    main()
