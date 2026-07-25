"""Sprint 15 Commit 1: build canonical WNBA market timelines from Warehouse V2.

This module does not call The Odds API. It converts already-collected sportsbook
snapshots into compact JSON artifacts used by later movement, steam and CLV engines.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
OUT_DIR = Path("data/market")
SNAPSHOTS_OUT = OUT_DIR / "market_snapshots.json"
TIMELINE_OUT = OUT_DIR / "market_timeline.json"
CLOSING_OUT = OUT_DIR / "closing_lines.json"
SUMMARY_OUT = Path("data/dashboard/wnba_market_timeline_summary.json")
SUPPORTED_BOOKS = {"draftkings", "fanduel"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def implied_probability(price: int | None) -> float | None:
    if price is None or price == 0:
        return None
    value = (-price) / ((-price) + 100) if price < 0 else 100 / (price + 100)
    return round(value, 6)


def canonical_key(row: sqlite3.Row) -> str:
    raw = "|".join(
        str(row[k] if row[k] is not None else "")
        for k in ("event_id", "bookmaker_key", "market_key", "outcome_key")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"Warehouse missing: {db}")
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Warehouse integrity check failed")
    return con


def load_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        """
        SELECT e.event_id,e.commence_time_utc,e.home_team,e.away_team,
               s.snapshot_id,s.returned_at_utc,s.requested_at_utc,
               w.bookmaker_key,w.bookmaker_title,w.market_key,w.participant,
               w.description,w.selection,w.point,w.american_price,w.decimal_price,
               w.outcome_key,w.bookmaker_last_update_utc,w.market_last_update_utc
        FROM wagers w
        JOIN snapshots s ON s.snapshot_id=w.snapshot_id
        JOIN events e ON e.event_id=w.event_id
        WHERE w.bookmaker_key IN ('draftkings','fanduel')
        ORDER BY e.event_id,w.bookmaker_key,w.market_key,w.outcome_key,s.returned_at_utc
        """
    ).fetchall()


def snapshot_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "market_id": canonical_key(row),
        "event_id": row["event_id"],
        "commence_time_utc": row["commence_time_utc"],
        "home_team": row["home_team"],
        "away_team": row["away_team"],
        "snapshot_id": row["snapshot_id"],
        "snapshot_time_utc": row["returned_at_utc"],
        "requested_at_utc": row["requested_at_utc"],
        "bookmaker": row["bookmaker_key"],
        "bookmaker_title": row["bookmaker_title"],
        "market": row["market_key"],
        "participant": row["participant"],
        "description": row["description"],
        "selection": row["selection"],
        "point": row["point"],
        "american_price": row["american_price"],
        "decimal_price": row["decimal_price"],
        "implied_probability": implied_probability(row["american_price"]),
        "outcome_key": row["outcome_key"],
        "bookmaker_last_update_utc": row["bookmaker_last_update_utc"],
        "market_last_update_utc": row["market_last_update_utc"],
    }


def changed(previous: dict[str, Any] | None, current: dict[str, Any]) -> bool:
    if previous is None:
        return True
    return any(previous.get(k) != current.get(k) for k in ("point", "american_price", "decimal_price"))


def build(rows: list[sqlite3.Row]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    snapshots: list[dict[str, Any]] = []
    for row in rows:
        record = snapshot_record(row)
        grouped[record["market_id"]].append(record)

    timelines: list[dict[str, Any]] = []
    closings: list[dict[str, Any]] = []
    for market_id, records in grouped.items():
        compact: list[dict[str, Any]] = []
        previous = None
        for record in records:
            if changed(previous, record):
                compact.append(record)
                snapshots.append(record)
                previous = record
        if not compact:
            continue
        first, last = compact[0], compact[-1]
        timeline = {
            "market_id": market_id,
            "event_id": first["event_id"],
            "commence_time_utc": first["commence_time_utc"],
            "home_team": first["home_team"],
            "away_team": first["away_team"],
            "bookmaker": first["bookmaker"],
            "market": first["market"],
            "participant": first["participant"],
            "selection": first["selection"],
            "outcome_key": first["outcome_key"],
            "opening": {"time_utc": first["snapshot_time_utc"], "point": first["point"], "american_price": first["american_price"]},
            "current": {"time_utc": last["snapshot_time_utc"], "point": last["point"], "american_price": last["american_price"]},
            "observations": compact,
            "observation_count": len(compact),
        }
        timelines.append(timeline)
        if last["snapshot_time_utc"] <= last["commence_time_utc"]:
            closings.append({
                "market_id": market_id,
                "event_id": last["event_id"],
                "commence_time_utc": last["commence_time_utc"],
                "bookmaker": last["bookmaker"],
                "market": last["market"],
                "participant": last["participant"],
                "selection": last["selection"],
                "point": last["point"],
                "american_price": last["american_price"],
                "decimal_price": last["decimal_price"],
                "implied_probability": last["implied_probability"],
                "closing_time_utc": last["snapshot_time_utc"],
            })
    snapshots.sort(key=lambda x: (x["snapshot_time_utc"], x["market_id"]))
    timelines.sort(key=lambda x: (x["commence_time_utc"], x["market_id"]))
    closings.sort(key=lambda x: (x["commence_time_utc"], x["market_id"]))
    return snapshots, timelines, closings


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def run(db: Path = DEFAULT_DB) -> dict[str, Any]:
    con = connect(db)
    rows = load_rows(con)
    snapshots, timelines, closings = build(rows)
    write_json(SNAPSHOTS_OUT, {"generated_at_utc": now_utc(), "records": snapshots})
    write_json(TIMELINE_OUT, {"generated_at_utc": now_utc(), "markets": timelines})
    write_json(CLOSING_OUT, {"generated_at_utc": now_utc(), "closing_lines": closings})
    summary = {
        "generated_at_utc": now_utc(),
        "warehouse": str(db),
        "source_rows": len(rows),
        "deduplicated_snapshots": len(snapshots),
        "markets_tracked": len(timelines),
        "closing_lines": len(closings),
        "books": sorted({x["bookmaker"] for x in snapshots}),
        "status": "READY" if timelines else "STANDBY",
    }
    write_json(SUMMARY_OUT, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    print(json.dumps(run(args.db), indent=2))


if __name__ == "__main__":
    main()
