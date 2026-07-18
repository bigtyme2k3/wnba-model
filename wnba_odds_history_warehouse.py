"""Compact DraftKings/FanDuel WNBA historical odds warehouse.

Historical pulls are manual and request-capped because The Odds API historical
endpoint consumes paid credits. Data is normalized into SQLite for line movement,
closing-line and outcome analysis.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

BASE_URL = "https://api.the-odds-api.com/v4"
SPORT = "basketball_wnba"
BOOKMAKERS = "draftkings,fanduel"
MARKETS = "h2h,spreads,totals"
DEFAULT_DB = Path("data/warehouse/wnba_odds_history.sqlite")
SUMMARY = Path("data/warehouse/wnba_odds_history_summary.json")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS games (
 game_id TEXT PRIMARY KEY, sport_key TEXT NOT NULL, commence_time_utc TEXT NOT NULL,
 game_date_utc TEXT NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
 completed INTEGER NOT NULL DEFAULT 0, home_score INTEGER, away_score INTEGER,
 updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
 snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, requested_at_utc TEXT NOT NULL,
 snapshot_time_utc TEXT NOT NULL UNIQUE, previous_snapshot_utc TEXT,
 next_snapshot_utc TEXT, api_requests_last INTEGER, api_requests_used INTEGER,
 api_requests_remaining INTEGER, created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS odds (
 odds_id INTEGER PRIMARY KEY AUTOINCREMENT,
 snapshot_id INTEGER NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
 game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
 bookmaker_key TEXT NOT NULL, bookmaker_title TEXT, bookmaker_last_update_utc TEXT,
 home_moneyline INTEGER, away_moneyline INTEGER, home_spread REAL,
 home_spread_price INTEGER, away_spread REAL, away_spread_price INTEGER,
 total REAL, over_price INTEGER, under_price INTEGER,
 UNIQUE(snapshot_id, game_id, bookmaker_key)
);
CREATE INDEX IF NOT EXISTS idx_games_commence ON games(commence_time_utc);
CREATE INDEX IF NOT EXISTS idx_odds_game_book ON odds(game_id, bookmaker_key);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON snapshots(snapshot_time_utc);
CREATE VIEW IF NOT EXISTS closing_odds AS
SELECT o.* FROM odds o
JOIN games g ON g.game_id=o.game_id
JOIN snapshots s ON s.snapshot_id=o.snapshot_id
WHERE s.snapshot_time_utc=(
 SELECT MAX(s2.snapshot_time_utc) FROM odds o2
 JOIN snapshots s2 ON s2.snapshot_id=o2.snapshot_id
 WHERE o2.game_id=o.game_id AND o2.bookmaker_key=o.bookmaker_key
 AND s2.snapshot_time_utc<=g.commence_time_utc
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso(value: str) -> str:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def request_snapshot(api_key: str, stamp: str) -> tuple[dict[str, Any], dict[str, int | None]]:
    response = requests.get(
        f"{BASE_URL}/historical/sports/{SPORT}/odds",
        params={"apiKey": api_key, "bookmakers": BOOKMAKERS, "markets": MARKETS,
                "oddsFormat": "american", "dateFormat": "iso", "date": stamp},
        timeout=30,
    )
    if response.status_code == 401:
        raise RuntimeError("API key invalid or historical access unavailable on this plan.")
    if response.status_code == 429:
        raise RuntimeError("The Odds API quota or rate limit was reached.")
    if response.status_code == 422:
        raise RuntimeError(f"Request rejected: {response.text[:300]}")
    response.raise_for_status()
    usage: dict[str, int | None] = {}
    for header, key in (("x-requests-last", "last"), ("x-requests-used", "used"),
                        ("x-requests-remaining", "remaining")):
        try:
            usage[key] = int(response.headers.get(header, ""))
        except ValueError:
            usage[key] = None
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected API response shape.")
    return payload, usage


def market_map(market: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(x.get("name")): x for x in market.get("outcomes", []) if isinstance(x, dict)}


def normalize(game: dict[str, Any], book: dict[str, Any]) -> dict[str, Any]:
    home, away = str(game.get("home_team") or ""), str(game.get("away_team") or "")
    row = {"bookmaker_key": book.get("key"), "bookmaker_title": book.get("title"),
           "bookmaker_last_update_utc": book.get("last_update"), "home_moneyline": None,
           "away_moneyline": None, "home_spread": None, "home_spread_price": None,
           "away_spread": None, "away_spread_price": None, "total": None,
           "over_price": None, "under_price": None}
    for market in book.get("markets", []):
        if not isinstance(market, dict):
            continue
        values, key = market_map(market), market.get("key")
        if key == "h2h":
            row["home_moneyline"] = values.get(home, {}).get("price")
            row["away_moneyline"] = values.get(away, {}).get("price")
        elif key == "spreads":
            row["home_spread"] = values.get(home, {}).get("point")
            row["home_spread_price"] = values.get(home, {}).get("price")
            row["away_spread"] = values.get(away, {}).get("point")
            row["away_spread_price"] = values.get(away, {}).get("price")
        elif key == "totals":
            row["total"] = values.get("Over", {}).get("point")
            if row["total"] is None:
                row["total"] = values.get("Under", {}).get("point")
            row["over_price"] = values.get("Over", {}).get("price")
            row["under_price"] = values.get("Under", {}).get("price")
    return row


def ingest(con: sqlite3.Connection, requested: str, payload: dict[str, Any], usage: dict[str, int | None]) -> dict[str, int]:
    stamp, created = iso(str(payload.get("timestamp") or requested)), now()
    con.execute("""INSERT OR IGNORE INTO snapshots
      (requested_at_utc,snapshot_time_utc,previous_snapshot_utc,next_snapshot_utc,
       api_requests_last,api_requests_used,api_requests_remaining,created_at_utc)
      VALUES (?,?,?,?,?,?,?,?)""",
      (requested, stamp, payload.get("previous_timestamp"), payload.get("next_timestamp"),
       usage.get("last"), usage.get("used"), usage.get("remaining"), created))
    sid = con.execute("SELECT snapshot_id FROM snapshots WHERE snapshot_time_utc=?", (stamp,)).fetchone()[0]
    game_count = odds_count = 0
    for game in payload.get("data", []):
        if not isinstance(game, dict) or not game.get("id") or not game.get("commence_time"):
            continue
        commence = iso(str(game["commence_time"]))
        con.execute("""INSERT INTO games
          (game_id,sport_key,commence_time_utc,game_date_utc,home_team,away_team,updated_at_utc)
          VALUES (?,?,?,?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET
          commence_time_utc=excluded.commence_time_utc,game_date_utc=excluded.game_date_utc,
          home_team=excluded.home_team,away_team=excluded.away_team,updated_at_utc=excluded.updated_at_utc""",
          (game["id"], game.get("sport_key") or SPORT, commence, commence[:10],
           game.get("home_team") or "", game.get("away_team") or "", created))
        game_count += 1
        for book in game.get("bookmakers", []):
            if not isinstance(book, dict) or book.get("key") not in {"draftkings", "fanduel"}:
                continue
            row = normalize(game, book)
            con.execute("""INSERT INTO odds
              (snapshot_id,game_id,bookmaker_key,bookmaker_title,bookmaker_last_update_utc,
               home_moneyline,away_moneyline,home_spread,home_spread_price,away_spread,
               away_spread_price,total,over_price,under_price)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(snapshot_id,game_id,bookmaker_key) DO UPDATE SET
               bookmaker_title=excluded.bookmaker_title,
               bookmaker_last_update_utc=excluded.bookmaker_last_update_utc,
               home_moneyline=excluded.home_moneyline,away_moneyline=excluded.away_moneyline,
               home_spread=excluded.home_spread,home_spread_price=excluded.home_spread_price,
               away_spread=excluded.away_spread,away_spread_price=excluded.away_spread_price,
               total=excluded.total,over_price=excluded.over_price,under_price=excluded.under_price""",
              (sid, game["id"], *row.values()))
            odds_count += 1
    con.commit()
    return {"games_seen": game_count, "odds_rows_seen": odds_count}


def stamps(start: str, end: str, hour: int) -> Iterable[str]:
    day, finish = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date()
    while day <= finish:
        if 5 <= day.month <= 10:
            yield datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        day += timedelta(days=1)


def summary(con: sqlite3.Connection, db_path: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"generated_at_utc": now(), "database": str(db_path), "sport": SPORT,
               "bookmakers": BOOKMAKERS.split(","), "markets": MARKETS.split(","),
               "games": con.execute("SELECT COUNT(*) FROM games").fetchone()[0],
               "snapshots": con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
               "odds_rows": con.execute("SELECT COUNT(*) FROM odds").fetchone()[0],
               "closing_rows": con.execute("SELECT COUNT(*) FROM closing_odds").fetchone()[0],
               "first_snapshot_utc": con.execute("SELECT MIN(snapshot_time_utc) FROM snapshots").fetchone()[0],
               "last_snapshot_utc": con.execute("SELECT MAX(snapshot_time_utc) FROM snapshots").fetchone()[0],
               **(extra or {})}
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "backfill", "summary"])
    parser.add_argument("--api-key", default=os.getenv("ODDS_API_KEY"))
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--hour-utc", type=int, default=22)
    parser.add_argument("--max-requests", type=int, default=10)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    con = connect(args.db)
    if args.action in {"init", "summary"}:
        print(json.dumps(summary(con, args.db, {"status": "initialized" if args.action == "init" else "ok"}), indent=2))
        return
    if not args.api_key:
        raise SystemExit("ODDS_API_KEY is required for backfill.")
    if not args.start or not args.end:
        raise SystemExit("--start and --end are required for backfill.")
    if not 0 <= args.hour_utc <= 23:
        raise SystemExit("--hour-utc must be 0-23.")
    requested = list(stamps(args.start, args.end, args.hour_utc))
    if len(requested) > args.max_requests:
        raise SystemExit(f"Refusing {len(requested)} requests; intentionally raise --max-requests.")
    run = {"requested": len(requested), "successful": 0, "failed": 0,
           "games_seen": 0, "odds_rows_seen": 0}
    for stamp in requested:
        try:
            payload, usage = request_snapshot(args.api_key, stamp)
            counts = ingest(con, stamp, payload, usage)
            run["successful"] += 1
            run["games_seen"] += counts["games_seen"]
            run["odds_rows_seen"] += counts["odds_rows_seen"]
            print(f"OK {stamp}: {counts}; credits={usage}")
        except Exception as exc:
            run["failed"] += 1
            print(f"ERROR {stamp}: {exc}", file=sys.stderr)
        time.sleep(args.sleep)
    print(json.dumps(summary(con, args.db, {"status": "backfill_complete", "run": run}), indent=2))


if __name__ == "__main__":
    main()
