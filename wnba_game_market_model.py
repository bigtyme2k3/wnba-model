"""Game-level WNBA spread and totals projection model.

Builds one auditable market projection per scheduled game. It prefers upstream
matchup/projection fields and falls back conservatively to the market line when
an upstream estimate is unavailable. No synthetic betting edge is invented.
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


def rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def first_number(items: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:
    for item in items:
        for key in keys:
            value = num(item.get(key))
            if value is not None:
                return value
    return None


def probability_from_edge(edge: float, scale: float) -> float:
    return clamp(0.5 + 0.5 * math.tanh(edge / scale), 0.02, 0.98)


def build(target: str) -> dict[str, Any]:
    master = load("data/dashboard/wnba_master.json", {})
    matchup = load("data/dashboard/wnba_matchup_intelligence.json", {})
    projection = load("data/dashboard/wnba_projection_ai.json", {})
    master_games = rows(master, "games")
    games = [g for g in master_games if str(g.get("bucket") or "today") == "today"] or master_games
    matchup_rows = rows(matchup, "matchups", "games", "rows")
    projection_rows = rows(projection, "games", "projections", "rows")
    output = []

    for game in games:
        name = game_name(game)
        related = [r for r in matchup_rows + projection_rows if same_game(game_name(r), name)]
        market_spread = num(game.get("spread", game.get("spread_home")))
        market_total = num(game.get("total"))
        projected_margin = first_number(related, ("projected_margin", "predicted_margin", "model_spread", "spread_projection"))
        projected_total = first_number(related, ("projected_total", "predicted_total", "model_total", "total_projection"))

        spread_source = "upstream_projection"
        total_source = "upstream_projection"
        if projected_margin is None:
            projected_margin = market_spread
            spread_source = "market_baseline" if market_spread is not None else "unavailable"
        if projected_total is None:
            projected_total = market_total
            total_source = "market_baseline" if market_total is not None else "unavailable"

        spread_edge = (projected_margin - market_spread) if projected_margin is not None and market_spread is not None else 0.0
        total_edge = (projected_total - market_total) if projected_total is not None and market_total is not None else 0.0
        spread_probability = probability_from_edge(abs(spread_edge), 7.0) if spread_source == "upstream_projection" else 0.5
        total_probability = probability_from_edge(abs(total_edge), 12.0) if total_source == "upstream_projection" else 0.5
        pair = teams(name)
        home = pair[1] if len(pair) == 2 else "Home"
        away = pair[0] if len(pair) == 2 else "Away"
        spread_pick = None
        if market_spread is not None and projected_margin is not None and spread_source == "upstream_projection":
            spread_pick = home if spread_edge >= 0 else away
        total_pick = None
        if market_total is not None and projected_total is not None and total_source == "upstream_projection":
            total_pick = "OVER" if total_edge > 0 else "UNDER" if total_edge < 0 else "PASS"

        picks = []
        if spread_pick and abs(spread_edge) >= 1.5:
            picks.append({"market": "SPREAD", "pick": spread_pick, "edge": round(spread_edge, 2), "probability": round(spread_probability, 4)})
        if total_pick and total_pick != "PASS" and abs(total_edge) >= 2.5:
            picks.append({"market": "TOTAL", "pick": total_pick, "edge": round(total_edge, 2), "probability": round(total_probability, 4)})

        output.append({
            "game": name,
            "target_date": target,
            "start_time": game.get("start_time") or game.get("commence_time") or game.get("tip"),
            "market_spread": market_spread,
            "projected_margin": projected_margin,
            "spread_edge": round(spread_edge, 2),
            "spread_pick": spread_pick or "PASS",
            "spread_probability": round(spread_probability, 4),
            "spread_source": spread_source,
            "market_total": market_total,
            "projected_total": projected_total,
            "total_edge": round(total_edge, 2),
            "total_pick": total_pick or "PASS",
            "total_probability": round(total_probability, 4),
            "total_source": total_source,
            "top_picks": sorted(picks, key=lambda x: x["probability"], reverse=True)[:3],
        })

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "summary": {
            "games": len(output),
            "spread_predictions": sum(x["spread_source"] == "upstream_projection" for x in output),
            "total_predictions": sum(x["total_source"] == "upstream_projection" for x in output),
            "market_baselines": sum(x["spread_source"] == "market_baseline" or x["total_source"] == "market_baseline" for x in output),
        },
        "games": output,
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in ("data/warehouse/wnba_game_market_model.json", "data/dashboard/wnba_game_market_model.json"):
        json.dump(report, open(path, "w", encoding="utf-8"), indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    print("Game market model built:", build(args.date)["summary"])


if __name__ == "__main__":
    main()
