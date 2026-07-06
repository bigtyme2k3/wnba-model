"""
game_command_center.py
----------------------
Builds a game-level command center for the live dashboard.

No external API calls. Uses the baked predictions JSON plus existing data already
created by the pipeline.

Adds `game_command_center` into predictions/predictions_YYYY-MM-DD.json.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone

PRED_DIR = "predictions"
OUT_DIR = "data/intelligence"


def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def game_key(g):
    away = (g.get("away") or {}).get("name") or g.get("away_team") or ""
    home = (g.get("home") or {}).get("name") or g.get("home_team") or ""
    return f"{away} @ {home}".strip()


def simple_prob(edge):
    return max(35, min(65, round(50 + safe_float(edge) * 2.2, 1)))


def match_game(row, key):
    raw = " ".join(str(row.get(k, "")) for k in ["game", "opp", "matchup", "event", "team", "home_team", "away_team"])
    return key.lower() in raw.lower() or all(part.lower() in raw.lower() for part in key.split(" @ ") if part)


def build_game_center(data):
    games = data.get("games", []) or []
    props = data.get("props", []) or []
    best_bets = data.get("best_bets", []) or []
    correlations = data.get("correlations", []) or []
    matchups = {m.get("game"): m for m in data.get("team_matchups", []) or []}
    slips = (data.get("slip_optimizer", {}) or {}).get("slips", []) or []

    centers = []
    for g in games:
        key = game_key(g)
        m = matchups.get(key, {})
        game_props = [p for p in props if match_game(p, key)]
        game_bets = [b for b in best_bets if match_game(b, key)]
        game_corr = [c for c in correlations if str(c.get("game", "")).lower() == key.lower()]
        top_props = sorted(game_props, key=lambda p: (safe_float(p.get("confidence_v2", p.get("score", 0))), safe_float(p.get("ev_pct", 0))), reverse=True)[:8]
        top_bets = sorted(game_bets, key=lambda b: (safe_float(b.get("score", 0)), safe_float(b.get("ev_pct", 0))), reverse=True)[:5]
        related_slips = []
        for s in slips:
            if any(key.lower() in str(play.get("game", "")).lower() for play in s.get("plays", [])):
                related_slips.append(s)
        model_edge = safe_float(m.get("offense_gap", 0))
        win_prob_home = simple_prob(model_edge)
        command_score = round((len(top_bets) * 12) + (len(top_props) * 3) + max(0, safe_float(m.get("pace", 80)) - 78) + sum(max(0, safe_float(p.get("ev_pct", 0))) for p in top_props[:3]) / 3, 1)
        centers.append({
            "game": key,
            "tip": g.get("tip") or g.get("start_time") or "",
            "away": (g.get("away") or {}).get("name") or g.get("away_team") or "",
            "home": (g.get("home") or {}).get("name") or g.get("home_team") or "",
            "win_probability_home": win_prob_home,
            "win_probability_away": round(100 - win_prob_home, 1),
            "projected_score": {
                "away": round((safe_float(m.get("total", 160)) / 2) - model_edge / 2, 1) if safe_float(m.get("total", 0)) else "—",
                "home": round((safe_float(m.get("total", 160)) / 2) + model_edge / 2, 1) if safe_float(m.get("total", 0)) else "—",
            },
            "pace": m.get("pace", "—"),
            "pace_label": m.get("pace_label", "—"),
            "vegas_total": m.get("total", "—"),
            "home_spread": m.get("spread_home", "—"),
            "matchup_note": m.get("matchup_note", ""),
            "command_score": command_score,
            "top_props": top_props,
            "top_bets": top_bets,
            "correlations": game_corr[:6],
            "related_slips": related_slips[:3],
            "injury_watch": [p for p in game_props if str(p.get("injury_status", "ACTIVE")).upper() != "ACTIVE"][:8],
            "market_summary": {
                "props": len(game_props),
                "best_bets": len(game_bets),
                "correlations": len(game_corr),
                "avg_confidence": round(sum(safe_float(p.get("confidence_v2", p.get("score", 0))) for p in game_props) / max(1, len(game_props)), 1),
                "avg_ev": round(sum(safe_float(p.get("ev_pct", 0)) for p in game_props) / max(1, len(game_props)), 1),
            },
        })
    centers.sort(key=lambda x: x.get("command_score", 0), reverse=True)
    return centers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Missing predictions file: {path}")
    with open(path) as f:
        data = json.load(f)
    centers = build_game_center(data)
    data["game_command_center"] = centers
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"game_command_center_{args.date}.json"), "w") as f:
        json.dump(centers, f, indent=2)
    print(f"✅ Game Command Center built: {len(centers)} games")


if __name__ == "__main__":
    main()
