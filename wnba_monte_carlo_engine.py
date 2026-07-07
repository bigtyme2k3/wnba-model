"""
wnba_monte_carlo_engine.py
--------------------------
Monte Carlo simulation engine for WNBA player props.

Inputs:
- data/raw/player_points_<date>.csv or player_points_today.csv
- data/warehouse/wnba_matchup_intelligence.json
- data/warehouse/wnba_player_intelligence.json
- data/warehouse/wnba_consensus_engine.json

Outputs:
- data/warehouse/wnba_monte_carlo_engine.json
- data/dashboard/wnba_monte_carlo_engine.json
"""
from __future__ import annotations

import argparse, json, math, os, random
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


def sf(v: Any, d: float = 0.0) -> float:
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return d
        return float(v)
    except Exception:
        return d


def norm(v: Any) -> str:
    return str(v or "").strip().lower().replace("’", "'")


def load_points(target: str) -> pd.DataFrame:
    for p in [f"data/raw/player_points_{target}.csv", "data/raw/player_points_today.csv"]:
        if os.path.exists(p):
            try:
                df = pd.read_csv(p)
                if not df.empty:
                    return df
            except Exception:
                pass
    return pd.DataFrame()


def player_map() -> Dict[str, dict]:
    data = load_json("data/warehouse/wnba_player_intelligence.json", {})
    out = {}
    for r in data.get("players", []) if isinstance(data, dict) else []:
        if r.get("player"):
            out[norm(r.get("player"))] = r
    return out


def matchup_map() -> Dict[str, dict]:
    data = load_json("data/warehouse/wnba_matchup_intelligence.json", {})
    out = {}
    for r in data.get("matchups", []) if isinstance(data, dict) else []:
        key = f"{norm(r.get('player'))}|{str(r.get('stat','')).upper()}|{norm(r.get('game'))}"
        out[key] = r
        out[f"{norm(r.get('player'))}|{str(r.get('stat','')).upper()}|"] = r
    return out


def consensus_map() -> Dict[str, dict]:
    data = load_json("data/warehouse/wnba_consensus_engine.json", {})
    out = {}
    for r in data.get("all_consensus", []) if isinstance(data, dict) else []:
        key = f"{norm(r.get('player'))}|{str(r.get('stat','')).upper()}|{norm(r.get('game'))}"
        out[key] = r
        out[f"{norm(r.get('player'))}|{str(r.get('stat','')).upper()}|"] = r
    return out


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def stat_volatility(stat: str, pred: float, role: float, minutes_trend: str) -> float:
    stat = stat.upper()
    base = {"PTS": 5.2, "REB": 3.1, "AST": 2.7, "3PM": 1.6, "PRA": 7.2, "PA": 6.2, "PR": 6.4, "RA": 4.2}.get(stat, 5.0)
    base += max(0, 60 - role) * 0.035
    if minutes_trend == "UP": base *= 0.95
    if minutes_trend == "DOWN": base *= 1.10
    base += max(0, pred - 20) * 0.04
    return clamp(base, 1.1, 12.0)


def simulate_row(row: dict, players: Dict[str, dict], matchups: Dict[str, dict], cons: Dict[str, dict], sims: int) -> dict:
    player = row.get("player")
    stat = str(row.get("stat", "PTS")).upper()
    game = row.get("game", "")
    key = f"{norm(player)}|{stat}|{norm(game)}"
    pinfo = players.get(norm(player), {})
    m = matchups.get(key) or matchups.get(f"{norm(player)}|{stat}|") or {}
    c = cons.get(key) or cons.get(f"{norm(player)}|{stat}|") or {}
    pred = sf(row.get("pred"), sf(c.get("pred"), 0))
    line = sf(row.get("line"), sf(c.get("line"), pred))
    signal = str(row.get("signal", c.get("signal", ""))).upper()
    role = sf(row.get("role_score"), sf((pinfo.get("intelligence") or {}).get("role_score"), 50))
    matchup_score = sf(m.get("matchup_score"), 55)
    minutes_trend = str(row.get("minutes_trend", (pinfo.get("recent_form") or {}).get("minutes_trend", "STABLE"))).upper()
    injury = str(row.get("injury_status", (pinfo.get("injury") or {}).get("status", "ACTIVE"))).upper()
    if not pred:
        pred = line
    matchup_adj = (matchup_score - 60) * 0.015
    mean = pred + matchup_adj
    if injury == "QUESTIONABLE":
        mean *= 0.92
    elif injury == "PROBABLE":
        mean *= 0.97
    sd = stat_volatility(stat, mean, role, minutes_trend)
    seed = sum(ord(ch) for ch in f"{player}|{stat}|{game}|{line}")
    rng = random.Random(seed)
    vals = []
    for _ in range(max(100, sims)):
        # Mix normal variation with a small minutes/role shock.
        minutes_shock = rng.gauss(0, 1) * (0.6 if role >= 70 else 1.0)
        value = rng.gauss(mean, sd) + minutes_shock
        vals.append(max(0, value))
    vals.sort()
    over_prob = sum(1 for v in vals if v > line) / len(vals)
    under_prob = sum(1 for v in vals if v < line) / len(vals)
    play_prob = over_prob if signal in {"OVER", "YES"} else under_prob if signal in {"UNDER", "NO"} else max(over_prob, under_prob)
    q = lambda p: vals[int(clamp(p, 0, 0.999) * (len(vals)-1))]
    return {
        "player": player,
        "team": row.get("team"),
        "game": game,
        "stat": stat,
        "line": line,
        "projection_mean": round(mean, 2),
        "projection_sd": round(sd, 2),
        "simulations": len(vals),
        "p05": round(q(0.05), 2),
        "p25": round(q(0.25), 2),
        "p50": round(q(0.50), 2),
        "p75": round(q(0.75), 2),
        "p95": round(q(0.95), 2),
        "over_probability": round(over_prob, 4),
        "under_probability": round(under_prob, 4),
        "recommended_side": "OVER" if over_prob >= under_prob else "UNDER",
        "model_signal": signal,
        "signal_probability": round(play_prob, 4),
        "edge_probability": round(play_prob - 0.5, 4),
        "matchup_score": matchup_score,
        "role_score": role,
        "injury_status": injury,
        "minutes_trend": minutes_trend,
        "risk_band": "LOW" if sd <= 3.0 and play_prob >= 0.60 else "MED" if play_prob >= 0.55 else "HIGH",
    }


def build(target: str, sims: int) -> Dict[str, Any]:
    df = load_points(target)
    players = player_map()
    matchups = matchup_map()
    cons = consensus_map()
    rows = []
    if not df.empty:
        for _, r in df.iterrows():
            try:
                rows.append(simulate_row(r.to_dict(), players, matchups, cons, sims))
            except Exception as exc:
                print(f"WARN simulation skipped: {exc}")
    rows.sort(key=lambda r: (r["signal_probability"], -sf(r["projection_sd"])), reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "summary": {
            "rows": len(rows),
            "simulations_per_row": max(100, sims),
            "low_risk": sum(1 for r in rows if r.get("risk_band") == "LOW"),
            "prob_60_plus": sum(1 for r in rows if sf(r.get("signal_probability")) >= 0.60),
        },
        "top_simulations": rows[:50],
        "all_simulations": rows,
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for p in ["data/warehouse/wnba_monte_carlo_engine.json", "data/dashboard/wnba_monte_carlo_engine.json"]:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    ap.add_argument("--sims", type=int, default=5000)
    args = ap.parse_args()
    print(f"Monte Carlo engine built: {build(args.date, args.sims)['summary']}")

if __name__ == "__main__":
    main()
