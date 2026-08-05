"""Refresh the authoritative WNBA current slate from ESPN.

Writes data/wnba/scores.json and replaces only the current-date game rows in
 data/dashboard/wnba_master.json. Historical/player/prop sections are preserved.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
HEADERS = {"User-Agent": "Mozilla/5.0 (WNBA model current-slate refresh)"}
ET = ZoneInfo("America/New_York")
SCORES = Path("data/wnba/scores.json")
MASTER = Path("data/dashboard/wnba_master.json")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def dump(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def team_name(competitor: dict) -> str:
    team = competitor.get("team") or {}
    return team.get("displayName") or team.get("shortDisplayName") or team.get("name") or ""


def parse_event(event: dict, target: str) -> dict | None:
    competitions = event.get("competitions") or []
    competition = competitions[0] if competitions else {}
    away = home = None
    for competitor in competition.get("competitors") or []:
        if competitor.get("homeAway") == "away":
            away = competitor
        elif competitor.get("homeAway") == "home":
            home = competitor
    if not away or not home:
        return None

    status_type = ((event.get("status") or {}).get("type") or {})
    state = status_type.get("state") or "pre"
    completed = bool(status_type.get("completed"))
    status = status_type.get("name") or status_type.get("description") or state
    odds_list = competition.get("odds") or []
    odds = odds_list[0] if odds_list else {}

    return {
        "game_id": str(event.get("id") or competition.get("id") or ""),
        "game_date": target,
        "bucket": "today",
        "game": f"{team_name(away)} @ {team_name(home)}",
        "away_team": team_name(away),
        "home_team": team_name(home),
        "away_score": away.get("score", "") if completed or state == "in" else "",
        "home_score": home.get("score", "") if completed or state == "in" else "",
        "status": status,
        "start_time": event.get("date") or competition.get("date") or "",
        "spread": odds.get("spread", ""),
        "total": odds.get("overUnder", ""),
        "moneyline_home": (odds.get("homeTeamOdds") or {}).get("moneyLine", ""),
        "moneyline_away": (odds.get("awayTeamOdds") or {}).get("moneyLine", ""),
        "source": "espn_scoreboard",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(ET).date().isoformat())
    args = parser.parse_args()
    target = args.date

    response = requests.get(
        ESPN,
        params={"dates": target.replace("-", ""), "limit": 50},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    raw = response.json()
    games = [g for event in raw.get("events", []) if (g := parse_event(event, target))]

    now = datetime.now(timezone.utc).isoformat()
    scores_payload = {
        "generated_at_utc": now,
        "target_date": target,
        "source": "espn_scoreboard",
        "data": {"events": raw.get("events", []), "games": games},
    }
    dump(SCORES, scores_payload)

    master = load(MASTER, {})
    existing_games = master.get("games", []) if isinstance(master, dict) else []
    historical = [
        row for row in existing_games
        if row.get("bucket") != "today" and row.get("game_date") != target
    ]
    master["generated_at_utc"] = now
    master["target_date"] = target
    master["schema_version"] = master.get("schema_version") or "master-v5-active-slate"
    master["games"] = games + historical
    master["today_games"] = games
    summary = master.setdefault("summary", {})
    summary["games"] = len(master["games"])
    summary["today_games"] = len(games)
    summary["yesterday_games"] = sum(row.get("bucket") == "yesterday" for row in historical)
    master["current_slate_refresh"] = {
        "generated_at_utc": now,
        "target_date": target,
        "source": "espn_scoreboard",
        "game_count": len(games),
        "status": "fresh" if games else "confirmed_empty_slate",
    }
    dump(MASTER, master)
    print(json.dumps({"target_date": target, "games": len(games), "matchups": [g["game"] for g in games]}, indent=2))


if __name__ == "__main__":
    main()
