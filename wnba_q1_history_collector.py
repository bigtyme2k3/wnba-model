"""Collect verified WNBA first-quarter team scores from ESPN scoreboards.

The collector uses completed-game period linescores only. It does not estimate missing
quarter scores. Output is cumulative and keyed by game/team for deterministic updates.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
HEADERS = {"User-Agent": "Mozilla/5.0 (WNBA research project)"}
OUTS = [Path("data/warehouse/wnba_q1_team_history.json"), Path("data/dashboard/wnba_q1_team_history.json")]


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result >= 0 else None
    except Exception:
        return None


def first_period_score(competitor: dict[str, Any]) -> float | None:
    lines = competitor.get("linescores") or competitor.get("lineScores") or []
    if not isinstance(lines, list) or not lines:
        return None
    first = lines[0] if isinstance(lines[0], dict) else {}
    return num(first.get("value", first.get("displayValue")))


def fetch_day(day: date) -> list[dict[str, Any]]:
    response = requests.get(
        BASE,
        headers=HEADERS,
        params={"dates": day.strftime("%Y%m%d"), "limit": 50},
        timeout=20,
    )
    response.raise_for_status()
    rows: list[dict[str, Any]] = []
    for event in response.json().get("events", []):
        status = str(event.get("status", {}).get("type", {}).get("name", "")).upper()
        if "FINAL" not in status:
            continue
        competition = (event.get("competitions") or [{}])[0]
        game_id = str(event.get("id") or competition.get("id") or "")
        competitors = competition.get("competitors") or []
        if len(competitors) < 2:
            continue
        for comp in competitors:
            team = comp.get("team") or {}
            q1 = first_period_score(comp)
            if not game_id or q1 is None:
                continue
            rows.append({
                "game_id": game_id,
                "game_date": day.isoformat(),
                "team_id": str(team.get("id") or ""),
                "team": str(team.get("displayName") or team.get("name") or "").strip(),
                "team_abbreviation": str(team.get("abbreviation") or "").strip(),
                "home_away": comp.get("homeAway"),
                "q1_points": q1,
                "source": "espn_scoreboard_linescores",
            })
    return rows


def build(season: int) -> dict[str, Any]:
    start = date(season, 5, 1)
    end = min(date(season, 10, 31), date.today())
    existing: dict[tuple[str, str], dict[str, Any]] = {}
    for path in OUTS:
        if not path.exists():
            continue
        try:
            payload = json.load(path.open(encoding="utf-8"))
            for row in payload.get("records", []):
                key = (str(row.get("game_id") or ""), str(row.get("team_id") or row.get("team") or ""))
                if all(key):
                    existing[key] = row
            break
        except Exception:
            pass

    checked = 0
    failures = 0
    current = start
    while current <= end:
        try:
            for row in fetch_day(current):
                key = (row["game_id"], row.get("team_id") or row["team"])
                existing[key] = row
            checked += 1
        except Exception as exc:
            failures += 1
            print(f"Q1 history warning {current}: {exc}")
        current += timedelta(days=1)
        time.sleep(0.06)

    records = sorted(existing.values(), key=lambda r: (r.get("game_date", ""), r.get("game_id", ""), r.get("team", "")))
    teams = sorted({r.get("team") for r in records if r.get("team")})
    games = len({r.get("game_id") for r in records if r.get("game_id")})
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "status": "ok" if records else "empty",
        "summary": {"records": len(records), "games": games, "teams": len(teams), "days_checked": checked, "failures": failures},
        "records": records,
        "methodology": "Verified ESPN completed-game first-period linescores only; no imputation.",
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print("Q1 HISTORY ACTIVE", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=date.today().year)
    args = parser.parse_args()
    build(args.season)


if __name__ == "__main__":
    main()
