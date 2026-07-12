"""M08 matchup intelligence for player and game projections."""
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


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


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
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def lookup(rows_: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    return {norm(row.get(field)): row for row in rows_ if row.get(field)}


def game_key(row: dict[str, Any]) -> str:
    return str(row.get("game") or "").strip()


def rest_context(team: str, game: str, schedule: list[dict[str, Any]]) -> tuple[int | None, bool]:
    current = next((x for x in schedule if game_key(x) == game), None)
    if not current:
        return None, False
    rest_map = current.get("rest_days") if isinstance(current.get("rest_days"), dict) else {}
    rest = rest_map.get(team)
    if rest is None:
        for key in ("home_rest_days", "away_rest_days"):
            if team and team in game and current.get(key) is not None:
                rest = current.get(key); break
    days = int(sf(rest, -1)) if rest is not None else None
    return (days if days is not None and days >= 0 else None), days == 0


def team_strength(team: str, standings: dict[str, dict[str, Any]]) -> float:
    record = standings.get(norm(team), {})
    wins = sf(record.get("wins")); losses = sf(record.get("losses")); pct = sf(record.get("win_pct"), -1)
    if pct < 0:
        pct = wins / max(1, wins + losses)
    return clamp(pct or 0.5, 0.2, 0.8)


def build(target: str) -> dict[str, Any]:
    points = read_points(target)
    standings_rows = rows(load("data/warehouse/wnba_standings.json", []), "standings", "rows")
    standings = lookup(standings_rows, "team")
    player_rows = rows(load("data/warehouse/wnba_player_intelligence.json", {}), "players")
    players = lookup(player_rows, "player")
    schedule = rows(load("data/dashboard/wnba_master.json", {}), "games")
    pbp_games = {game_key(r): r for r in rows(load("data/warehouse/wnba_play_by_play_layer.json", {}), "games")}
    injury_rows = rows(load("data/warehouse/wnba_injury_intelligence.json", {}), "adjustments", "players")
    injuries = lookup(injury_rows, "player")
    output: list[dict[str, Any]] = []

    if not points.empty:
        for _, source in points.iterrows():
            row = source.to_dict()
            player = str(row.get("player") or "").strip()
            if not player:
                continue
            team = str(row.get("team") or "").strip(); opp = str(row.get("opp") or "").strip(); game = str(row.get("game") or "")
            stat = str(row.get("stat") or "").upper().replace("THREES", "3PM")
            intel = players.get(norm(player), {}); injury = injuries.get(norm(player), {})
            pace = pbp_games.get(game, {})
            opp_strength = team_strength(opp, standings)
            role = sf((intel.get("intelligence") or {}).get("role_score"), sf(row.get("role_score"), 50))
            recent = intel.get("recent_form", {}) if isinstance(intel.get("recent_form"), dict) else {}
            minutes_trend = str(recent.get("minutes_trend") or row.get("minutes_trend") or "STABLE").upper()
            performance_trend = str(recent.get("points_trend") or row.get("points_trend") or "STABLE").upper()
            rest_days, back_to_back = rest_context(team, game, schedule)
            home = bool(team and game.endswith(team))
            pace_value = sf(pace.get("pace_40"), 80.0)
            pace_adjustment = clamp((pace_value - 80.0) * 0.08, -4, 4)
            defense_adjustment = clamp((0.5 - opp_strength) * 18, -5.4, 5.4)
            rest_adjustment = -3.0 if back_to_back else 1.0 if rest_days is not None and rest_days >= 2 else 0.0
            venue_adjustment = 1.5 if home else -0.5
            trend_adjustment = (3 if minutes_trend == "UP" else -3 if minutes_trend == "DOWN" else 0)
            if stat in {"PTS", "PRA", "PA", "PR", "3PM"}:
                trend_adjustment += 2 if performance_trend == "UP" else -2 if performance_trend == "DOWN" else 0
            injury_status = str(injury.get("severity") or row.get("injury_status") or "ACTIVE").upper()
            injury_adjustment = -12 if injury_status in {"OUT", "DOUBTFUL"} else -5 if injury_status == "QUESTIONABLE" else -1 if injury_status == "PROBABLE" else 0
            components = {
                "opponent_defense": round(defense_adjustment, 2), "pace": round(pace_adjustment, 2),
                "rest": round(rest_adjustment, 2), "venue": round(venue_adjustment, 2),
                "trend": round(trend_adjustment, 2), "injury": round(injury_adjustment, 2),
                "role": round((role - 50) * 0.08, 2),
            }
            total_adjustment = sum(components.values())
            score = clamp(60 + total_adjustment, 0, 100)
            output.append({
                "player": player, "team": team, "opp": opp, "game": game, "stat": stat,
                "line": row.get("line"), "pred": row.get("pred"), "signal": row.get("signal"), "conf": row.get("conf"),
                "matchup_score": round(score, 1),
                "matchup_label": "EXCELLENT" if score >= 80 else "GOOD" if score >= 68 else "NEUTRAL" if score >= 52 else "DIFFICULT",
                "components": components, "total_adjustment": round(total_adjustment, 2),
                "opponent_strength": round(opp_strength, 3), "pace_40": pace.get("pace_40"),
                "pace_mode": pace.get("mode", "missing"), "pace_confidence": pace.get("data_confidence", 0),
                "rest_days": rest_days, "back_to_back": back_to_back, "home": home,
                "injury_status": injury_status, "role_score": round(role, 1),
                "minutes_trend": minutes_trend, "performance_trend": performance_trend,
                "reasoning": "; ".join(f"{k} {v:+.1f}" for k, v in components.items()),
                "source_trace": ["player_intelligence", "standings", "schedule", "play_by_play_layer", "injury_intelligence"],
            })

    output.sort(key=lambda x: x["matchup_score"], reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target, "status": "ok",
        "summary": {"rows": len(output), "excellent": sum(x["matchup_label"] == "EXCELLENT" for x in output),
                    "good": sum(x["matchup_label"] == "GOOD" for x in output), "back_to_back": sum(x["back_to_back"] for x in output)},
        "matchups": output,
    }
    os.makedirs("data/warehouse", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
    for path in ("data/warehouse/wnba_matchup_intelligence.json", "data/dashboard/wnba_matchup_intelligence.json"):
        json.dump(report, open(path, "w", encoding="utf-8"), indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args()
    print("M08 matchup intelligence built:", build(args.date)["summary"])


if __name__ == "__main__":
    main()
