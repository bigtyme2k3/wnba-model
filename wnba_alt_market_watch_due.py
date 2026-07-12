"""Decide whether a lightweight ALT market refresh is due.

The decision is based on each game's actual scheduled start time, not weekday
assumptions. This protects early Saturday/Sunday games and unusual weekday
matinees.

Checkpoints before each game: 12h, 6h, 3h, 60m, 30m, and 15m. A checkpoint is
considered due within a configurable tolerance window and is recorded so it is
not repeated.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
STATE = Path("data/history/wnba_alt_market_watch_state.json")
OUT = Path("data/dashboard/wnba_alt_market_watch_due.json")
CHECKPOINTS = [720, 360, 180, 60, 30, 15]


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def fetch_games(target: str) -> list[dict[str, Any]]:
    response = requests.get(
        ESPN,
        params={"dates": target.replace("-", ""), "limit": 50},
        headers={"User-Agent": "Mozilla/5.0 WNBA model"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    games: list[dict[str, Any]] = []
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        start = parse_time(event.get("date") or competition.get("date"))
        status = str(event.get("status", {}).get("type", {}).get("name") or "")
        games.append({
            "game_id": str(event.get("id") or ""),
            "game": f"{away.get('team', {}).get('displayName', 'Away')} @ {home.get('team', {}).get('displayName', 'Home')}",
            "start_utc": start.isoformat() if start else None,
            "status": status,
        })
    return games


def evaluate(target: str, tolerance_minutes: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    state = load(STATE, {"completed": {}})
    completed = state.setdefault("completed", {})
    games = fetch_games(target)
    due: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []

    for game in games:
        start = parse_time(game.get("start_utc"))
        if start is None:
            continue
        minutes_to_tip = (start - now).total_seconds() / 60.0
        if minutes_to_tip < -5:
            continue
        upcoming.append({**game, "minutes_to_tip": round(minutes_to_tip, 1)})
        for checkpoint in CHECKPOINTS:
            key = f"{target}|{game['game_id']}|{checkpoint}"
            lower = checkpoint - tolerance_minutes
            upper = checkpoint + tolerance_minutes
            if lower <= minutes_to_tip <= upper and not completed.get(key):
                due.append({
                    **game,
                    "checkpoint_minutes": checkpoint,
                    "minutes_to_tip": round(minutes_to_tip, 1),
                    "state_key": key,
                })

    result = {
        "generated_at_utc": now.isoformat(),
        "target_date": target,
        "run_refresh": bool(due),
        "due": due,
        "upcoming_games": sorted(upcoming, key=lambda row: row["minutes_to_tip"]),
        "policy": {
            "source": "ESPN scoreboard event start times",
            "weekday_assumptions": False,
            "checkpoints_minutes_before_tip": CHECKPOINTS,
            "tolerance_minutes": tolerance_minutes,
            "early_weekend_games_supported": True,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    return result


def mark_complete(result: dict[str, Any]) -> None:
    state = load(STATE, {"completed": {}})
    completed = state.setdefault("completed", {})
    now = datetime.now(timezone.utc).isoformat()
    for item in result.get("due", []):
        completed[str(item.get("state_key"))] = now
    state["updated_at_utc"] = now
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, allow_nan=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--tolerance-minutes", type=int, default=16)
    parser.add_argument("--mark-complete", action="store_true")
    args = parser.parse_args()
    result = evaluate(args.date, args.tolerance_minutes)
    if args.mark_complete and result.get("run_refresh"):
        mark_complete(result)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
