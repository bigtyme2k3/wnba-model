"""Audit pending ALT archive rows against the official WNBA schedule before date aliasing.

The archive can contain stale dashboard slate dates. Date proximity alone is unsafe
because WNBA teams can play the same opponent on consecutive or near-consecutive
dates. This module queries ESPN's historical scoreboard for a +/-7 day window around
each pending archive date and classifies each pending matchup as:

- exact_date: official schedule contains the same home/away matchup on archive date
- unique_schedule_alias: exactly one same-orientation matchup exists in the window
- repeated_matchup_ambiguous: multiple same-orientation meetings exist in the window
- home_away_mismatch: only reversed-orientation meetings exist
- schedule_not_found: no matching official schedule event was found

No archive records are modified here. The generated audit is consumed by
wnba_alt_date_alias_recovery.py as a guardrail.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from typing import Any

import requests

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WNBA-Model/5.0; +https://github.com/bigtyme2k3/wnba-model)",
    "Accept": "application/json,text/plain,*/*",
}
DIAGNOSTICS = Path("data/dashboard/wnba_alt_pending_diagnostics.json")
DASHBOARD = Path("data/dashboard/wnba_alt_schedule_audit.json")
WAREHOUSE = Path("data/warehouse/wnba_alt_schedule_audit.json")


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def team_key(value: Any) -> str:
    words = norm(value).split()
    return words[-1] if words else ""


def parse_matchup(value: Any) -> tuple[str, str] | None:
    text = str(value or "")
    parts = re.split(r"\s+@\s+|\s+at\s+", text, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        return team_key(parts[0]), team_key(parts[1])
    parts = re.split(r"\s+vs\.?\s+", text, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        return team_key(parts[0]), team_key(parts[1])
    return None


def team_name(competitor: dict[str, Any]) -> str:
    team = competitor.get("team") or {}
    return team.get("displayName") or team.get("shortDisplayName") or team.get("name") or ""


def fetch_day(day: str) -> list[dict[str, Any]]:
    response = requests.get(
        ESPN,
        params={"dates": day.replace("-", ""), "limit": 50},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    raw = response.json()
    games: list[dict[str, Any]] = []
    for event in raw.get("events", []):
        comps = event.get("competitions") or []
        comp = comps[0] if comps else {}
        away = home = None
        for competitor in comp.get("competitors") or []:
            if competitor.get("homeAway") == "away":
                away = competitor
            elif competitor.get("homeAway") == "home":
                home = competitor
        if not away or not home:
            continue
        away_name = team_name(away)
        home_name = team_name(home)
        status = ((event.get("status") or {}).get("type") or {})
        games.append({
            "date": day,
            "event_id": str(event.get("id") or comp.get("id") or ""),
            "away_team": away_name,
            "home_team": home_name,
            "away_key": team_key(away_name),
            "home_key": team_key(home_name),
            "game": f"{away_name} @ {home_name}",
            "status": status.get("name") or status.get("description") or status.get("state") or "",
            "completed": bool(status.get("completed")),
            "start_time": event.get("date") or comp.get("date") or "",
            "source": "espn_scoreboard",
        })
    return games


def pending_rows() -> list[dict[str, Any]]:
    payload = load(DIAGNOSTICS, {"inspector": []})
    return [row for row in payload.get("inspector", []) if isinstance(row, dict)]


def row_identity(row: dict[str, Any]) -> str:
    line = row.get("line") if row.get("line") is not None else row.get("alt_line")
    return "|".join([
        str(row.get("date") or "")[:10],
        norm(row.get("player")),
        norm(row.get("stat")),
        norm(row.get("side")),
        str(line if line is not None else ""),
    ])


def classify(row: dict[str, Any], schedule: list[dict[str, Any]], window: int) -> dict[str, Any]:
    target_str = str(row.get("date") or "")[:10]
    matchup = parse_matchup(row.get("game"))
    base = {
        "row_key": row_identity(row),
        "date": target_str,
        "player": row.get("player"),
        "game": row.get("game"),
        "stat": row.get("stat"),
        "side": row.get("side"),
        "line": row.get("line") if row.get("line") is not None else row.get("alt_line"),
    }
    if not target_str or not matchup:
        return {**base, "classification": "schedule_not_found", "candidate_games": []}
    try:
        target = date.fromisoformat(target_str)
    except ValueError:
        return {**base, "classification": "schedule_not_found", "candidate_games": []}

    away_key, home_key = matchup
    candidates = []
    reversed_candidates = []
    for game in schedule:
        try:
            gdate = date.fromisoformat(str(game.get("date") or "")[:10])
        except ValueError:
            continue
        if abs((gdate - target).days) > window:
            continue
        if game.get("away_key") == away_key and game.get("home_key") == home_key:
            candidates.append(game)
        elif game.get("away_key") == home_key and game.get("home_key") == away_key:
            reversed_candidates.append(game)

    exact = [g for g in candidates if g.get("date") == target_str]
    if exact:
        classification = "exact_date"
        suggested_date = target_str
    elif len(candidates) == 1:
        classification = "unique_schedule_alias"
        suggested_date = candidates[0].get("date")
    elif len(candidates) > 1:
        classification = "repeated_matchup_ambiguous"
        suggested_date = None
    elif reversed_candidates:
        classification = "home_away_mismatch"
        suggested_date = None
    else:
        classification = "schedule_not_found"
        suggested_date = None

    return {
        **base,
        "classification": classification,
        "suggested_date": suggested_date,
        "candidate_dates": sorted({str(g.get("date")) for g in candidates}),
        "candidate_games": candidates,
        "reversed_candidate_dates": sorted({str(g.get("date")) for g in reversed_candidates}),
        "reversed_candidate_games": reversed_candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", type=int, default=7)
    parser.add_argument("--sleep", type=float, default=0.05)
    args = parser.parse_args()

    pending = pending_rows()
    target_dates = sorted({str(row.get("date") or "")[:10] for row in pending if row.get("date")})
    fetch_dates: set[str] = set()
    for value in target_dates:
        try:
            target = date.fromisoformat(value)
        except ValueError:
            continue
        for delta in range(-args.window, args.window + 1):
            fetch_dates.add((target + timedelta(days=delta)).isoformat())

    schedule: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for day in sorted(fetch_dates):
        try:
            schedule.extend(fetch_day(day))
        except Exception as exc:
            errors.append({"date": day, "error": f"{type(exc).__name__}: {exc}"})
        if args.sleep:
            time.sleep(args.sleep)

    rows = [classify(row, schedule, args.window) for row in pending]
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("classification") or "unknown")
        counts[key] = counts.get(key, 0) + 1

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "espn_scoreboard",
        "window_days": args.window,
        "pending_rows": len(rows),
        "target_dates": target_dates,
        "schedule_dates_checked": len(fetch_dates),
        "schedule_games_found": len(schedule),
        "classification_counts": counts,
        "fetch_errors": errors,
        "rows": rows,
    }
    text = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    for path in (DASHBOARD, WAREHOUSE):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(json.dumps({
        "pending_rows": len(rows),
        "classification_counts": counts,
        "fetch_errors": len(errors),
        "dashboard": str(DASHBOARD),
    }, indent=2))


if __name__ == "__main__":
    main()
