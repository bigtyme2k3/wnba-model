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
from typing import Any, Dict
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
        value = float(v)
        return value if math.isfinite(value) else d
    except Exception:
        return d


def norm(v: Any) -> str:
    return str(v or "").strip().lower().replace("’", "'")


def load_points(target: str) -> tuple[pd.DataFrame, str]:
    for path in [f"data/raw/player_points_{target}.csv", "data/raw/player_points_today.csv"]:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                if not df.empty:
                    return df, path
            except Exception:
                pass
    return pd.DataFrame(), "none"


def player_map() -> Dict[str, dict]:
    data = load_json("data/warehouse/wnba_player_intelligence.json", {})
    out = {}
    for row in data.get("players", []) if isinstance(data, dict) else []:
        if row.get("player"):
            out[norm(row.get("player"))] = row
    return out


def matchup_map() -> Dict[str, dict]:
    data = load_json("data/warehouse/wnba_matchup_intelligence.json", {})
    out = {}
    for row in data.get("matchups", []) if isinstance(data, dict) else []:
        key = f"{norm(row.get('player'))}|{str(row.get('stat','')).upper()}|{norm(row.get('game'))}"
        out[key] = row
        out[f"{norm(row.get('player'))}|{str(row.get('stat','')).upper()}|"] = row
    return out


def consensus_map() -> Dict[str, dict]:
    data = load_json("data/warehouse/wnba_consensus_engine.json", {})
    out = {}
    for row in data.get("all_consensus", []) if isinstance(data, dict) else []:
        key = f"{norm(row.get('player'))}|{str(row.get('stat','')).upper()}|{norm(row.get('game'))}"
        out[key] = row
        out[f"{norm(row.get('player'))}|{str(row.get('stat','')).upper()}|"] = row
    return out


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def stat_volatility(stat: str, pred: float, role: float, minutes_trend: str) -> float:
    stat = stat.upper()
    base = {"PTS": 5.2, "REB": 3.1, "AST": 2.7, "3PM": 1.6, "PRA": 7.2, "PA": 6.2, "PR": 6.4, "RA": 4.2}.get(stat, 5.0)
    base += max(0, 60 - role) * 0.035
    if minutes_trend == "UP":
        base *= 0.95
    if minutes_trend == "DOWN":
        base *= 1.10
    base += max(0, pred - 20) * 0.04
    return clamp(base, 1.1, 12.0)


def simulate_row(row: dict, players: Dict[str, dict], matchups: Dict[str, dict], cons: Dict[str, dict], sims: int) -> dict:
    player = row.get("player")
    stat = str(row.get("stat", "PTS")).upper()
    game = row.get("game", "")
    key = f"{norm(player)}|{stat}|{norm(game)}"
    pinfo = players.get(norm(player), {})
    matchup = matchups.get(key) or matchups.get(f"{norm(player)}|{stat}|") or {}
    consensus = cons.get(key) or cons.get(f"{norm(player)}|{stat}|") or {}
    pred = sf(row.get("pred"), sf(consensus.get("pred"), 0))
    line = sf(row.get("line"), sf(consensus.get("line"), pred))
    signal = str(row.get("signal", consensus.get("signal", ""))).upper()
    role = sf(row.get("role_score"), sf((pinfo.get("intelligence") or {}).get("role_score"), 50))
    matchup_score = sf(matchup.get("matchup_score"), 55)
    minutes_trend = str(row.get("minutes_trend", (pinfo.get("recent_form") or {}).get("minutes_trend", "STABLE"))).upper()
    injury = str(row.get("injury_status", (pinfo.get("injury") or {}).get("status", "ACTIVE"))).upper()
    history_games = int(sf(row.get("history_games", row.get("history_games_available", consensus.get("history_games", 0)))))
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
        minutes_shock = rng.gauss(0, 1) * (0.6 if role >= 70 else 1.0)
        value = rng.gauss(mean, sd) + minutes_shock
        vals.append(max(0, value))
    vals.sort()
    over_prob = sum(1 for value in vals if value > line) / len(vals)
    under_prob = sum(1 for value in vals if value < line) / len(vals)
    play_prob = over_prob if signal in {"OVER", "YES"} else under_prob if signal in {"UNDER", "NO"} else max(over_prob, under_prob)
    quantile = lambda p: vals[int(clamp(p, 0, 0.999) * (len(vals) - 1))]
    return {
        "player": player,
        "team": row.get("team"),
        "game": game,
        "stat": stat,
        "line": line,
        "projection_mean": round(mean, 2),
        "projection_sd": round(sd, 2),
        "simulations": len(vals),
        "p05": round(quantile(0.05), 2),
        "p25": round(quantile(0.25), 2),
        "p50": round(quantile(0.50), 2),
        "p75": round(quantile(0.75), 2),
        "p95": round(quantile(0.95), 2),
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
        "history_games": history_games,
        "risk_band": "LOW" if sd <= 3.0 and play_prob >= 0.60 else "MED" if play_prob >= 0.55 else "HIGH",
    }


def build(target: str, sims: int) -> Dict[str, Any]:
    df, source_path = load_points(target)
    players = player_map()
    matchups = matchup_map()
    consensus = consensus_map()
    rows = []
    skipped = 0
    if not df.empty:
        for _, source_row in df.iterrows():
            try:
                rows.append(simulate_row(source_row.to_dict(), players, matchups, consensus, sims))
            except Exception as exc:
                skipped += 1
                print(f"WARN simulation skipped: {exc}")
    rows.sort(key=lambda row: (row["signal_probability"], -sf(row["projection_sd"])), reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "input_source": source_path,
        "summary": {
            "rows": len(rows),
            "source_rows": len(df),
            "skipped_rows": skipped,
            "simulations_per_row": max(100, sims),
            "low_risk": sum(1 for row in rows if row.get("risk_band") == "LOW"),
            "prob_60_plus": sum(1 for row in rows if sf(row.get("signal_probability")) >= 0.60),
            "history_5_plus": sum(1 for row in rows if sf(row.get("history_games")) >= 5),
        },
        "top_simulations": rows[:50],
        "all_simulations": rows,
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_monte_carlo_engine.json", "data/dashboard/wnba_monte_carlo_engine.json"]:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--sims", type=int, default=5000)
    args = parser.parse_args()
    print(f"Monte Carlo engine built: {build(args.date, args.sims)['summary']}")


if __name__ == "__main__":
    main()
