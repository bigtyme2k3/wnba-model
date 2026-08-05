"""Refresh the authoritative WNBA current slate.

ESPN is attempted first. If ESPN blocks GitHub Actions (for example HTTP 403),
The Odds API becomes the authoritative fallback. The script writes
``data/wnba/scores.json`` and replaces only the current-date game rows in
``data/dashboard/wnba_master.json``. Historical/player/prop sections are
preserved.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
ODDS_API = "https://api.the-odds-api.com/v4/sports/basketball_wnba/odds"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WNBA-Model/5.0; +https://github.com/bigtyme2k3/wnba-model)",
    "Accept": "application/json,text/plain,*/*",
}
ET = ZoneInfo("America/New_York")
SCORES = Path("data/wnba/scores.json")
MASTER = Path("data/dashboard/wnba_master.json")


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def team_name(competitor: dict[str, Any]) -> str:
    team = competitor.get("team") or {}
    return team.get("displayName") or team.get("shortDisplayName") or team.get("name") or ""


def parse_espn_event(event: dict[str, Any], target: str) -> dict[str, Any] | None:
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


def fetch_espn(target: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    response = requests.get(
        ESPN,
        params={"dates": target.replace("-", ""), "limit": 50},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    raw = response.json()
    games = [g for event in raw.get("events", []) if (g := parse_espn_event(event, target))]
    return games, raw


def market_outcomes(bookmaker: dict[str, Any], key: str) -> list[dict[str, Any]]:
    for market in bookmaker.get("markets") or []:
        if market.get("key") == key:
            return market.get("outcomes") or []
    return []


def parse_odds_event(event: dict[str, Any], target: str) -> dict[str, Any] | None:
    commence = event.get("commence_time") or ""
    try:
        event_date = datetime.fromisoformat(commence.replace("Z", "+00:00")).astimezone(ET).date().isoformat()
    except ValueError:
        return None
    if event_date != target:
        return None

    home = event.get("home_team") or ""
    away = event.get("away_team") or ""
    books = event.get("bookmakers") or []
    preferred = next((b for b in books if b.get("key") == "fanduel"), None)
    preferred = preferred or next((b for b in books if b.get("key") == "draftkings"), None)
    preferred = preferred or (books[0] if books else {})

    spread = total = ml_home = ml_away = ""
    for outcome in market_outcomes(preferred, "spreads"):
        if outcome.get("name") == home:
            spread = outcome.get("point", "")
            break
    totals = market_outcomes(preferred, "totals")
    if totals:
        total = totals[0].get("point", "")
    for outcome in market_outcomes(preferred, "h2h"):
        if outcome.get("name") == home:
            ml_home = outcome.get("price", "")
        elif outcome.get("name") == away:
            ml_away = outcome.get("price", "")

    return {
        "game_id": str(event.get("id") or ""),
        "game_date": target,
        "bucket": "today",
        "game": f"{away} @ {home}",
        "away_team": away,
        "home_team": home,
        "away_score": "",
        "home_score": "",
        "status": "STATUS_SCHEDULED",
        "start_time": commence,
        "spread": spread,
        "total": total,
        "moneyline_home": ml_home,
        "moneyline_away": ml_away,
        "source": "the_odds_api",
        "sportsbook": preferred.get("title") or preferred.get("key") or "",
    }


def fetch_odds_api(target: str, api_key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    response = requests.get(
        ODDS_API,
        params={
            "apiKey": api_key,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "bookmakers": "fanduel,draftkings",
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
        timeout=30,
    )
    if response.status_code == 401:
        raise RuntimeError("ODDS_API_KEY is invalid or unauthorized")
    if response.status_code == 429:
        raise RuntimeError("The Odds API quota or rate limit was reached")
    response.raise_for_status()
    raw = response.json()
    if not isinstance(raw, list):
        raise RuntimeError("Unexpected The Odds API response shape")
    games = [g for event in raw if (g := parse_odds_event(event, target))]
    return games, raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(ET).date().isoformat())
    parser.add_argument("--api-key", default=os.getenv("ODDS_API_KEY"))
    args = parser.parse_args()
    target = args.date

    errors: list[str] = []
    raw: Any = None
    source = ""
    try:
        games, raw = fetch_espn(target)
        source = "espn_scoreboard"
    except Exception as exc:
        errors.append(f"ESPN: {type(exc).__name__}: {exc}")
        if not args.api_key:
            raise SystemExit("ESPN refresh failed and ODDS_API_KEY is unavailable: " + errors[-1])
        games, raw = fetch_odds_api(target, args.api_key)
        source = "the_odds_api"

    now = datetime.now(timezone.utc).isoformat()
    scores_payload = {
        "generated_at_utc": now,
        "target_date": target,
        "source": source,
        "fallback_errors": errors,
        "data": {"events": raw, "games": games},
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
        "source": source,
        "fallback_errors": errors,
        "game_count": len(games),
        "status": "fresh" if games else "confirmed_empty_slate",
    }
    dump(MASTER, master)
    print(json.dumps({
        "target_date": target,
        "source": source,
        "fallback_errors": errors,
        "games": len(games),
        "matchups": [g["game"] for g in games],
    }, indent=2))


if __name__ == "__main__":
    main()
