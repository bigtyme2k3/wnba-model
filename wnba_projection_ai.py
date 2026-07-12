"""M09 explainable player projection engine."""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd


def load(path: str, default: Any) -> Any:
    try:
        if os.path.exists(path):
            return json.load(open(path, encoding="utf-8"))
    except Exception:
        pass
    return default


def sf(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("player") or "").strip().lower(), str(row.get("game") or "").strip().lower(), str(row.get("stat") or "").strip().upper().replace("THREES", "3PM"))


def read_points(target: str) -> pd.DataFrame:
    for path in (f"data/raw/player_points_{target}.csv", "data/raw/player_points_today.csv"):
        try:
            if os.path.exists(path):
                return pd.read_csv(path)
        except Exception:
            pass
    return pd.DataFrame()


def rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key_name in keys:
            value = payload.get(key_name)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def recent_values(row: dict[str, Any]) -> list[float]:
    for field in ("last10", "recent", "history", "recent_values"):
        value = row.get(field)
        if isinstance(value, list):
            numbers = [sf(x, math.nan) for x in value]
            return [x for x in numbers if math.isfinite(x)]
    return []


def stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1))


def build(target: str) -> dict[str, Any]:
    points = read_points(target)
    sim_map = {key(r): r for r in rows(load("data/warehouse/wnba_monte_carlo_engine.json", {}), "all_simulations", "simulations")}
    matchup_map = {key(r): r for r in rows(load("data/warehouse/wnba_matchup_intelligence.json", {}), "matchups")}
    player_map = {str(r.get("player") or "").strip().lower(): r for r in rows(load("data/warehouse/wnba_player_intelligence.json", {}), "players")}
    injury_map = {str(r.get("player") or "").strip().lower(): r for r in rows(load("data/warehouse/wnba_injury_intelligence.json", {}), "adjustments", "players")}
    output: list[dict[str, Any]] = []

    if not points.empty:
        for _, source in points.iterrows():
            row = source.to_dict(); row["stat"] = str(row.get("stat") or "").upper().replace("THREES", "3PM")
            player = str(row.get("player") or "").strip()
            if not player:
                continue
            simulation = sim_map.get(key(row), {}); matchup = matchup_map.get(key(row), {})
            player_intel = player_map.get(player.lower(), {}); injury = injury_map.get(player.lower(), {})
            line = sf(row.get("line")); base = sf(row.get("pred"), line)
            recent = recent_values(row)
            recent_mean = sum(recent[-5:]) / len(recent[-5:]) if recent else base
            season_mean = sf(row.get("season_avg"), sf(row.get("avg"), base))
            sim_median = sf(simulation.get("p50"), base)
            minutes = sf(row.get("projected_minutes"), sf((player_intel.get("recent_form") or {}).get("minutes_avg"), sf(row.get("minutes"), 30)))
            minutes_baseline = max(1.0, sf(row.get("minutes_baseline"), minutes))
            minutes_factor = clamp(minutes / minutes_baseline, 0.6, 1.25)
            usage_factor = clamp(sf(row.get("usage_factor"), 1.0), 0.75, 1.25)
            baseline = base * 0.35 + recent_mean * 0.25 + season_mean * 0.20 + sim_median * 0.20
            matchup_adjustment = sf(matchup.get("total_adjustment"), (sf(matchup.get("matchup_score"), 60) - 60) * 0.08)
            pace_adjustment = sf((matchup.get("components") or {}).get("pace"), 0.0)
            injury_status = str(injury.get("severity") or matchup.get("injury_status") or row.get("injury_status") or "ACTIVE").upper()
            injury_factor = sf(injury.get("projection_factor"), 0.0)
            if injury_factor == 0.0:
                injury_factor = 0.0 if injury_status == "ACTIVE" else -0.02 if injury_status == "PROBABLE" else -0.08 if injury_status == "QUESTIONABLE" else -0.25
            injury_adjustment = baseline * injury_factor
            role_adjustment = baseline * (minutes_factor - 1) + baseline * (usage_factor - 1)
            final = max(0.0, baseline + matchup_adjustment + pace_adjustment + injury_adjustment + role_adjustment)
            variance = max(stddev(recent), sf(simulation.get("stddev"), 0), max(1.0, final * 0.12))
            lower = max(0.0, final - 1.28 * variance); upper = final + 1.28 * variance
            confidence = clamp(100 - min(45, variance / max(final, 1) * 100) - (10 if len(recent) < 5 else 0) - (8 if injury_status in {"QUESTIONABLE", "UNKNOWN"} else 0), 25, 95)
            contributions = {
                "baseline": round(baseline, 2), "matchup": round(matchup_adjustment, 2), "pace": round(pace_adjustment, 2),
                "injury": round(injury_adjustment, 2), "minutes_usage": round(role_adjustment, 2),
            }
            output.append({
                "player": player, "team": row.get("team"), "game": row.get("game"), "stat": row.get("stat"), "line": row.get("line"),
                "signal": row.get("signal"), "base_projection": round(base, 2), "recent_mean": round(recent_mean, 2),
                "season_mean": round(season_mean, 2), "sim_median": round(sim_median, 2), "projected_minutes": round(minutes, 1),
                "minutes_factor": round(minutes_factor, 3), "usage_factor": round(usage_factor, 3),
                "matchup_score": matchup.get("matchup_score"), "injury_status": injury_status,
                "ai_projection": round(final, 2), "ai_edge": round(final - line, 2),
                "variance": round(variance, 2), "interval_80": [round(lower, 2), round(upper, 2)],
                "projection_confidence": round(confidence, 1), "feature_contributions": contributions,
                "projection_source": "weighted_baseline+monte_carlo+matchup+pace+minutes+usage+injury",
                "source_trace": ["player_points", "player_intelligence", "monte_carlo", "matchup_intelligence", "injury_intelligence"],
            })

    output.sort(key=lambda x: abs(sf(x.get("ai_edge"))), reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target, "status": "ok",
        "summary": {"rows": len(output), "strong_edges": sum(abs(sf(x.get("ai_edge"))) >= 2 for x in output),
                    "high_confidence": sum(sf(x.get("projection_confidence")) >= 75 for x in output)},
        "projections": output,
    }
    os.makedirs("data/warehouse", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
    for path in ("data/warehouse/wnba_projection_ai.json", "data/dashboard/wnba_projection_ai.json"):
        json.dump(report, open(path, "w", encoding="utf-8"), indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args()
    print("M09 projection engine built:", build(args.date)["summary"])


if __name__ == "__main__":
    main()
