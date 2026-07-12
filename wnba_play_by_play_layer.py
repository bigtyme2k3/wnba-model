"""M07 play-by-play, possessions, pace, and lineup context layer.

The layer normalizes event feeds when available and degrades explicitly to a
boxscore/schedule baseline when play-by-play is missing. Fallback rows are never
presented as observed event data.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

EVENT_TYPES = {"SHOT_MADE", "SHOT_MISSED", "FREE_THROW", "REBOUND", "TURNOVER", "FOUL", "SUBSTITUTION", "TIMEOUT", "PERIOD_START", "PERIOD_END", "OTHER"}


def load(path: str, default: Any) -> Any:
    try:
        if os.path.exists(path):
            return json.load(open(path, encoding="utf-8"))
    except Exception:
        pass
    return default


def num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def game_name(row: dict[str, Any]) -> str:
    if row.get("game"):
        return str(row["game"])
    away = row.get("away_team") or (row.get("away") or {}).get("name")
    home = row.get("home_team") or (row.get("home") or {}).get("name")
    return " @ ".join(str(x) for x in (away, home) if x)


def normalize_type(row: dict[str, Any]) -> str:
    raw = str(row.get("event_type") or row.get("type") or row.get("play_type") or row.get("description") or "").upper()
    if "SUB" in raw: return "SUBSTITUTION"
    if "TURNOVER" in raw: return "TURNOVER"
    if "REBOUND" in raw: return "REBOUND"
    if "FREE THROW" in raw or "FREETHROW" in raw: return "FREE_THROW"
    if "MISS" in raw: return "SHOT_MISSED"
    if "MAKE" in raw or "MADE" in raw: return "SHOT_MADE"
    if "FOUL" in raw: return "FOUL"
    if "TIMEOUT" in raw: return "TIMEOUT"
    if "START" in raw and ("PERIOD" in raw or "QUARTER" in raw): return "PERIOD_START"
    if "END" in raw and ("PERIOD" in raw or "QUARTER" in raw): return "PERIOD_END"
    return "OTHER"


def normalize_event(row: dict[str, Any], index: int, default_game: str = "") -> dict[str, Any]:
    event_type = normalize_type(row)
    return {
        "event_id": str(row.get("event_id") or row.get("id") or index),
        "game": game_name(row) or default_game,
        "period": int(num(row.get("period") or row.get("quarter"), 0)),
        "clock": str(row.get("clock") or row.get("time") or ""),
        "team": row.get("team") or row.get("team_name"),
        "player": row.get("player") or row.get("athlete") or row.get("player_name"),
        "event_type": event_type if event_type in EVENT_TYPES else "OTHER",
        "points": int(num(row.get("points"), 0)),
        "description": str(row.get("description") or row.get("text") or ""),
        "source": str(row.get("source") or "raw_play_by_play"),
    }


def possessions_from_events(events: list[dict[str, Any]]) -> int:
    turnovers = sum(e["event_type"] == "TURNOVER" for e in events)
    made = sum(e["event_type"] == "SHOT_MADE" for e in events)
    defensive_rebounds = sum(e["event_type"] == "REBOUND" and "OFF" not in e.get("description", "").upper() for e in events)
    period_ends = sum(e["event_type"] == "PERIOD_END" for e in events)
    return max(0, turnovers + made + defensive_rebounds + period_ends)


def lineup_stints(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    substitutions = [e for e in events if e["event_type"] == "SUBSTITUTION"]
    return [{
        "game": e["game"], "period": e["period"], "clock": e["clock"], "team": e.get("team"),
        "description": e.get("description"), "observed": True,
    } for e in substitutions]


def boxscore_possessions(row: dict[str, Any]) -> float | None:
    fga = num(row.get("fga"), -1); fta = num(row.get("fta"), -1); orb = num(row.get("orb"), -1); tov = num(row.get("tov"), -1)
    if min(fga, fta, orb, tov) < 0:
        return None
    return round(fga + 0.44 * fta - orb + tov, 2)


def build(target: str) -> dict[str, Any]:
    raw_candidates = [
        "data/raw/wnba_play_by_play.json", "data/warehouse/wnba_play_by_play_raw.json",
        "data/wnba/play_by_play.json", "data/wnba/pbp.json",
    ]
    raw_payload: Any = {}
    source_file = None
    for path in raw_candidates:
        if Path(path).exists():
            payload = load(path, {})
            candidate_rows = rows(payload, "events", "plays", "play_by_play", "items")
            if candidate_rows:
                raw_payload = payload; source_file = path; break

    raw_events = rows(raw_payload, "events", "plays", "play_by_play", "items")
    normalized = [normalize_event(row, index) for index, row in enumerate(raw_events)]
    normalized = [e for e in normalized if e["game"]]
    games_payload = load("data/dashboard/wnba_master.json", {})
    schedule_games = rows(games_payload, "games")
    boxscores = rows(load("data/warehouse/wnba_boxscores.json", {}), "games", "boxscores", "rows")

    by_game: dict[str, list[dict[str, Any]]] = {}
    for event in normalized:
        by_game.setdefault(event["game"], []).append(event)

    game_rows = []
    known_games = {game_name(g): g for g in schedule_games if game_name(g)}
    for name in sorted(set(known_games) | set(by_game)):
        events = by_game.get(name, [])
        schedule = known_games.get(name, {})
        related_box = [b for b in boxscores if game_name(b) == name]
        if events:
            possessions = possessions_from_events(events)
            periods = max([e["period"] for e in events] or [4])
            minutes = 10 * max(4, periods)
            pace = round(possessions * 40 / max(minutes, 1), 2)
            mode = "observed_play_by_play"
            confidence = 1.0 if len(events) >= 100 else 0.8 if len(events) >= 40 else 0.65
        else:
            estimates = [boxscore_possessions(b) for b in related_box]
            estimates = [x for x in estimates if x is not None]
            possessions = round(sum(estimates) / len(estimates), 2) if estimates else None
            pace = possessions
            mode = "boxscore_estimate" if estimates else "schedule_baseline"
            confidence = 0.7 if estimates else 0.35
        game_rows.append({
            "game": name,
            "target_date": target,
            "start_time": schedule.get("start_time") or schedule.get("commence_time"),
            "mode": mode,
            "observed_event_count": len(events),
            "possessions": possessions,
            "pace_40": pace,
            "lineup_stints": lineup_stints(events),
            "substitution_count": sum(e["event_type"] == "SUBSTITUTION" for e in events),
            "data_confidence": confidence,
            "fallback_used": mode != "observed_play_by_play",
            "quality_flags": (["NO_PLAY_BY_PLAY"] if not events else []) + (["NO_POSSESSION_ESTIMATE"] if possessions is None else []),
        })

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "source_file": source_file,
        "status": "ok",
        "summary": {
            "games": len(game_rows), "events": len(normalized),
            "observed_games": sum(g["mode"] == "observed_play_by_play" for g in game_rows),
            "fallback_games": sum(g["fallback_used"] for g in game_rows),
            "lineup_stints": sum(len(g["lineup_stints"]) for g in game_rows),
        },
        "events": normalized,
        "games": game_rows,
    }
    os.makedirs("data/warehouse", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
    for path in ("data/warehouse/wnba_play_by_play_layer.json", "data/dashboard/wnba_play_by_play_layer.json"):
        json.dump(report, open(path, "w", encoding="utf-8"), indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args()
    print("M07 play-by-play layer built:", build(args.date)["summary"])


if __name__ == "__main__":
    main()
