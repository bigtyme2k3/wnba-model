"""Collect current-season ESPN WNBA play-by-play and backfill player quarter splits.

The collector uses completed games only. It stores normalized event rows, then
updates matching player-game warehouse records with quarter points, made/attempted
free throws, and foul categories. Existing boxscore totals remain authoritative
for reconciliation; mismatches are flagged rather than overwritten silently.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"
HEADERS = {"User-Agent": "Mozilla/5.0 (WNBA research project)"}
RAW = Path("data/raw/wnba_historical_play_by_play.json")
WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")
DASHBOARD = Path("data/dashboard/wnba_player_game_logs.json")


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def num(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(url, headers=HEADERS, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def scoreboard(day: date) -> list[dict[str, Any]]:
    payload = fetch_json(f"{ESPN_BASE}/scoreboard", {"dates": day.strftime("%Y%m%d"), "limit": 50})
    return [e for e in payload.get("events", []) if isinstance(e, dict)]


def summary(game_id: str) -> dict[str, Any]:
    return fetch_json(f"{ESPN_BASE}/summary", {"event": game_id})


def team_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    competition = payload.get("header", {}).get("competitions", [{}])[0]
    for item in competition.get("competitors", []):
        team = item.get("team", {})
        team_id = str(team.get("id") or "")
        if team_id:
            out[team_id] = {
                "name": team.get("displayName") or team.get("name"),
                "abbr": team.get("abbreviation"),
                "home_away": item.get("homeAway"),
            }
    return out


def event_type(play: dict[str, Any]) -> str:
    text = str(play.get("text") or "").lower()
    type_text = str(play.get("type", {}).get("text") or "").lower()
    joined = f"{type_text} {text}"
    if "free throw" in joined:
        return "FREE_THROW"
    if any(token in joined for token in ("foul", "technical", "flagrant")):
        return "FOUL"
    if any(token in joined for token in ("substitution", "enters the game", "leaves the game")):
        return "SUBSTITUTION"
    if play.get("scoringPlay"):
        return "SHOT_MADE"
    if any(token in joined for token in ("misses", "missed")):
        return "SHOT_MISSED"
    if "rebound" in joined:
        return "REBOUND"
    if "turnover" in joined:
        return "TURNOVER"
    return "OTHER"


def player_from_play(play: dict[str, Any]) -> tuple[str | None, str | None]:
    participants = play.get("participants") if isinstance(play.get("participants"), list) else []
    for participant in participants:
        athlete = participant.get("athlete", {}) if isinstance(participant, dict) else {}
        name = athlete.get("displayName") or athlete.get("shortName")
        if name:
            return str(name), str(athlete.get("id") or "") or None
    text = str(play.get("text") or "")
    match = re.match(r"^([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})", text)
    return (match.group(1), None) if match else (None, None)


def normalized_events(payload: dict[str, Any], game_date: str) -> list[dict[str, Any]]:
    competition = payload.get("header", {}).get("competitions", [{}])[0]
    game_id = str(competition.get("id") or "")
    teams = team_map(payload)
    names = [v.get("name") for v in teams.values() if v.get("name")]
    game = " @ ".join(names[:2]) if len(names) >= 2 else game_id
    output: list[dict[str, Any]] = []
    for play in payload.get("plays", []):
        if not isinstance(play, dict):
            continue
        player, player_id = player_from_play(play)
        team_id = str(play.get("team", {}).get("id") or "")
        team = teams.get(team_id, {})
        period = int(num(play.get("period", {}).get("number"), 0) or 0)
        value = int(num(play.get("scoreValue"), 0) or 0)
        output.append({
            "game_id": game_id,
            "game": game,
            "game_date": game_date,
            "play_id": str(play.get("id") or ""),
            "period": period,
            "clock": play.get("clock", {}).get("displayValue"),
            "event_type": event_type(play),
            "description": play.get("text"),
            "player": player,
            "player_id": player_id,
            "team_id": team_id or None,
            "team": team.get("name"),
            "team_abbr": team.get("abbr"),
            "home_away": team.get("home_away"),
            "points": value,
            "scoring_play": bool(play.get("scoringPlay")),
            "source": "espn_summary_plays",
        })
    return output


def collect(season: int) -> dict[str, Any]:
    today = date.today()
    start = date(season, 5, 1)
    end = min(date(season, 10, 31), today)
    existing = load(RAW, {"events": []})
    by_play = {f"{e.get('game_id')}|{e.get('play_id')}": e for e in existing.get("events", []) if isinstance(e, dict)}
    games_seen = {str(e.get("game_id")) for e in by_play.values()}
    requested = completed = added_games = errors = 0
    current = start
    while current <= end:
        try:
            events = scoreboard(current)
            requested += 1
            for event in events:
                game_id = str(event.get("id") or "")
                status = str(event.get("status", {}).get("type", {}).get("name") or "").upper()
                if not game_id or "FINAL" not in status:
                    continue
                completed += 1
                if game_id in games_seen:
                    continue
                try:
                    payload = summary(game_id)
                    normalized = normalized_events(payload, str(current))
                    for row in normalized:
                        by_play[f"{row.get('game_id')}|{row.get('play_id')}"] = row
                    games_seen.add(game_id)
                    added_games += 1
                    time.sleep(0.2)
                except Exception:
                    errors += 1
        except Exception:
            errors += 1
        current += timedelta(days=1)
        time.sleep(0.05)
    all_events = list(by_play.values())
    all_events.sort(key=lambda e: (str(e.get("game_date") or ""), str(e.get("game_id") or ""), int(num(e.get("period"), 0) or 0), str(e.get("clock") or "")))
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "status": "ok",
        "summary": {"days_requested": requested, "completed_games_seen": completed, "new_games_added": added_games, "games": len(games_seen), "events": len(all_events), "errors": errors},
        "events": all_events,
    }
    RAW.parent.mkdir(parents=True, exist_ok=True)
    with RAW.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print("Historical play-by-play collection:", report["summary"])
    return report


def foul_kind(text: str) -> str:
    lowered = text.lower()
    if "technical" in lowered: return "technical"
    if "flagrant" in lowered: return "flagrant"
    if "offensive" in lowered or "charge" in lowered: return "offensive"
    if "shooting" in lowered: return "shooting"
    return "personal"


def event_key_candidates(event: dict[str, Any]) -> list[str]:
    game_id = str(event.get("game_id") or "")
    player_id = str(event.get("player_id") or "")
    player = norm(event.get("player"))
    return [f"{game_id}|{player_id}" if game_id and player_id else "", f"{game_id}|{player}" if game_id and player else ""]


def record_key_candidates(record: dict[str, Any]) -> list[str]:
    game_id = str(record.get("game_id") or "")
    player_id = str(record.get("player_id") or "")
    player = norm(record.get("player"))
    record_id = str(record.get("record_id") or "")
    return [record_id, f"{game_id}|{player_id}" if game_id and player_id else "", f"{game_id}|{player}" if game_id and player else ""]


def apply_backfill() -> dict[str, Any]:
    pbp = load(RAW, {"events": []})
    warehouse = load(WAREHOUSE, {"records": []})
    records = [r for r in warehouse.get("records", []) if isinstance(r, dict)]
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        for candidate in record_key_candidates(record):
            if candidate:
                index[candidate] = record
    accum: dict[int, dict[str, Any]] = defaultdict(lambda: {"period_points": defaultdict(int), "ftm": 0, "fta": 0, "three_pm": 0, "fouls": defaultdict(int), "events": 0})
    unmatched = 0
    for event in pbp.get("events", []):
        if not isinstance(event, dict) or not event.get("player"):
            continue
        record = next((index.get(k) for k in event_key_candidates(event) if k and index.get(k)), None)
        if record is None:
            unmatched += 1
            continue
        bucket = accum[id(record)]
        bucket["record"] = record
        bucket["events"] += 1
        period = int(num(event.get("period"), 0) or 0)
        etype = str(event.get("event_type") or "")
        points = int(num(event.get("points"), 0) or 0)
        text = str(event.get("description") or "")
        if etype in {"SHOT_MADE", "FREE_THROW"} and points > 0:
            bucket["period_points"][period] += points
            if etype == "FREE_THROW": bucket["ftm"] += 1
            if etype == "SHOT_MADE" and points == 3: bucket["three_pm"] += 1
        if etype == "FREE_THROW": bucket["fta"] += 1
        if etype == "FOUL": bucket["fouls"][foul_kind(text)] += 1
    updated = complete = partial = mismatches = 0
    for bucket in accum.values():
        record = bucket["record"]
        scoring = record.setdefault("scoring", {})
        fouls = record.setdefault("fouls", {})
        quality = record.setdefault("data_quality", {})
        qpts = [bucket["period_points"].get(i, 0) for i in range(1, 5)]
        ot = sum(v for p, v in bucket["period_points"].items() if p >= 5)
        event_total = sum(qpts) + ot
        box_total = num(scoring.get("total_pts"))
        scoring.update({"q1_pts": qpts[0], "q2_pts": qpts[1], "q3_pts": qpts[2], "q4_pts": qpts[3], "ot_pts": ot, "first_half_pts": qpts[0] + qpts[1], "second_half_pts": qpts[2] + qpts[3] + ot})
        scoring["ftm"] = bucket["ftm"]
        scoring["fta"] = bucket["fta"]
        scoring["free_throw_points"] = bucket["ftm"]
        scoring["three_pm"] = bucket["three_pm"]
        for name in ("personal", "offensive", "shooting", "technical", "flagrant"):
            fouls[name] = bucket["fouls"].get(name, 0)
        fouls["total_committed"] = sum(bucket["fouls"].values())
        fouls["fouled_out"] = fouls["total_committed"] >= 6
        match = box_total is None or int(box_total) == event_total
        quality["quarter_points_match_total"] = match
        quality["quarter_data_status"] = "complete" if match else "partial"
        quality["event_data_status"] = "observed"
        quality.setdefault("sources", [])
        if "historical_espn_play_by_play" not in quality["sources"]: quality["sources"].append("historical_espn_play_by_play")
        quality.setdefault("validation_flags", [])
        if not match and "HISTORICAL_PBP_POINTS_DO_NOT_MATCH_BOXSCORE" not in quality["validation_flags"]:
            quality["validation_flags"].append("HISTORICAL_PBP_POINTS_DO_NOT_MATCH_BOXSCORE")
            mismatches += 1
        updated += 1
        complete += match
        partial += not match
    warehouse["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    warehouse.setdefault("summary", {}).update({"historical_pbp_backfill": True, "historical_pbp_records_updated": updated, "quarter_complete": sum(r.get("data_quality", {}).get("quarter_data_status") == "complete" for r in records), "quarter_partial": sum(r.get("data_quality", {}).get("quarter_data_status") == "partial" for r in records), "historical_pbp_unmatched_events": unmatched, "historical_pbp_mismatches": mismatches})
    warehouse["records"] = records
    for path in (WAREHOUSE, DASHBOARD):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(warehouse, handle, indent=2, allow_nan=False)
    report = {"updated": updated, "complete": complete, "partial": partial, "mismatches": mismatches, "unmatched_events": unmatched}
    print("Historical play-by-play backfill:", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=date.today().year)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.collect or not args.apply: collect(args.season)
    if args.apply or not args.collect: apply_backfill()


if __name__ == "__main__":
    main()
