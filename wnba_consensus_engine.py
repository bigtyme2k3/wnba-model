"""
wnba_consensus_engine.py
------------------------
Combines multiple engines into one final recommendation layer.

Engines/votes:
- Projection/EV from player_points
- Player Intelligence role score
- Matchup Intelligence score
- Injury status
- Market/odds availability
- DeepSeek master predictions when available

Outputs:
- data/warehouse/wnba_consensus_engine.json
- data/dashboard/wnba_consensus_engine.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List

import pandas as pd


def load_json(path: str, default: Any):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "" or str(v).lower() == "nan": return default
        return float(v)
    except Exception:
        return default


def key(player: Any, stat: Any, game: Any = "") -> str:
    return "|".join([str(player or "").strip().lower(), str(stat or "").strip().upper(), str(game or "").strip().lower()])


def load_points(target: str) -> pd.DataFrame:
    for path in [f"data/raw/player_points_{target}.csv", "data/raw/player_points_today.csv"]:
        if os.path.exists(path):
            try: return pd.read_csv(path)
            except Exception: pass
    return pd.DataFrame()


def matchup_lookup() -> Dict[str, dict]:
    data = load_json("data/warehouse/wnba_matchup_intelligence.json", {})
    out = {}
    for r in data.get("matchups", []) if isinstance(data, dict) else []:
        out[key(r.get("player"), r.get("stat"), r.get("game"))] = r
        out[key(r.get("player"), r.get("stat"), "")] = r
    return out


def deepseek_lookup() -> Dict[str, dict]:
    data = load_json("data/dashboard/deepseek_master_predictions.json", {})
    out = {}
    for r in data.get("top_master_predictions", []) if isinstance(data, dict) else []:
        out[key(r.get("player"), r.get("stat"), r.get("game"))] = r
        out[key(r.get("player"), r.get("stat"), "")] = r
    return out


def vote(label: str, score: float, threshold: float = 65) -> Dict[str, Any]:
    return {"engine": label, "score": round(max(0, min(100, score)), 1), "agree": score >= threshold}


def grade(score: float) -> str:
    if score >= 88: return "ELITE"
    if score >= 78: return "STRONG"
    if score >= 68: return "PLAYABLE"
    if score >= 58: return "WATCH"
    return "PASS"


def build(target: str) -> Dict[str, Any]:
    points = load_points(target)
    matchups = matchup_lookup()
    deepseek = deepseek_lookup()
    rows: List[Dict[str, Any]] = []

    if not points.empty:
        for _, p in points.iterrows():
            player, stat, game = p.get("player"), p.get("stat"), p.get("game")
            m = matchups.get(key(player, stat, game)) or matchups.get(key(player, stat, "")) or {}
            d = deepseek.get(key(player, stat, game)) or deepseek.get(key(player, stat, "")) or {}
            ev_score = max(0, min(100, 55 + safe_float(p.get("ev_pct"), 0) * 1.7))
            edge_score = max(0, min(100, 55 + abs(safe_float(p.get("edge"), 0)) * 8))
            role_score = safe_float(p.get("role_score"), 50)
            matchup_score = safe_float(m.get("matchup_score"), 55)
            injury_status = str(p.get("injury_status", "ACTIVE")).upper()
            injury_score = 88 if injury_status == "ACTIVE" else 65 if injury_status == "PROBABLE" else 45 if injury_status == "QUESTIONABLE" else 10
            market_score = 82 if str(p.get("market_status", "")).upper() == "ACTIVE MARKET" else 40
            deepseek_score = safe_float(d.get("master_score"), 0)
            votes = [
                vote("Projection EV", ev_score),
                vote("Projection Edge", edge_score),
                vote("Player Intelligence", role_score),
                vote("Matchup Intelligence", matchup_score),
                vote("Injury Engine", injury_score),
                vote("Market Engine", market_score),
            ]
            if deepseek_score:
                votes.append(vote("DeepSeek Engine", deepseek_score))
            score = sum(v["score"] for v in votes) / max(1, len(votes))
            agree = sum(1 for v in votes if v["agree"])
            consensus = round((score * 0.78) + ((agree / max(1, len(votes))) * 100 * 0.22), 1)
            rows.append({
                "player": player,
                "team": p.get("team"),
                "game": game,
                "stat": stat,
                "line": p.get("line"),
                "pred": p.get("pred"),
                "signal": p.get("signal"),
                "conf": p.get("conf"),
                "ev_pct": p.get("ev_pct"),
                "edge": p.get("edge"),
                "consensus_score": consensus,
                "consensus_grade": grade(consensus),
                "engine_agreement": f"{agree}/{len(votes)}",
                "votes": votes,
                "recommendation": "BET" if consensus >= 78 and p.get("signal") in {"OVER", "UNDER", "YES", "NO"} else "LEAN" if consensus >= 68 else "WATCH" if consensus >= 58 else "PASS",
                "matchup_label": m.get("matchup_label"),
                "deepseek_rating": d.get("master_rating"),
            })

    rows.sort(key=lambda r: r["consensus_score"], reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "summary": {
            "rows": len(rows),
            "bets": sum(1 for r in rows if r["recommendation"] == "BET"),
            "leans": sum(1 for r in rows if r["recommendation"] == "LEAN"),
            "elite": sum(1 for r in rows if r["consensus_grade"] == "ELITE"),
        },
        "top_consensus": rows[:50],
        "all_consensus": rows,
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_consensus_engine.json", "data/dashboard/wnba_consensus_engine.json"]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    report = build(args.date)
    print(f"✅ Consensus engine built: {report['summary']}")


if __name__ == "__main__":
    main()
