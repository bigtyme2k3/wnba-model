"""Game-level WNBA spread and totals projection model.

Consumes independent game score projections from matchup intelligence, compares
those projections with sportsbook lines, and never substitutes the market line
as the model forecast.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from typing import Any


def load(path: str, default: Any) -> Any:
    try:
        if os.path.exists(path):
            return json.load(open(path, encoding="utf-8"))
    except Exception:
        pass
    return default


def num(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def game_name(row: dict[str, Any]) -> str:
    if row.get("game"):
        return str(row["game"])
    away = row.get("away_team") or (row.get("away") or {}).get("name")
    home = row.get("home_team") or (row.get("home") or {}).get("name")
    return " @ ".join(str(x) for x in (away, home) if x)


def teams(name: str) -> list[str]:
    return [part.strip() for part in str(name or "").split(" @ ") if part.strip()]


def same_game(left: str, right: str) -> bool:
    if left == right:
        return True
    a, b = teams(left), teams(right)
    return len(a) == 2 and len(b) == 2 and set(a) == set(b)


def rows(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [x for x in payload[key] if isinstance(x, dict)]
    return []


def probability_from_edge(edge: float, scale: float) -> float:
    return clamp(0.5 + 0.5 * math.tanh(abs(edge) / scale), 0.02, 0.98)


def build(target: str) -> dict[str, Any]:
    master = load("data/dashboard/wnba_master.json", {})
    matchup = load("data/dashboard/wnba_matchup_intelligence.json", {})
    master_games = rows(master, "games")
    games = [g for g in master_games if str(g.get("bucket") or "today") == "today"] or master_games
    game_projections = rows(matchup, "games")
    output = []

    for game in games:
        name = game_name(game)
        model = next((r for r in game_projections if same_game(game_name(r), name)), {})
        market_spread = num(game.get("spread", game.get("spread_home")))
        market_total = num(game.get("total"))
        projected_margin = num(model.get("projected_margin"))
        projected_total = num(model.get("projected_total"))
        projected_home_score = num(model.get("projected_home_score"))
        projected_away_score = num(model.get("projected_away_score"))
        pair = teams(name); away = pair[0] if len(pair) == 2 else "Away"; home = pair[1] if len(pair) == 2 else "Home"

        # Sportsbook home spread -5.5 represents a market-implied home margin of
        # +5.5, hence the sign inversion here.
        market_margin = -market_spread if market_spread is not None else None
        spread_edge = projected_margin - market_margin if projected_margin is not None and market_margin is not None else None
        total_edge = projected_total - market_total if projected_total is not None and market_total is not None else None
        spread_probability = probability_from_edge(spread_edge, 7.0) if spread_edge is not None else None
        total_probability = probability_from_edge(total_edge, 12.0) if total_edge is not None else None
        spread_pick = home if spread_edge is not None and spread_edge > 0 else away if spread_edge is not None and spread_edge < 0 else "PASS"
        total_pick = "OVER" if total_edge is not None and total_edge > 0 else "UNDER" if total_edge is not None and total_edge < 0 else "PASS"
        spread_recommendation = spread_pick if spread_edge is not None and abs(spread_edge) >= 1.5 else "PASS"
        total_recommendation = total_pick if total_edge is not None and abs(total_edge) >= 2.5 else "PASS"
        picks = []
        if spread_recommendation != "PASS":
            picks.append({"market": "SPREAD", "pick": spread_recommendation, "line": market_spread, "edge": round(spread_edge, 2), "probability": round(spread_probability, 4)})
        if total_recommendation != "PASS":
            picks.append({"market": "TOTAL", "pick": total_recommendation, "line": market_total, "edge": round(total_edge, 2), "probability": round(total_probability, 4)})

        output.append({
            "game": name, "target_date": target,
            "start_time": game.get("start_time") or game.get("commence_time") or game.get("tip"),
            "away_team": away, "home_team": home,
            "projected_away_score": projected_away_score, "projected_home_score": projected_home_score,
            "market_spread": market_spread, "market_margin": market_margin,
            "projected_margin": projected_margin, "spread_edge": round(spread_edge, 2) if spread_edge is not None else None,
            "spread_pick": spread_pick, "spread_recommendation": spread_recommendation,
            "spread_probability": round(spread_probability, 4) if spread_probability is not None else None,
            "spread_source": model.get("projection_source", "unavailable") if projected_margin is not None else "unavailable",
            "market_total": market_total, "projected_total": projected_total,
            "total_edge": round(total_edge, 2) if total_edge is not None else None,
            "total_pick": total_pick, "total_recommendation": total_recommendation,
            "total_probability": round(total_probability, 4) if total_probability is not None else None,
            "total_source": model.get("projection_source", "unavailable") if projected_total is not None else "unavailable",
            "top_picks": sorted(picks, key=lambda x: x["probability"], reverse=True)[:3],
            "model_available": projected_margin is not None and projected_total is not None,
        })

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target,
        "status": "ok" if any(x["model_available"] for x in output) else "degraded",
        "summary": {
            "games": len(output),
            "spread_predictions": sum(x["projected_margin"] is not None for x in output),
            "total_predictions": sum(x["projected_total"] is not None for x in output),
            "spread_recommendations": sum(x["spread_recommendation"] != "PASS" for x in output),
            "total_recommendations": sum(x["total_recommendation"] != "PASS" for x in output),
            "unavailable": sum(not x["model_available"] for x in output),
        },
        "games": output,
    }
    os.makedirs("data/warehouse", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
    for path in ("data/warehouse/wnba_game_market_model.json", "data/dashboard/wnba_game_market_model.json"):
        json.dump(report, open(path, "w", encoding="utf-8"), indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args()
    print("Game market model built:", build(args.date)["summary"])


if __name__ == "__main__":
    main()
