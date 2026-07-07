"""
wnba_matchup_intelligence.py
----------------------------
Builds matchup intelligence for every projected player prop.

Inputs:
- data/warehouse/wnba_player_intelligence.json
- data/warehouse/wnba_games.json
- data/warehouse/wnba_standings.json
- data/raw/player_points_<date>.csv or player_points_today.csv

Outputs:
- data/warehouse/wnba_matchup_intelligence.json
- data/dashboard/wnba_matchup_intelligence.json
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


def norm(v: Any) -> str:
    return str(v or "").strip().lower().replace("’", "'")


def load_points(target: str) -> pd.DataFrame:
    for path in [f"data/raw/player_points_{target}.csv", "data/raw/player_points_today.csv"]:
        if os.path.exists(path):
            try:
                return pd.read_csv(path)
            except Exception:
                pass
    return pd.DataFrame()


def standings_lookup() -> Dict[str, dict]:
    rows = load_json("data/warehouse/wnba_standings.json", [])
    out = {}
    if isinstance(rows, list):
        for r in rows:
            team = str(r.get("team", "")).strip()
            if team:
                out[norm(team)] = r
    return out


def player_lookup() -> Dict[str, dict]:
    data = load_json("data/warehouse/wnba_player_intelligence.json", {})
    out = {}
    for r in data.get("players", []) if isinstance(data, dict) else []:
        if r.get("player"):
            out[norm(r.get("player"))] = r
    return out


def team_strength(team: str, standings: Dict[str, dict]) -> float:
    rec = standings.get(norm(team), {})
    wins = safe_float(rec.get("wins"), 0)
    losses = safe_float(rec.get("losses"), 0)
    pct = safe_float(rec.get("win_pct"), -1)
    if pct < 0:
        pct = wins / max(1, wins + losses)
    return max(0.2, min(0.8, pct or 0.5))


def stat_matchup_score(stat: str, opp: str, standings: Dict[str, dict]) -> Dict[str, Any]:
    strength = team_strength(opp, standings)
    # Weaker opponent = better prop environment.
    base = 72 - ((strength - 0.5) * 55)
    if stat in {"PTS", "PRA", "PA", "PR", "3PM"}:
        label = "scoring environment"
    elif stat in {"REB", "RA"}:
        label = "rebounding environment"
        base += 2
    elif stat == "AST":
        label = "assist environment"
        base += 1
    else:
        label = "general prop environment"
    return {"score": round(max(35, min(95, base)), 1), "label": label, "opponent_strength": round(strength, 3)}


def build(target: str) -> Dict[str, Any]:
    points = load_points(target)
    standings = standings_lookup()
    players = player_lookup()
    rows: List[Dict[str, Any]] = []

    if not points.empty:
        for _, p in points.iterrows():
            player = str(p.get("player", "")).strip()
            stat = str(p.get("stat", "")).upper()
            opp = str(p.get("opp", "")).strip()
            if not player:
                continue
            intel = players.get(norm(player), {})
            role = safe_float((intel.get("intelligence") or {}).get("role_score"), safe_float(p.get("role_score"), 50))
            recent = intel.get("recent_form", {}) or {}
            match = stat_matchup_score(stat, opp, standings)
            minutes_trend = str(recent.get("minutes_trend", p.get("minutes_trend", "STABLE"))).upper()
            points_trend = str(recent.get("points_trend", p.get("points_trend", "STABLE"))).upper()
            trend_bonus = 0
            if minutes_trend == "UP": trend_bonus += 4
            if points_trend == "UP" and stat in {"PTS", "PRA", "PA", "PR", "3PM"}: trend_bonus += 4
            if minutes_trend == "DOWN": trend_bonus -= 4
            if points_trend == "DOWN" and stat in {"PTS", "PRA", "PA", "PR", "3PM"}: trend_bonus -= 4
            final = (match["score"] * 0.55) + (role * 0.30) + (safe_float(p.get("ev_pct"), 0) * 0.15) + trend_bonus
            rows.append({
                "player": player,
                "team": p.get("team"),
                "opp": opp,
                "game": p.get("game"),
                "stat": stat,
                "line": p.get("line"),
                "pred": p.get("pred"),
                "signal": p.get("signal"),
                "conf": p.get("conf"),
                "ev_pct": p.get("ev_pct"),
                "matchup_score": round(max(0, min(100, final)), 1),
                "matchup_label": "EXCELLENT" if final >= 82 else "GOOD" if final >= 70 else "NEUTRAL" if final >= 58 else "DIFFICULT",
                "opponent_context": match,
                "role_score": role,
                "minutes_trend": minutes_trend,
                "points_trend": points_trend,
                "reasoning": f"{match['label']} vs {opp}; role score {round(role,1)}; minutes {minutes_trend}; points {points_trend}.",
            })

    rows.sort(key=lambda r: r["matchup_score"], reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "summary": {"rows": len(rows), "excellent": sum(1 for r in rows if r["matchup_label"] == "EXCELLENT"), "good": sum(1 for r in rows if r["matchup_label"] == "GOOD")},
        "matchups": rows,
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_matchup_intelligence.json", "data/dashboard/wnba_matchup_intelligence.json"]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    report = build(args.date)
    print(f"✅ Matchup intelligence built: {report['summary']}")


if __name__ == "__main__":
    main()
