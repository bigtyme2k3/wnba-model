"""Historical WNBA odds warehouse v2.

Primary source: The Odds API historical endpoints.
Books: DraftKings, FanDuel, Fanatics only.
Each sportsbook outcome is stored independently. No synthetic markets or prices.
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
REGISTRY = Path("config/market_registry.json")
DEFAULT_DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
SUMMARY = Path("data/warehouse/wnba_odds_warehouse_v2_summary.json")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS events(
 event_id TEXT PRIMARY KEY, sport_key TEXT NOT NULL, commence_time_utc TEXT NOT NULL,
 game_date_utc TEXT NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
 completed INTEGER NOT NULL DEFAULT 0, home_score REAL, away_score REAL,
 updated_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots(
 snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, requested_at_utc TEXT NOT NULL,
 returned_at_utc TEXT NOT NULL, endpoint_type TEXT NOT NULL,
 event_id TEXT NOT NULL DEFAULT '', previous_snapshot_utc TEXT, next_snapshot_utc TEXT,
 requests_last INTEGER, requests_used INTEGER, requests_remaining INTEGER,
 created_at_utc TEXT NOT NULL,
 UNIQUE(returned_at_utc, endpoint_type, event_id)
);
CREATE TABLE IF NOT EXISTS wagers(
 wager_id INTEGER PRIMARY KEY AUTOINCREMENT,
 snapshot_id INTEGER NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
 event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
 bookmaker_key TEXT NOT NULL, bookmaker_title TEXT, bookmaker_last_update_utc TEXT,
 market_key TEXT NOT NULL, market_last_update_utc TEXT,
 participant TEXT NOT NULL, description TEXT, selection TEXT NOT NULL,
 point REAL, american_price INTEGER, decimal_price REAL,
 outcome_key TEXT NOT NULL, created_at_utc TEXT NOT NULL,
 UNIQUE(snapshot_id,event_id,bookmaker_key,market_key,outcome_key)
);
CREATE TABLE IF NOT EXISTS grades(
 wager_id INTEGER PRIMARY KEY REFERENCES wagers(wager_id) ON DELETE CASCADE,
 actual_result REAL, grade TEXT, profit_units REAL, graded_at_utc TEXT,
 grading_source TEXT, notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_wagers_lookup
 ON wagers(event_id,bookmaker_key,market_key,outcome_key);
CREATE INDEX IF NOT EXISTS idx_wagers_participant
 ON wagers(participant,market_key);
CREATE VIEW IF NOT EXISTS closing_wagers AS
SELECT w.* FROM wagers w
JOIN events e ON e.event_id=w.event_id
JOIN snapshots s ON s.snapshot_id=w.snapshot_id
WHERE s.returned_at_utc=(
 SELECT MAX(s2.returned_at_utc)
 FROM wagers w2 JOIN snapshots s2 ON s2.snapshot_id=w2.snapshot_id
 WHERE w2.event_id=w.event_id AND w2.bookmaker_key=w.bookmaker_key
 AND w2.market_key=w.market_key AND w2.outcome_key=w.outcome_key
 AND s2.returned_at_utc<=e.commence_time_utc
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso(value: str) -> str:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def registry() -> dict[str, Any]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for key in ("sport", "bookmakers", "core_markets", "event_markets"):
        if key not in data:
            raise RuntimeError(f"Market registry missing {key}")
    return data


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def usage(response: requests.Response) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for header, key in (("x-requests-last", "last"), ("x-requests-used", "used"),
                        ("x-requests-remaining", "remaining")):
        try:
            out[key] = int(response.headers.get(header, ""))
        except ValueError:
            out[key] = None
    return out


def get_json(url: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int | None]]:
    response = requests.get(url, params=params, timeout=45)
    if response.status_code == 401:
        raise RuntimeError("ODDS_API_KEY invalid or historical access unavailable")
    if response.status_code == 429:
        raise RuntimeError("The Odds API quota/rate limit was reached")
    if response.status_code == 422:
        raise RuntimeError(f"The Odds API rejected request: {response.text[:400]}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Odds API response")
    return payload, usage(response)


def request_core(key: str, cfg: dict[str, Any], stamp: str):
    return get_json(
        f"{BASE_URL}/historical/sports/{cfg['sport']}/odds",
        {"apiKey": key, "date": stamp, "dateFormat": "iso", "oddsFormat": "american",
         "bookmakers": ",".join(cfg["bookmakers"]),
         "markets": ",".join(cfg["core_markets"])},
    )


def request_event(key: str, cfg: dict[str, Any], event_id: str, stamp: str):
    return get_json(
        f"{BASE_URL}/historical/sports/{cfg['sport']}/events/{event_id}/odds",
        {"apiKey": key, "date": stamp, "dateFormat": "iso", "oddsFormat": "american",
         "bookmakers": ",".join(cfg["bookmakers"]),
         "markets": ",".join(cfg["event_markets"])},
    )


def decimal_price(value: Any) -> float | None:
    try:
        price = int(value)
    except (TypeError, ValueError):
        return None
    return round(1 + (price / 100 if price > 0 else 100 / abs(price)), 6) if price else None


def event_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("data", [])
    return raw if isinstance(raw, list) else ([raw] if isinstance(raw, dict) else [])


def add_snapshot(con: sqlite3.Connection, requested: str, payload: dict[str, Any],
                 headers: dict[str, int | None], endpoint: str, event_id: str = "") -> int:
    returned = iso(str(payload.get("timestamp") or requested))
    con.execute("""INSERT OR IGNORE INTO snapshots
      (requested_at_utc,returned_at_utc,endpoint_type,event_id,previous_snapshot_utc,
       next_snapshot_utc,requests_last,requests_used,requests_remaining,created_at_utc)
      VALUES (?,?,?,?,?,?,?,?,?,?)""",
      (iso(requested), returned, endpoint, event_id, payload.get("previous_timestamp"),
       payload.get("next_timestamp"), headers.get("last"), headers.get("used"),
       headers.get("remaining"), now()))
    row = con.execute("""SELECT snapshot_id FROM snapshots
      WHERE returned_at_utc=? AND endpoint_type=? AND event_id=?""",
      (returned, endpoint, event_id)).fetchone()
    if row is None:
        raise RuntimeError("Could not resolve snapshot")
    return int(row[0])


def add_event(con: sqlite3.Connection, game: dict[str, Any], sport: str) -> None:
    commence = iso(str(game["commence_time"]))
    con.execute("""INSERT INTO events
      (event_id,sport_key,commence_time_utc,game_date_utc,home_team,away_team,updated_at_utc)
      VALUES (?,?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET
      commence_time_utc=excluded.commence_time_utc,game_date_utc=excluded.game_date_utc,
      home_team=excluded.home_team,away_team=excluded.away_team,updated_at_utc=excluded.updated_at_utc""",
      (game["id"], sport, commence, commence[:10], game.get("home_team") or "",
       game.get("away_team") or "", now()))


def add_wagers(con: sqlite3.Connection, sid: int, game: dict[str, Any], cfg: dict[str, Any]) -> int:
    add_event(con, game, cfg["sport"])
    allowed = set(cfg["bookmakers"])
    count = 0
    for book in game.get("bookmakers", []):
        if not isinstance(book, dict) or book.get("key") not in allowed:
            continue
        for market in book.get("markets", []):
            if not isinstance(market, dict) or not market.get("key"):
                continue
            market_key = str(market["key"])
            for outcome in market.get("outcomes", []):
                if not isinstance(outcome, dict) or not outcome.get("name"):
                    continue
                participant = str(outcome.get("description") or outcome["name"])
                outcome_key = "|".join(str(x or "") for x in
                    (market_key, outcome.get("description"), outcome.get("name"), outcome.get("point")))
                con.execute("""INSERT INTO wagers
                  (snapshot_id,event_id,bookmaker_key,bookmaker_title,bookmaker_last_update_utc,
                   market_key,market_last_update_utc,participant,description,selection,point,
                   american_price,decimal_price,outcome_key,created_at_utc)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(snapshot_id,event_id,bookmaker_key,market_key,outcome_key)
                  DO UPDATE SET american_price=excluded.american_price,
                  decimal_price=excluded.decimal_price,
                  bookmaker_last_update_utc=excluded.bookmaker_last_update_utc,
                  market_last_update_utc=excluded.market_last_update_utc""",
                  (sid, game["id"], book["key"], book.get("title"), book.get("last_update"),
                   market_key, market.get("last_update"), participant, outcome.get("description"),
                   str(outcome["name"]), outcome.get("point"), outcome.get("price"),
                   decimal_price(outcome.get("price")), outcome_key, now()))
                count += 1
    return count


def ingest(con: sqlite3.Connection, requested: str, payload: dict[str, Any],
           headers: dict[str, int | None], cfg: dict[str, Any], endpoint: str,
           event_id: str = "") -> tuple[list[str], int]:
    sid = add_snapshot(con, requested, payload, headers, endpoint, event_id)
    ids, count = [], 0
    for game in event_rows(payload):
        if not game.get("id") or not game.get("commence_time"):
            continue
        ids.append(str(game["id"]))
        count += add_wagers(con, sid, game, cfg)
    con.commit()
    return ids, count


def summarize(con: sqlite3.Connection, db: Path) -> dict[str, Any]:
    result = {
        "generated_at_utc": now(), "database": str(db),
        "events": con.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "snapshots": con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
        "wagers": con.execute("SELECT COUNT(*) FROM wagers").fetchone()[0],
        "closing_wagers": con.execute("SELECT COUNT(*) FROM closing_wagers").fetchone()[0],
        "graded": con.execute("SELECT COUNT(*) FROM grades WHERE grade IS NOT NULL").fetchone()[0],
        "books": [r[0] for r in con.execute("SELECT DISTINCT bookmaker_key FROM wagers ORDER BY 1")],
        "markets": [r[0] for r in con.execute("SELECT DISTINCT market_key FROM wagers ORDER BY 1")],
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def collect(key: str, stamp: str, db: Path, event_markets: bool,
            max_events: int, pause: float) -> dict[str, Any]:
    cfg, con = registry(), connect(db)
    report: dict[str, Any] = {"requested_at_utc": iso(stamp), "core_requests": 1,
        "event_requests": 0, "wager_rows_seen": 0, "failures": []}
    payload, headers = request_core(key, cfg, stamp)
    ids, count = ingest(con, stamp, payload, headers, cfg, "core")
    report["events_seen"] = len(set(ids)); report["wager_rows_seen"] += count
    if event_markets:
        for event_id in ids[:max_events]:
            try:
                extra, extra_headers = request_event(key, cfg, event_id, stamp)
                _, count = ingest(con, stamp, extra, extra_headers, cfg, "event_markets", event_id)
                report["event_requests"] += 1; report["wager_rows_seen"] += count
            except Exception as exc:
                report["failures"].append({"event_id": event_id, "error": str(exc)})
            time.sleep(pause)
    report["warehouse"] = summarize(con, db)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "collect", "summary"])
    parser.add_argument("--date")
    parser.add_argument("--api-key", default=os.getenv("ODDS_API_KEY"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--include-event-markets", action="store_true")
    parser.add_argument("--max-event-requests", type=int, default=6)
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()
    con = connect(args.db)
    if args.action in {"init", "summary"}:
        print(json.dumps(summarize(con, args.db), indent=2)); return
    if not args.api_key:
        raise SystemExit("ODDS_API_KEY is required")
    if not args.date:
        raise SystemExit("--date is required")
    print(json.dumps(collect(args.api_key, args.date, args.db,
        args.include_event_markets, args.max_event_requests, args.sleep), indent=2))


if __name__ == "__main__":
    main()
