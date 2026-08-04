"""Recover completed WNBA player box scores from ESPN's public scoreboard feed.

This is a secondary source used only when the canonical player-game-log warehouse
is missing completed-game rows. It writes normalized full-game totals to
``data/raw/wnba_boxscores_<date>.json`` for the existing warehouse builder.
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"


def fetch_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    request_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        request_url,
        headers={"User-Agent": "wnba-model/5.0 (+github-actions)"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def number(value: Any) -> float | int | None:
    if value in (None, "", "--"):
        return None
    text = str(value).strip()
    try:
        parsed = float(text)
        return int(parsed) if parsed.is_integer() else parsed
    except ValueError:
        return None


def minutes(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    text = str(value).strip()
    if ":" in text:
        left, right = text.split(":", 1)
        try:
            return round(float(left) + float(right) / 60.0, 3)
        except ValueError:
            return None
    parsed = number(text)
    return float(parsed) if parsed is not None else None


def parse_made_attempted(value: Any) -> tuple[int | None, int | None]:
    text = str(value or "").strip()
    if "-" not in text:
        return None, None
    made, attempted = text.split("-", 1)
    return int(number(made) or 0), int(number(attempted) or 0)


def competitor_name(competitor: dict[str, Any]) -> str:
    team = competitor.get("team") or {}
    return str(team.get("displayName") or team.get("shortDisplayName") or team.get("name") or "").strip()


def game_name(event: dict[str, Any]) -> str:
    competition = ((event.get("competitions") or [{}])[0])
    competitors = competition.get("competitors") or []
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    return f"{competitor_name(away)} @ {competitor_name(home)}".strip()


def final_event(event: dict[str, Any]) -> bool:
    status = ((event.get("status") or {}).get("type") or {})
    return bool(status.get("completed")) or str(status.get("state") or "").lower() == "post"


def parse_summary(event: dict[str, Any], target_date: str) -> list[dict[str, Any]]:
    event_id = str(event.get("id") or "")
    payload = fetch_json(SUMMARY, {"event": event_id})
    game = game_name(event)
    rows: list[dict[str, Any]] = []
    boxscore = payload.get("boxscore") or {}
    for team_block in boxscore.get("players") or []:
        team = team_block.get("team") or {}
        team_name = str(team.get("displayName") or team.get("shortDisplayName") or "").strip()
        for stat_group in team_block.get("statistics") or []:
            labels = [str(x).strip().upper() for x in stat_group.get("labels") or stat_group.get("names") or []]
            for athlete_row in stat_group.get("athletes") or []:
                athlete = athlete_row.get("athlete") or {}
                player = str(athlete.get("displayName") or athlete.get("fullName") or "").strip()
                if not player:
                    continue
                values = athlete_row.get("stats") or []
                stat = {label: values[index] if index < len(values) else None for index, label in enumerate(labels)}
                fgm, fga = parse_made_attempted(stat.get("FG"))
                fg3m, fg3a = parse_made_attempted(stat.get("3PT"))
                ftm, fta = parse_made_attempted(stat.get("FT"))
                row = {
                    "source": "espn_boxscore_fallback",
                    "source_event_id": event_id,
                    "date": target_date,
                    "game": game,
                    "player": player,
                    "team": team_name,
                    "starter": bool(athlete_row.get("starter")),
                    "minutes": minutes(stat.get("MIN")),
                    "pts": number(stat.get("PTS")),
                    "reb": number(stat.get("REB")),
                    "oreb": number(stat.get("OREB")),
                    "dreb": number(stat.get("DREB")),
                    "ast": number(stat.get("AST")),
                    "stl": number(stat.get("STL")),
                    "blk": number(stat.get("BLK")),
                    "tov": number(stat.get("TO") or stat.get("TOV")),
                    "pf": number(stat.get("PF")),
                    "plus_minus": number(stat.get("+/-")),
                    "fgm": fgm,
                    "fga": fga,
                    "fg3m": fg3m,
                    "fg3a": fg3a,
                    "ftm": ftm,
                    "fta": fta,
                }
                if any(row.get(key) is not None for key in ("pts", "reb", "ast", "minutes")):
                    rows.append(row)
    return rows


def build(target_date: str) -> dict[str, Any]:
    compact = target_date.replace("-", "")
    scoreboard = fetch_json(SCOREBOARD, {"dates": compact, "limit": "100"})
    events = [event for event in scoreboard.get("events") or [] if final_event(event)]
    players: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for event in events:
        try:
            players.extend(parse_summary(event, target_date))
        except Exception as exc:  # preserve partial recovery when one game fails
            errors.append({"event_id": str(event.get("id") or ""), "error": str(exc)})
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "date": target_date,
        "source": "ESPN public WNBA scoreboard/summary",
        "status": "ok" if players else "no_rows",
        "events_examined": len(events),
        "players": players,
        "errors": errors,
    }
    output = Path(f"data/raw/wnba_boxscores_{target_date}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": target_date, "events": len(events), "players": len(players), "errors": len(errors)}))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
