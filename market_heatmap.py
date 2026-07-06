"""
market_heatmap.py
-----------------
Builds a market heat map from today's props and best bets.

Adds `market_heatmap` to predictions/predictions_YYYY-MM-DD.json.
No external API calls.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date

PRED_DIR = "predictions"
OUT_DIR = "data/intelligence"


def f(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def grade(score):
    if score >= 85:
        return "HOT"
    if score >= 70:
        return "WARM"
    if score >= 55:
        return "NEUTRAL"
    return "COLD"


def build_heatmap(data):
    props = data.get("props", []) or []
    best = data.get("best_bets", []) or []
    by_stat = defaultdict(list)
    by_book = defaultdict(list)
    by_game = defaultdict(list)
    for p in props:
        by_stat[str(p.get("stat", "UNKNOWN")).upper()].append(p)
        by_book[str(p.get("best_book_title") or p.get("best_book") or "Unknown")].append(p)
        by_game[str(p.get("game") or "Unknown")].append(p)

    def summarize(rows):
        if not rows:
            return {}
        count = len(rows)
        strong = [r for r in rows if f(r.get("confidence_v2", r.get("score", 0))) >= 84]
        overs = [r for r in rows if str(r.get("signal", "")).upper() in {"OVER", "YES"}]
        unders = [r for r in rows if str(r.get("signal", "")).upper() in {"UNDER", "NO"}]
        avg_ev = sum(f(r.get("ev_pct")) for r in rows) / max(1, count)
        avg_conf = sum(f(r.get("confidence_v2", r.get("score", 0))) for r in rows) / max(1, count)
        max_ev = max([f(r.get("ev_pct")) for r in rows] or [0])
        opportunity = round(min(100, max(0, avg_conf * 0.55 + max(0, avg_ev) * 2.2 + len(strong) * 4 + max_ev * 0.8)), 1)
        top = sorted(rows, key=lambda r: (f(r.get("confidence_v2", r.get("score", 0))), f(r.get("ev_pct"))), reverse=True)[:5]
        return {
            "count": count,
            "strong_count": len(strong),
            "over_count": len(overs),
            "under_count": len(unders),
            "avg_ev": round(avg_ev, 1),
            "avg_confidence": round(avg_conf, 1),
            "max_ev": round(max_ev, 1),
            "opportunity_score": opportunity,
            "grade": grade(opportunity),
            "top": top,
        }

    markets = {k: summarize(v) for k, v in by_stat.items()}
    books = {k: summarize(v) for k, v in by_book.items()}
    games = {k: summarize(v) for k, v in by_game.items()}
    market_rank = sorted(markets.items(), key=lambda kv: kv[1].get("opportunity_score", 0), reverse=True)
    book_rank = sorted(books.items(), key=lambda kv: kv[1].get("opportunity_score", 0), reverse=True)
    game_rank = sorted(games.items(), key=lambda kv: kv[1].get("opportunity_score", 0), reverse=True)
    return {
        "markets": markets,
        "books": books,
        "games": games,
        "ranked_markets": [{"name": k, **v} for k, v in market_rank],
        "ranked_books": [{"name": k, **v} for k, v in book_rank],
        "ranked_games": [{"name": k, **v} for k, v in game_rank],
        "summary": {
            "best_market": market_rank[0][0] if market_rank else "—",
            "best_book": book_rank[0][0] if book_rank else "—",
            "best_game": game_rank[0][0] if game_rank else "—",
            "props_analyzed": len(props),
            "best_bets": len(best),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Missing predictions file: {path}")
    with open(path) as fobj:
        data = json.load(fobj)
    heat = build_heatmap(data)
    data["market_heatmap"] = heat
    with open(path, "w") as fobj:
        json.dump(data, fobj, indent=2)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"market_heatmap_{args.date}.json"), "w") as fobj:
        json.dump(heat, fobj, indent=2)
    print(f"✅ Market heat map built: {heat['summary']}")


if __name__ == "__main__":
    main()
