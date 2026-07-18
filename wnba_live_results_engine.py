"""Event-driven WNBA game-status monitor and postgame trigger queue.

The monitor merges the active-slate master schedule with credit-free score feeds.
This prevents a stale/previous-day scoreboard response from making today's slate
look empty. Games are matched by game ID first, then normalized team pairing.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCORES = Path("data/wnba/scores.json")
MASTER = Path("data/dashboard/wnba_master.json")
STATE = Path("data/history/wnba_live_results_state.json")
OUTS = [Path("data/warehouse/wnba_live_results_engine.json"), Path("data/dashboard/wnba_live_results_engine.json")]
ET = ZoneInfo("America/New_York")


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(payload, path.open("w", encoding="utf-8"), indent=2, ensure_ascii=False)


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").replace(" at ", " @ ").split())


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
    candidates = [event.get("status"), event.get("status_detail"), event.get("state"), event.get("game_status")]
    status_type = event.get("status_type")
    if isinstance(status_type, dict): candidates += [status_type.get("name"), status_type.get("state"), status_type.get("description")]
    status = event.get("status")
    if isinstance(status, dict):
        typ = status.get("type") if isinstance(status.get("type"), dict) else {}
        candidates += [typ.get("name"), typ.get("state"), typ.get("description")]
    text = " ".join(str(x or "") for x in candidates).lower().replace("_", " ")
    if any(token in text for token in ("final", "completed", "post", "closed")): return "FINAL"
    if any(token in text for token in ("halftime", "half time")): return "HALFTIME"
    if any(token in text for token in ("in progress", "inprogress", "live", "quarter", "1st", "2nd", "3rd", "4th", "overtime")): return "LIVE"
    if any(token in text for token in ("postponed", "canceled", "cancelled", "suspended")): return "INACTIVE"
    return "SCHEDULED"


def event_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list): return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict): return []
    data = payload.get("data", payload)
    if isinstance(data, list): return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("events", "games", "scoreboard", "results", "scores"):
            rows = data.get(key)
            if isinstance(rows, list): return [x for x in rows if isinstance(x, dict)]
    return []


def teams(event: dict[str, Any]) -> tuple[str, str]:
    home_value = event.get("home_team") or event.get("home") or ""
    away_value = event.get("away_team") or event.get("away") or ""
    home = str(home_value.get("name") if isinstance(home_value, dict) else home_value)
    away = str(away_value.get("name") if isinstance(away_value, dict) else away_value)
    for competitor in event.get("competitors", []) or []:
        if not isinstance(competitor, dict): continue
        team = competitor.get("team") or {}
        name = (team.get("displayName") or team.get("name") or team.get("abbreviation")) if isinstance(team, dict) else str(team)
        side = str(competitor.get("home_away") or competitor.get("homeAway") or "").lower()
        if side == "home": home = str(name or home)
        elif side == "away": away = str(name or away)
    if (not away or not home) and " @ " in str(event.get("game") or ""):
        away, home = [x.strip() for x in str(event["game"]).split(" @ ", 1)]
    return away, home


def scores(event: dict[str, Any]) -> tuple[float | None, float | None]:
    def number(value: Any) -> float | None:
        try: return float(value)
        except Exception: return None
    away = number(event.get("away_score", event.get("away_points")))
    home = number(event.get("home_score", event.get("home_points")))
    for competitor in event.get("competitors", []) or []:
        if not isinstance(competitor, dict): continue
        side = str(competitor.get("home_away") or competitor.get("homeAway") or "").lower()
        value = number(competitor.get("score"))
        if side == "away": away = value
        elif side == "home": home = value
    return away, home


def normalize_event(event: dict[str, Any], target: str, source: str) -> dict[str, Any] | None:
    start = event.get("start_time") or event.get("date") or event.get("commence_time") or event.get("tip") or ""
    explicit_date = str(event.get("game_date") or event.get("target_date") or "")
    game_date = local_date(start) or explicit_date or target
    if game_date != target: return None
    away, home = teams(event)
    if not away or not home: return None
    away_score, home_score = scores(event)
    game_id = str(event.get("id") or event.get("game_id") or f"{target}|{norm(away)}|{norm(home)}")
    return {
        "game_id": game_id, "game_date": target, "game": f"{away} @ {home}",
        "away_team": away, "home_team": home, "start_time": start,
        "status": canonical_status(event), "status_detail": event.get("status_detail") or event.get("status"),
        "away_score": away_score, "home_score": home_score, "source": source,
    }


def master_games(target: str) -> list[dict[str, Any]]:
    payload = load(MASTER, {})
    rows = payload.get("games", []) if isinstance(payload, dict) else []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict): continue
        row_date = str(row.get("game_date") or "")
        bucket = str(row.get("bucket") or "")
        if row_date != target and bucket != "today": continue
        item = normalize_event(row, target, "master_schedule")
        if item: out.append(item)
    return out


def csv_score_events(target: str) -> list[dict[str, Any]]:
    out = []
    for path in (Path(f"data/raw/scores_{target}.csv"), Path("data/raw/scores_today.csv")):
        if not path.exists(): continue
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    item = normalize_event(dict(row), target, str(path))
                    if item: out.append(item)
        except Exception:
            continue
    return out


def merge_games(schedule: list[dict[str, Any]], observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    pair_to_id: dict[str, str] = {}
    for game in schedule:
        merged[game["game_id"]] = game
        pair_to_id[norm(game["game"])] = game["game_id"]
    rank = {"SCHEDULED": 0, "INACTIVE": 1, "LIVE": 2, "HALFTIME": 3, "FINAL": 4}
    for obs in observations:
        key = obs["game_id"] if obs["game_id"] in merged else pair_to_id.get(norm(obs["game"]))
        if not key:
            key = obs["game_id"]; merged[key] = obs; pair_to_id[norm(obs["game"])] = key; continue
        old = merged[key]
        if rank.get(obs["status"], 0) >= rank.get(old["status"], 0):
            merged[key] = {**old, **obs, "game_id": key, "start_time": obs.get("start_time") or old.get("start_time")}
    return sorted(merged.values(), key=lambda x: str(x.get("start_time") or x.get("game")))


def parse_games(target: str) -> list[dict[str, Any]]:
    observations = []
    for event in event_list(load(SCORES, {})):
        item = normalize_event(event, target, str(SCORES))
        if item: observations.append(item)
    observations.extend(csv_score_events(target))
    return merge_games(master_games(target), observations)


def build(target: str, mark_graded: list[str] | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    state = load(STATE, {"games": {}}); previous = state.get("games", {}) if isinstance(state, dict) else {}
    mark = set(mark_graded or []); games = parse_games(target); newly_final = []; queue = []; transitions = []
    current_ids = {game["game_id"] for game in games}
    for game in games:
        game_id = game["game_id"]; old = previous.get(game_id, {}) if isinstance(previous.get(game_id), dict) else {}
        old_status = old.get("status", "UNKNOWN"); graded = bool(old.get("graded", False)) or game_id in mark
        if old_status != game["status"]: transitions.append({"game_id": game_id, "game": game["game"], "from": old_status, "to": game["status"]})
        if game["status"] == "FINAL" and old_status != "FINAL" and not graded: newly_final.append(game)
        if game["status"] == "FINAL" and not graded: queue.append(game)
        previous[game_id] = {**game, "last_seen_utc": now, "graded": graded, "graded_at_utc": now if game_id in mark else old.get("graded_at_utc")}
    for game_id in list(previous):
        if game_id not in current_ids and previous[game_id].get("status") != "FINAL": previous.pop(game_id, None)
    dump(STATE, {"updated_at_utc": now, "target_date": target, "games": previous})
    summary = {
        "games": len(games), "scheduled": sum(g["status"] == "SCHEDULED" for g in games),
        "live": sum(g["status"] in {"LIVE", "HALFTIME"} for g in games), "final": sum(g["status"] == "FINAL" for g in games),
        "newly_final": len(newly_final), "queued": len(queue), "graded_total": sum(bool(x.get("graded")) for x in previous.values()),
    }
    payload = {
        "generated_at_utc": now, "target_date": target, "status": "grading_required" if queue else "watching",
        "run_grading": bool(queue), "summary": summary, "games": games, "transitions": transitions,
        "newly_final_games": newly_final, "grading_queue": queue,
        "policy": {"odds_api_used": False, "poll_interval_minutes": 15, "grade_once_per_game": True, "trigger": "new or ungraded FINAL game", "schedule_fallback": "active-slate master"},
    }
    for path in OUTS: dump(path, payload)
    print(json.dumps(payload, separators=(",", ":"))); return payload


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); parser.add_argument("--mark-graded", action="append", default=[])
    args = parser.parse_args(); build(args.date, args.mark_graded)


if __name__ == "__main__": main()
