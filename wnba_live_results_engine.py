"""Event-driven WNBA game-status monitor and postgame trigger queue.

This engine uses the non-odds schedule/score feed in data/wnba/scores.json. It
persists the last observed status for every game, emits newly-final games once,
and tracks whether each final game has completed the grading pipeline.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCORES = Path("data/wnba/scores.json")
STATE = Path("data/history/wnba_live_results_state.json")
OUTS = [
    Path("data/warehouse/wnba_live_results_engine.json"),
    Path("data/dashboard/wnba_live_results_engine.json"),
]
ET = ZoneInfo("America/New_York")


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(payload, path.open("w", encoding="utf-8"), indent=2, ensure_ascii=False)


def local_date(value: Any) -> str:
    try:
        text = str(value or "").replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ET).date().isoformat()
    except Exception:
        return ""


def canonical_status(event: dict[str, Any]) -> str:
    candidates = [
        event.get("status"), event.get("status_detail"), event.get("state"),
        (event.get("status_type") or {}).get("name") if isinstance(event.get("status_type"), dict) else None,
        (event.get("status_type") or {}).get("state") if isinstance(event.get("status_type"), dict) else None,
        (event.get("status") or {}).get("type", {}).get("name") if isinstance(event.get("status"), dict) else None,
        (event.get("status") or {}).get("type", {}).get("state") if isinstance(event.get("status"), dict) else None,
    ]
    text = " ".join(str(x or "") for x in candidates).lower()
    if any(token in text for token in ("final", "completed", "post", "closed")):
        return "FINAL"
    if any(token in text for token in ("halftime", "half")):
        return "HALFTIME"
    if any(token in text for token in ("in progress", "live", "quarter", "q1", "q2", "q3", "q4", "overtime")):
        return "LIVE"
    if any(token in text for token in ("postponed", "canceled", "cancelled", "suspended")):
        return "INACTIVE"
    return "SCHEDULED"


def event_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("events", "games", "scoreboard"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [x for x in rows if isinstance(x, dict)]
    return []


def teams(event: dict[str, Any]) -> tuple[str, str]:
    home = str(event.get("home_team") or event.get("home") or "")
    away = str(event.get("away_team") or event.get("away") or "")
    for competitor in event.get("competitors", []) or []:
        if not isinstance(competitor, dict):
            continue
        team = competitor.get("team") or {}
        name = team.get("displayName") or team.get("name") or team.get("abbreviation") if isinstance(team, dict) else str(team)
        side = str(competitor.get("home_away") or competitor.get("homeAway") or "").lower()
        if side == "home": home = str(name or home)
        elif side == "away": away = str(name or away)
    return away, home


def parse_games(target: str) -> list[dict[str, Any]]:
    payload = load(SCORES, {})
    games: list[dict[str, Any]] = []
    for event in event_list(payload):
        start = event.get("start_time") or event.get("date") or event.get("commence_time") or ""
        game_date = local_date(start) or str(event.get("game_date") or target)
        if game_date != target:
            continue
        away, home = teams(event)
        game_id = str(event.get("id") or event.get("game_id") or f"{target}|{away}|{home}")
        games.append({
            "game_id": game_id,
            "game_date": target,
            "game": f"{away} @ {home}" if away and home else str(event.get("name") or game_id),
            "away_team": away,
            "home_team": home,
            "start_time": start,
            "status": canonical_status(event),
            "status_detail": event.get("status_detail") or event.get("status"),
        })
    return games


def build(target: str, mark_graded: list[str] | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    state = load(STATE, {"games": {}})
    previous = state.get("games", {}) if isinstance(state, dict) else {}
    mark = set(mark_graded or [])
    games = parse_games(target)
    newly_final: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []

    current_ids = {game["game_id"] for game in games}
    for game in games:
        game_id = game["game_id"]
        old = previous.get(game_id, {}) if isinstance(previous.get(game_id), dict) else {}
        old_status = old.get("status", "UNKNOWN")
        graded = bool(old.get("graded", False)) or game_id in mark
        if old_status != game["status"]:
            transitions.append({"game_id": game_id, "game": game["game"], "from": old_status, "to": game["status"]})
        if game["status"] == "FINAL" and old_status != "FINAL" and not graded:
            newly_final.append(game)
        if game["status"] == "FINAL" and not graded:
            queue.append(game)
        previous[game_id] = {
            **game,
            "last_seen_utc": now,
            "graded": graded,
            "graded_at_utc": now if game_id in mark else old.get("graded_at_utc"),
        }

    # Keep historical final/graded records while pruning stale non-final entries.
    for game_id in list(previous):
        if game_id not in current_ids and previous[game_id].get("status") != "FINAL":
            previous.pop(game_id, None)

    state_payload = {"updated_at_utc": now, "target_date": target, "games": previous}
    dump(STATE, state_payload)
    summary = {
        "games": len(games),
        "scheduled": sum(g["status"] == "SCHEDULED" for g in games),
        "live": sum(g["status"] in {"LIVE", "HALFTIME"} for g in games),
        "final": sum(g["status"] == "FINAL" for g in games),
        "newly_final": len(newly_final),
        "queued": len(queue),
        "graded_total": sum(bool(x.get("graded")) for x in previous.values()),
    }
    payload = {
        "generated_at_utc": now,
        "target_date": target,
        "status": "grading_required" if queue else "watching",
        "run_grading": bool(queue),
        "summary": summary,
        "games": games,
        "transitions": transitions,
        "newly_final_games": newly_final,
        "grading_queue": queue,
        "policy": {
            "odds_api_used": False,
            "poll_interval_minutes": 15,
            "grade_once_per_game": True,
            "trigger": "new or ungraded FINAL game",
        },
    }
    for path in OUTS:
        dump(path, payload)
    print(json.dumps(payload, separators=(",", ":")))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--mark-graded", action="append", default=[])
    args = parser.parse_args()
    build(args.date, args.mark_graded)


if __name__ == "__main__":
    main()
