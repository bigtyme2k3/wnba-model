"""
WNBA Monte Carlo simulation engine for player props.
Uses projection, matchup, role, recent minutes, and current injury intelligence.
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


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return clean_json(value.item())
        except Exception:
            pass
    return value


def norm(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().replace("’", "'").split())


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
    return {norm(r.get("player")): r for r in data.get("players", []) if r.get("player")}


def injury_map() -> Dict[str, dict]:
    data = load_json("data/warehouse/wnba_injury_intelligence.json", {})
    return {norm(r.get("player")): r for r in data.get("adjustments", []) if r.get("player")}


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


def stat_volatility(stat: str, pred: float, role: float, minutes_trend: str, injury_status: str) -> float:
    base = {"PTS": 5.2, "REB": 3.1, "AST": 2.7, "3PM": 1.6, "PRA": 7.2, "PA": 6.2, "PR": 6.4, "RA": 4.2}.get(stat.upper(), 5.0)
    base += max(0, 60 - role) * 0.035
    if minutes_trend == "UP": base *= 0.95
    if minutes_trend == "DOWN": base *= 1.10
    if injury_status in {"QUESTIONABLE", "UNKNOWN"}: base *= 1.20
    elif injury_status == "PROBABLE": base *= 1.08
    base += max(0, pred - 20) * 0.04
    return clamp(base, 1.1, 14.0)


def simulate_row(row: dict, players: Dict[str, dict], injuries: Dict[str, dict], matchups: Dict[str, dict], cons: Dict[str, dict], sims: int) -> dict:
    player = str(row.get("player") or "")
    stat = str(row.get("stat", "PTS")).upper()
    game = str(row.get("game", "") or "")
    key = f"{norm(player)}|{stat}|{norm(game)}"
    pinfo = players.get(norm(player), {})
    injury = injuries.get(norm(player), {})
    matchup = matchups.get(key) or matchups.get(f"{norm(player)}|{stat}|") or {}
    consensus = cons.get(key) or cons.get(f"{norm(player)}|{stat}|") or {}

    pred = sf(row.get("pred"), sf(consensus.get("pred"), 0))
    line = sf(row.get("line"), sf(consensus.get("line"), pred))
    signal = str(row.get("signal", consensus.get("signal", ""))).upper()
    role = sf(row.get("role_score"), sf((pinfo.get("intelligence") or {}).get("role_score"), 50))
    matchup_score = sf(matchup.get("matchup_score"), 55)
    minutes_trend = str(row.get("minutes_trend", (pinfo.get("recent_form") or {}).get("minutes_trend", "STABLE"))).upper()
    status = str(injury.get("severity") or row.get("injury_status") or (pinfo.get("injury") or {}).get("status") or "ACTIVE").upper()
    projection_factor = sf(injury.get("projection_factor"), 1.0)
    projected_minutes = injury.get("projected_minutes")
    minutes_delta = injury.get("minutes_delta")
    history_games = int(sf(row.get("history_games", row.get("history_games_available", consensus.get("history_games", 0)))))

    if not pred:
        pred = line
    matchup_adj = (matchup_score - 60) * 0.015
    mean_before_injury = pred + matchup_adj
    mean = mean_before_injury * projection_factor
    if status in {"OUT", "DOUBTFUL"}:
        mean = 0.0
    sd = stat_volatility(stat, mean, role, minutes_trend, status)

    seed = sum(ord(ch) for ch in f"{player}|{stat}|{game}|{line}|{status}|{projection_factor}")
    rng = random.Random(seed)
    vals = []
    for _ in range(max(100, sims)):
        if status in {"OUT", "DOUBTFUL"}:
            value = 0.0
        else:
            minutes_shock = rng.gauss(0, 1) * (0.6 if role >= 70 else 1.0)
            value = rng.gauss(mean, sd) + minutes_shock
        vals.append(max(0, value))
    vals.sort()

    over_prob = sum(1 for value in vals if value > line) / len(vals)
    under_prob = sum(1 for value in vals if value < line) / len(vals)
    play_prob = over_prob if signal in {"OVER", "YES"} else under_prob if signal in {"UNDER", "NO"} else max(over_prob, under_prob)
    quantile = lambda p: vals[int(clamp(p, 0, 0.999) * (len(vals) - 1))]
    return clean_json({
        "player": player,
        "team": row.get("team"),
        "game": game,
        "stat": stat,
        "line": line,
        "projection_mean_before_injury": round(mean_before_injury, 2),
        "projection_mean": round(mean, 2),
        "projection_sd": round(sd, 2),
        "simulations": len(vals),
        "p05": round(quantile(0.05), 2), "p25": round(quantile(0.25), 2),
        "p50": round(quantile(0.50), 2), "p75": round(quantile(0.75), 2), "p95": round(quantile(0.95), 2),
        "over_probability": round(over_prob, 4),
        "under_probability": round(under_prob, 4),
        "recommended_side": "OVER" if over_prob >= under_prob else "UNDER",
        "model_signal": signal,
        "signal_probability": round(play_prob, 4),
        "edge_probability": round(play_prob - 0.5, 4),
        "matchup_score": matchup_score,
        "role_score": role,
        "injury_status": status,
        "injury_detail": injury.get("detail"),
        "injury_projection_factor": round(projection_factor, 4),
        "projected_minutes": projected_minutes,
        "minutes_delta": minutes_delta,
        "injury_blocked": status in {"OUT", "DOUBTFUL"},
        "minutes_trend": minutes_trend,
        "history_games": history_games,
        "risk_band": "BLOCKED" if status in {"OUT", "DOUBTFUL"} else "HIGH" if status in {"QUESTIONABLE", "UNKNOWN"} else "LOW" if sd <= 3.0 and play_prob >= 0.60 else "MED" if play_prob >= 0.55 else "HIGH",
    })


def build(target: str, sims: int) -> Dict[str, Any]:
    df, source_path = load_points(target)
    players = player_map()
    injuries = injury_map()
    matchups = matchup_map()
    consensus = consensus_map()
    rows, skipped = [], 0
    if not df.empty:
        for _, source_row in df.iterrows():
            try:
                rows.append(simulate_row(source_row.to_dict(), players, injuries, matchups, consensus, sims))
            except Exception as exc:
                skipped += 1
                print(f"WARN simulation skipped: {exc}")
    rows.sort(key=lambda row: (row.get("injury_blocked") is False, row["signal_probability"], -sf(row["projection_sd"])), reverse=True)
    report = clean_json({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "input_source": source_path,
        "summary": {
            "rows": len(rows), "source_rows": len(df), "skipped_rows": skipped,
            "simulations_per_row": max(100, sims),
            "low_risk": sum(1 for row in rows if row.get("risk_band") == "LOW"),
            "prob_60_plus": sum(1 for row in rows if sf(row.get("signal_probability")) >= 0.60 and not row.get("injury_blocked")),
            "history_5_plus": sum(1 for row in rows if sf(row.get("history_games")) >= 5),
            "injury_adjusted": sum(1 for row in rows if sf(row.get("injury_projection_factor"), 1) != 1),
            "injury_blocked": sum(1 for row in rows if row.get("injury_blocked")),
            "questionable": sum(1 for row in rows if row.get("injury_status") == "QUESTIONABLE"),
        },
        "top_simulations": [row for row in rows if not row.get("injury_blocked")][:50],
        "all_simulations": rows,
    })
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
