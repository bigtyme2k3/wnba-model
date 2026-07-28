"""Bridge current line-shopping output into the canonical V2 odds warehouse.

The existing line_shopping.py collector is the only network caller. This bridge reuses
its exact DraftKings/FanDuel rows, preserving listed prices without fabrication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from wnba_odds_warehouse_v2 import connect, decimal_price, now, summarize

DEFAULT_INPUT = Path("data/raw/line_shopping_today.csv")
DEFAULT_DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
CATALOG = Path("data/warehouse/sprint24_phase2_live_market_catalog.json")
BOOKS = {"draftkings", "fanduel"}


def utc_iso(value: object) -> str:
    dt = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(dt):
        raise ValueError(f"Invalid commence time: {value!r}")
    return dt.to_pydatetime().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def split_game(value: object) -> tuple[str, str]:
    text = str(value or "")
    if " @ " not in text:
        return "", ""
    away, home = text.split(" @ ", 1)
    return away.strip(), home.strip()


def outcome_key(row: pd.Series) -> str:
    raw = "|".join(str(row.get(k, "") or "") for k in ("market_key", "player", "team", "side", "line"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def add_snapshot(con: sqlite3.Connection, stamp: str) -> int:
    con.execute(
        """INSERT OR IGNORE INTO snapshots
        (requested_at_utc,returned_at_utc,endpoint_type,event_id,created_at_utc)
        VALUES (?,?,?,?,?)""",
        (stamp, stamp, "live_line_shopping", "", stamp),
    )
    row = con.execute(
        "SELECT snapshot_id FROM snapshots WHERE returned_at_utc=? AND endpoint_type=? AND event_id=''",
        (stamp, "live_line_shopping"),
    ).fetchone()
    if row is None:
        raise RuntimeError("Could not create live snapshot")
    return int(row[0])


def build(input_path: Path = DEFAULT_INPUT, db_path: Path = DEFAULT_DB) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(f"Live line-shopping file missing: {input_path}")
    frame = pd.read_csv(input_path, low_memory=False)
    required = {"event_id", "game", "commence_time", "market_key", "side", "book_key", "line", "odds"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"Live line-shopping schema missing: {missing}")

    frame["book_key"] = frame["book_key"].astype(str).str.lower()
    frame = frame[frame["book_key"].isin(BOOKS)].copy()
    frame = frame[frame["event_id"].notna() & frame["commence_time"].notna()].copy()
    frame["odds"] = pd.to_numeric(frame["odds"], errors="coerce")
    frame["line"] = pd.to_numeric(frame["line"], errors="coerce")
    frame = frame[frame["odds"].notna()].copy()

    stamp = now()
    con = connect(db_path)
    sid = add_snapshot(con, stamp)
    events_written: set[str] = set()
    wagers_written = 0
    prop_rows = 0

    for _, row in frame.iterrows():
        event_id = str(row["event_id"])
        commence = utc_iso(row["commence_time"])
        away, home = split_game(row.get("game"))
        con.execute(
            """INSERT INTO events
            (event_id,sport_key,commence_time_utc,game_date_utc,home_team,away_team,updated_at_utc)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET
            commence_time_utc=excluded.commence_time_utc,game_date_utc=excluded.game_date_utc,
            home_team=excluded.home_team,away_team=excluded.away_team,updated_at_utc=excluded.updated_at_utc""",
            (event_id, "basketball_wnba", commence, commence[:10], home, away, stamp),
        )
        events_written.add(event_id)

        market_key = str(row.get("market_key") or "")
        player = str(row.get("player") or "").strip()
        team = str(row.get("team") or "").strip()
        side = str(row.get("side") or "").strip()
        participant = player or team or side
        description = player or team or None
        price = int(float(row["odds"]))
        point = None if pd.isna(row.get("line")) else float(row.get("line"))
        con.execute(
            """INSERT INTO wagers
            (snapshot_id,event_id,bookmaker_key,bookmaker_title,bookmaker_last_update_utc,
             market_key,market_last_update_utc,participant,description,selection,point,
             american_price,decimal_price,outcome_key,created_at_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(snapshot_id,event_id,bookmaker_key,market_key,outcome_key)
            DO UPDATE SET american_price=excluded.american_price,decimal_price=excluded.decimal_price,
            bookmaker_last_update_utc=excluded.bookmaker_last_update_utc,
            market_last_update_utc=excluded.market_last_update_utc""",
            (sid, event_id, row["book_key"], row.get("book_title"), stamp,
             market_key, stamp, participant, description, side, point, price,
             decimal_price(price), outcome_key(row), stamp),
        )
        wagers_written += 1
        prop_rows += int(str(row.get("market_type") or "").upper() == "PROP")

    con.commit()
    warehouse = summarize(con, db_path)
    con.close()
    report = {
        "generated_at_utc": stamp,
        "status": "PASS" if events_written and wagers_written else "WARN",
        "source": str(input_path),
        "books": sorted(BOOKS),
        "input_rows": int(len(frame)),
        "events_ingested": len(events_written),
        "wagers_ingested": wagers_written,
        "player_prop_rows": prop_rows,
        "warehouse": warehouse,
        "production_recommendations_changed": False,
    }
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    build(args.input, args.db)


if __name__ == "__main__":
    main()
