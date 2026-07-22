"""Historical WNBA betting warehouse v2.

Primary data source: The Odds API historical endpoints.
Sportsbooks: DraftKings, FanDuel, Fanatics only.

The collector stores every returned outcome as an independent wager record. It
never averages books and never invents unavailable markets. Core game markets
are collected from historical sport snapshots. Additional/Q1/player markets are
collected one event at a time from the historical event endpoint.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.the-odds-api.com/v4"
REGISTRY_PATH = Path("config/market_registry.json")
DEFAULT_DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
SUMMARY_PATH = Path("data/warehouse/wnba_odds_warehouse_v2_summary.json")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  sport_key TEXT NOT NULL,
  commence_time_utc TEXT NOT NULL,
  game_date_utc TEXT NOT NULL,
  home_team TEXT NOT NULL,
  away_team TEXT NOT NULL,
  completed INTEGER NOT NULL DEFAULT 0,
  home_score REAL,
  away_score REAL,
  updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
  requested_at_utc TEXT NOT NULL,
  returned_at_utc TEXT NOT NULL,
  endpoint_type TEXT NOT NULL,
  event_id TEXT,
  previous_snapshot_utc TEXT,
  next_snapshot_utc TEXT,
  requests_last INTEGER,
  requests_used INTEGER,
  requests_remaining INTEGER,
  created_at_utc TEXT NOT NULL,
  UNIQUE(returned_at_utc, endpoint_type, COALESCE(event_id, ''))
);
CREATE TABLE IF NOT EXISTS wagers (
  wager_id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id INTEGER NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  bookmaker_key TEXT NOT NULL,
  bookmaker_title TEXT,
  bookmaker_last_update_utc TEXT,
  market_key TEXT NOT NULL,
  market_last_update_utc TEXT,
  participant TEXT NOT NULL,
  description TEXT,
  selection TEXT NOT NULL,
  point REAL,
  american_price INTEGER,
  decimal_price REAL,
  outcome_key TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  UNIQUE(snapshot_id, event_id, bookmaker_key, market_key, outcome_key)
);
CREATE TABLE IF NOT EXISTS grades (
  wager_id INTEGER PRIMARY KEY REFERENCES wagers(wager_id) ON DELETE CASCADE,
  actual_result REAL,
  grade TEXT,
  profit_units REAL,
  graded_at_utc TEXT,
  grading_source TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_wagers_event_book_market
  ON wagers(event_id, bookmaker_key, market_key);
CREATE INDEX IF NOT EXISTS idx_wagers_participant_market
  ON wagers(participant, market_key);
CREATE INDEX IF NOT EXISTS idx_snapshots_returned
  ON snapshots(returned_at_utc);
CREATE VIEW IF NOT EXISTS closing_wagers AS
SELECT w.* FROM wagers w
JOIN events e ON e.event_id=w.event_id
JOIN snapshots s ON s.snapshot_id=w.snapshot_id
WHERE s.returned_at_utc=(
  SELECT MAX(s2.returned_at_utc)
  FROM wagers w2 JOIN snapshots s2 ON s2.snapshot_id=w2.snapshot_id
  WHERE w2.event_id=w.event_id
    AND w2.bookmaker_key=w.bookmaker_key
    AND w2.market_key=w.market_key
    AND w2.outcome_key=w.outcome_key
    AND s2.returned_at_utc<=e.commence_time_utc
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso(value: str) -> str:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"sport", "bookmakers", "core_markets", "event_markets"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"Market registry missing: {sorted(missing)}")
    return data


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def usage_headers(response: requests.Response) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for header, key in (
        ("x-requests-last", "last"),
        ("x-requests-used", "used"),
        ("x-requests-remaining", "remaining"),
    ):
        try:
            result[key] = int(response.headers.get(header, ""))
        except ValueError:
            result[key] = None
    return result


def request_json(url: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
    response = requests.get(url, params=params, timeout=45)
    if response.status_code == 401:
        raise RuntimeError("Odds API key invalid or historical access unavailable.")
    if response.status_code == 429:
        raise RuntimeError("Odds API quota or rate limit reached.")
    if response.status_code == 422:
        raise RuntimeError(f"Odds API rejected request: {response.text[:500]}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Odds API response shape.")
    return payload, usage_headers(response)


def request_core(api_key: str, registry: dict[str, Any], stamp: str) -> tuple[dict[str, Any], dict[str, int | None]]:
    sport = registry["sport"]
    return request_json(
        f"{BASE_URL}/historical/sports/{sport}/odds",
        {
            "apiKey": api_key,
            "bookmakers": ",".join(registry["bookmakers"]),
            "markets": ",".join(registry["core_markets"]),
            "oddsFormat": "american",
            "dateFormat": "iso",
            "date": stamp,
        },
    )


def request_event(api_key: str, registry: dict[str, Any], event_id: str, stamp: str, markets: list[str]) -> tuple[dict[str, Any], dict[str, int | None]]:
    sport = registry["sport"]
    return request_json(
        f"{BASE_URL}/historical/sports/{sport}/events/{event_id}/odds",
        {
            "apiKey": api_key,
            "bookmakers": ",".join(registry["bookmakers"]),
            "markets": ",".join(markets),
            "oddsFormat": "american",
            "dateFormat": "iso",
            "date": stamp,
        },
    )


def american_to_decimal(price: Any) -> float | None:
    try:
        p = int(price)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    return round(1 + (p / 100 if p > 0 else 100 / abs(p)), 6)


def outcome_identity(market_key: str, outcome: dict[str, Any]) -> str:
    return "|".join(
        str(x or "")
        for x in (
            market_key,
            outcome.get("description"),
            outcome.get("name"),
            outcome.get("point"),
        )
    )


def upsert_event(con: sqlite3.Connection, event: dict[str, Any], sport: str) -> None:
    commence = iso(str(event["commence_time"]))
    con.execute(
        """INSERT INTO events
        (event_id,sport_key,commence_time_utc,game_date_utc,home_team,away_team,updated_at_utc)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(event_id) DO UPDATE SET
          commence_time_utc=excluded.commence_time_utc,
          game_date_utc=excluded.game_date_utc,
          home_team=excluded.home_team,
          away_team=excluded.away_team,
          updated_at_utc=excluded.updated_at_utc""",
        (
            event["id"], sport, commence, commence[:10],
            event.get("home_team") or "", event.get("away_team") or "", utc_now(),
        ),
    )


def insert_snapshot(con: sqlite3.Connection, requested: str, payload: dict[str, Any], usage: dict[str, int | None], endpoint_type: str, event_id: str | None) -> int:
    returned = iso(str(payload.get("timestamp") or requested))
    con.execute(
        """INSERT OR IGNORE INTO snapshots
        (requested_at_utc,returned_at_utc,endpoint_type,event_id,previous_snapshot_utc,
         next_snapshot_utc,requests_last,requests_used,requests_remaining,created_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            iso(requested), returned, endpoint_type, event_id,
            payload.get("previous_timestamp"), payload.get("next_timestamp"),
            usage.get("last"), usage.get("used"), usage.get("remaining"), utc_now(),
        ),
    )
    row = con.execute(
        "SELECT snapshot_id FROM snapshots WHERE returned_at_utc=? AND endpoint_type=? AND COALESCE(event_id,'')=COALESCE(?, '')",
        (returned, endpoint_type, event_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Unable to resolve snapshot row.")
    return int(row[0])


def ingest_event(con: sqlite3.Connection, sid: int, event: dict[str, Any], registry: dict[str, Any]) -> int:
    upsert_event(con, event, registry["sport"])
    allowed = set(registry["bookmakers"])
    inserted = 0
    for book in event.get("bookmakers", []):
        if not isinstance(book, dict) or book.get("key") not in allowed:
            continue
        for market in book.get("markets", []):
            if not isinstance(market, dict) or not market.get("key"):
                continue
            market_key = str(market["key"])
            for outcome in market.get("outcomes", []):
                if not isinstance(outcome, dict) or not outcome.get("name"):
                    continue
                participant = str(outcome.get("description") or outcome.get("name"))
                identity = outcome_identity(market_key, outcome)
                con.execute(
                    """INSERT INTO wagers
                    (snapshot_id,event_id,bookmaker_key,bookmaker_title,bookmaker_last_update_utc,
                     market_key,market_last_update_utc,participant,description,selection,point,
                     american_price,decimal_price,outcome_key,created_at_utc)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(snapshot_id,event_id,bookmaker_key,market_key,outcome_key)
                    DO UPDATE SET american_price=excluded.american_price,
                                  decimal_price=excluded.decimal_price,
                                  bookmaker_last_update_utc=excluded.bookmaker_last_update_utc,
                                  market_last_update_utc=excluded.market_last_update_utc""",
                    (
                        sid, event["id"], book["key"], book.get("title"), book.get("last_update"),
                        market_key, market.get("last_update"), participant,
                        outcome.get("description"), str(outcome["name"]), outcome.get("point"),
                        outcome.get("price"), american_to_decimal(outcome.get("price")), identity,
                        utc_now(),
                    ),
                )
                inserted += 1
    return inserted


def ingest_payload(con: sqlite3.Connection, requested: str, payload: dict[str, Any], usage: dict[str, int | None], registry: dict[str, Any], endpoint_type: str, event_id: str | None = None) -> tuple[list[str], int]:
    sid = insert_snapshot(con, requested, payload, usage, endpoint_type, event_id)
    raw = payload.get("data", [])
    events = raw if isinstance(raw, list) else [raw]
    event_ids: list[str] = []
    rows = 0
    for event in events:
        if not isinstance(event, dict) or not event.get("id") or not event.get("commence_time"):
            continue
        event_ids.append(str(event["id"]))
        rows += ingest_event(con, sid, event, registry)
    con.commit()
    return event_ids, rows


def collect(api_key: str, stamp: str, db: Path, include_event_markets: bool, max_event_requests: int, sleep_seconds: float) -> dict[str, Any]:
    registry = load_registry()
    con = connect(db)
    report: dict[str, Any] = {
        "requested_at_utc": iso(stamp), "core_requests": 0, "event_requests": 0,
        "events": 0, "wager_rows_seen": 0, "failures": [],
    }
    core, usage = request_core(api_key, registry, stamp)
    report["core_requests"] = 1
    event_ids, rows = ingest_payload(con, stamp, core, usage, registry, "core")
    report["events"] = len(set(event_ids))
    report["wager_rows_seen"] += rows

    if include_event_markets:
        markets = list(registry["event_markets"])
        for event_id in event_ids[:max_event_requests]:
            try:
                payload, event_usage = request_event(api_key, registry, event_id, stamp, markets)
                _, event_rows = ingest_payload(
                    con, stamp, payload, event_usage, registry, "event_markets", event_id
                )
                report["event_requests"] += 1
                report["wager_rows_seen"] += event_rows
            except Exception as exc:  # preserve successful events and report unsupported markets
                report["failures"].append({"event_id": event_id, "error": str(exc)})
            time.sleep(sleep_seconds)

    report.update(summary(con, db))
    return report


def summary(con: sqlite3.Connection, db: Path) -> dict[str, Any]:
    payload = {
        "generated_at_utc": utc_now(),
        "database": str(db),
        "events_total": con.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "snapshots_total": con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
        "wagers_total": con.execute("SELECT COUNT(*) FROM wagers").fetchone()[0],
        "closing_wagers_total": con.execute("SELECT COUNT(*) FROM closing_wagers").fetchone()[0],
        "graded_total": con.execute("SELECT COUNT(*) FROM grades WHERE grade IS NOT NULL").fetchone()[0],
        "books": [r[0] for r in con.execute("SELECT DISTINCT bookmaker_key FROM wagers ORDER BY 1")],
        "markets": [r[0] for r in con.execute("SELECT DISTINCT market_key FROM wagers ORDER BY 1")],
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "collect", "summary"])
    parser.add_argument("--date", help="Historical ISO timestamp, e.g. 2026-06-01T22:00:00Z")
    parser.add_argument("--api-key", default=os.getenv("ODDS_API_KEY"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--include-event-markets", action="store_true")
    parser.add_argument("--max-event-requests", type=int, default=6)
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    con = connect(args.db)
    if args.action == "init":
        print(json.dumps(summary(con, args.db), indent=2))
        return
    if args.action == "summary":
        print(json.dumps(summary(con, args.db), indent=2))
        return
    if not args.api_key:
        raise SystemExit("ODDS_API_KEY is required.")
    if not args.date:
        raise SystemExit("--date is required for collect.")
    report = collect(
        args.api_key, args.date, args.db, args.include_event_markets,
        args.max_event_requests, args.sleep,
    )
    print(json.dumps(report, indent=2))
    if report["failures"]:
        print("Some event-market requests failed; successful data was retained.")


if __name__ == "__main__":
    main()
