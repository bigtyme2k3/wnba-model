"""Refresh upcoming WNBA odds from The Odds API and append them to the warehouse.

Uses the current odds endpoint, limited to DraftKings and FanDuel and the h2h,
spreads, and totals markets. The request is intentionally a single live snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests

from wnba_odds_history_warehouse import (
    BASE_URL,
    BOOKMAKERS,
    MARKETS,
    SPORT,
    connect,
    ingest,
    now,
    summary,
)

DEFAULT_DB = Path("data/warehouse/wnba_odds_history.sqlite")
STATUS_OUT = Path("data/dashboard/wnba_live_slate_status.json")
WAREHOUSE_STATUS_OUT = Path("data/warehouse/wnba_live_slate_status.json")


def header_int(response: requests.Response, name: str) -> int | None:
    try:
        return int(response.headers.get(name, ""))
    except (TypeError, ValueError):
        return None


def request_live(api_key: str) -> tuple[list[dict[str, Any]], dict[str, int | None]]:
    response = requests.get(
        f"{BASE_URL}/sports/{SPORT}/odds",
        params={
            "apiKey": api_key,
            "bookmakers": BOOKMAKERS,
            "markets": MARKETS,
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
        timeout=30,
    )
    if response.status_code == 401:
        raise RuntimeError("ODDS_API_KEY is invalid or unauthorized.")
    if response.status_code == 429:
        raise RuntimeError("The Odds API quota or rate limit was reached.")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected current-odds response shape.")
    usage = {
        "last": header_int(response, "x-requests-last"),
        "used": header_int(response, "x-requests-used"),
        "remaining": header_int(response, "x-requests-remaining"),
    }
    return payload, usage


def build_status(db_path: Path, counts: dict[str, int], usage: dict[str, int | None]) -> dict[str, Any]:
    con = connect(db_path)
    upcoming_games = con.execute(
        "SELECT COUNT(*) FROM games WHERE completed=0 AND commence_time_utc>=?", (now(),)
    ).fetchone()[0]
    upcoming_with_books = con.execute(
        """
        SELECT COUNT(DISTINCT g.game_id)
        FROM games g JOIN closing_odds c ON c.game_id=g.game_id
        WHERE g.completed=0 AND g.commence_time_utc>=?
        """,
        (now(),),
    ).fetchone()[0]
    next_tip = con.execute(
        "SELECT MIN(commence_time_utc) FROM games WHERE completed=0 AND commence_time_utc>=?",
        (now(),),
    ).fetchone()[0]
    con.close()
    payload = {
        "generated_at_utc": now(),
        "status": "slate_available" if upcoming_with_books else "no_upcoming_markets",
        "source": "The Odds API current odds endpoint",
        "scope": {"sport": SPORT, "bookmakers": BOOKMAKERS.split(","), "markets": MARKETS.split(",")},
        "request": {**counts, "api_usage": usage},
        "warehouse": {
            "upcoming_games": upcoming_games,
            "upcoming_games_with_current_odds": upcoming_with_books,
            "next_commence_time_utc": next_tip,
        },
    }
    for path in (STATUS_OUT, WAREHOUSE_STATUS_OUT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    return payload


def refresh(api_key: str, db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    games, usage = request_live(api_key)
    requested = now()
    wrapped = {"timestamp": requested, "data": games}
    con = connect(db_path)
    counts = ingest(con, requested, wrapped, usage)
    warehouse_summary = summary(con, db_path, {"status": "live_refresh_complete", "live_run": counts})
    con.close()
    status = build_status(db_path, counts, usage)
    print(json.dumps({"warehouse": warehouse_summary, "live_status": status}, indent=2, allow_nan=False))
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=os.getenv("ODDS_API_KEY"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("ODDS_API_KEY is required.")
    refresh(args.api_key, args.db)


if __name__ == "__main__":
    main()
