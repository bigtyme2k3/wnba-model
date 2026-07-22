"""Migrate the legacy WNBA core-odds warehouse into Warehouse V2.

The migration is idempotent. It preserves legacy event IDs and snapshot times,
converts each legacy game-line row into independent wager outcomes, carries final
scores into V2, grades verified core markets, and records a detailed audit trail.

Default mode is read-only inventory. Pass --execute to write to V2.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import wnba_odds_warehouse_v2 as v2

LEGACY_DB = Path("data/warehouse/wnba_odds_history.sqlite")
V2_DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
REPORT = Path("data/warehouse/wnba_warehouse_migration_report.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(con.execute(sql, params).fetchall())


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?", (name,)
    ).fetchone() is not None


def count(con: sqlite3.Connection, table: str) -> int:
    if not table_exists(con, table):
        return 0
    return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def inventory(legacy: sqlite3.Connection, target: sqlite3.Connection) -> dict[str, Any]:
    legacy_games = count(legacy, "games")
    legacy_snapshots = count(legacy, "snapshots")
    legacy_odds = count(legacy, "odds")
    legacy_results = 0
    if table_exists(legacy, "games"):
        legacy_results = int(legacy.execute(
            "SELECT COUNT(*) FROM games WHERE home_score IS NOT NULL AND away_score IS NOT NULL"
        ).fetchone()[0])
    return {
        "generated_at_utc": utc_now(),
        "legacy": {
            "database": str(LEGACY_DB),
            "games": legacy_games,
            "snapshots": legacy_snapshots,
            "odds_rows": legacy_odds,
            "games_with_results": legacy_results,
            "closing_rows": count(legacy, "closing_odds"),
        },
        "v2_before": {
            "database": str(V2_DB),
            "events": count(target, "events"),
            "snapshots": count(target, "snapshots"),
            "wagers": count(target, "wagers"),
            "grades": count(target, "grades"),
            "closing_wagers": count(target, "closing_wagers"),
        },
    }


def ensure_audit_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS migration_sources (
      source_key TEXT PRIMARY KEY,
      source_database TEXT NOT NULL,
      migrated_at_utc TEXT NOT NULL,
      notes TEXT
    );
    CREATE TABLE IF NOT EXISTS migration_record_map (
      source_key TEXT NOT NULL,
      source_table TEXT NOT NULL,
      source_pk TEXT NOT NULL,
      target_table TEXT NOT NULL,
      target_pk TEXT NOT NULL,
      migrated_at_utc TEXT NOT NULL,
      PRIMARY KEY(source_key, source_table, source_pk, target_table, target_pk)
    );
    CREATE TABLE IF NOT EXISTS migration_conflicts (
      conflict_id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_key TEXT NOT NULL,
      entity_type TEXT NOT NULL,
      natural_key TEXT NOT NULL,
      legacy_payload TEXT,
      target_payload TEXT,
      detected_at_utc TEXT NOT NULL,
      resolution TEXT NOT NULL DEFAULT 'review'
    );
    """)


def american_to_decimal(price: int | None) -> float | None:
    if price is None or price == 0:
        return None
    return round(1 + (price / 100 if price > 0 else 100 / abs(price)), 6)


def outcome_key(market: str, participant: str, selection: str, point: float | None) -> str:
    point_text = "" if point is None else f"|{float(point):g}"
    return f"legacy_v1|{market}|{participant}|{selection}{point_text}"


def upsert_event(target: sqlite3.Connection, game: sqlite3.Row, created: str) -> None:
    target.execute("""
      INSERT INTO events
      (event_id,sport_key,commence_time_utc,game_date_utc,home_team,away_team,
       completed,home_score,away_score,updated_at_utc)
      VALUES (?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(event_id) DO UPDATE SET
       commence_time_utc=excluded.commence_time_utc,
       game_date_utc=excluded.game_date_utc,
       home_team=excluded.home_team,
       away_team=excluded.away_team,
       completed=MAX(events.completed,excluded.completed),
       home_score=COALESCE(events.home_score,excluded.home_score),
       away_score=COALESCE(events.away_score,excluded.away_score),
       updated_at_utc=excluded.updated_at_utc
    """, (
        game["game_id"], game["sport_key"], game["commence_time_utc"], game["game_date_utc"],
        game["home_team"], game["away_team"], int(game["home_score"] is not None and game["away_score"] is not None),
        game["home_score"], game["away_score"], created,
    ))


def upsert_snapshot(target: sqlite3.Connection, snap: sqlite3.Row, created: str) -> int:
    target.execute("""
      INSERT OR IGNORE INTO snapshots
      (requested_at_utc,returned_at_utc,endpoint_type,event_id,previous_snapshot_utc,
       next_snapshot_utc,requests_last,requests_used,requests_remaining,created_at_utc)
      VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        snap["requested_at_utc"], snap["snapshot_time_utc"], "legacy_core", None,
        snap["previous_snapshot_utc"], snap["next_snapshot_utc"], snap["api_requests_last"],
        snap["api_requests_used"], snap["api_requests_remaining"], created,
    ))
    row = target.execute(
        "SELECT snapshot_id FROM snapshots WHERE returned_at_utc=? AND endpoint_type='legacy_core' AND event_id IS NULL",
        (snap["snapshot_time_utc"],),
    ).fetchone()
    if row is None:
        # A core snapshot may already exist under the V2 endpoint label. Reuse it.
        row = target.execute(
            "SELECT snapshot_id FROM snapshots WHERE returned_at_utc=? ORDER BY snapshot_id LIMIT 1",
            (snap["snapshot_time_utc"],),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"Unable to resolve target snapshot for {snap['snapshot_time_utc']}")
    return int(row[0])


def legacy_outcomes(game: sqlite3.Row, odd: sqlite3.Row) -> Iterable[dict[str, Any]]:
    book = odd["bookmaker_key"]
    common = {
        "event_id": odd["game_id"], "bookmaker_key": book,
        "bookmaker_title": odd["bookmaker_title"],
        "bookmaker_last_update_utc": odd["bookmaker_last_update_utc"],
    }
    pairs = [
        ("h2h", game["home_team"], game["home_team"], None, odd["home_moneyline"]),
        ("h2h", game["away_team"], game["away_team"], None, odd["away_moneyline"]),
        ("spreads", game["home_team"], game["home_team"], odd["home_spread"], odd["home_spread_price"]),
        ("spreads", game["away_team"], game["away_team"], odd["away_spread"], odd["away_spread_price"]),
        ("totals", f"{game['away_team']} @ {game['home_team']}", "Over", odd["total"], odd["over_price"]),
        ("totals", f"{game['away_team']} @ {game['home_team']}", "Under", odd["total"], odd["under_price"]),
    ]
    for market, participant, selection, point, price in pairs:
        if price is None:
            continue
        yield {
            **common, "market_key": market, "market_last_update_utc": odd["bookmaker_last_update_utc"],
            "participant": participant, "description": "migrated from legacy core warehouse",
            "selection": selection, "point": point, "american_price": price,
            "decimal_price": american_to_decimal(price),
            "outcome_key": outcome_key(market, participant, selection, point),
        }


def grade_core(event: sqlite3.Row, wager: sqlite3.Row) -> tuple[float | None, str | None]:
    hs, as_ = event["home_score"], event["away_score"]
    if hs is None or as_ is None:
        return None, None
    market, selection, point = wager["market_key"], wager["selection"], wager["point"]
    if market == "h2h":
        winner = event["home_team"] if hs > as_ else event["away_team"] if as_ > hs else None
        return (1.0 if selection == winner else 0.0), ("push" if winner is None else "win" if selection == winner else "loss")
    if market == "spreads" and point is not None:
        score = (hs if selection == event["home_team"] else as_) + float(point)
        opponent = as_ if selection == event["home_team"] else hs
        return score - opponent, "win" if score > opponent else "loss" if score < opponent else "push"
    if market == "totals" and point is not None:
        actual = hs + as_
        if actual == point:
            return actual, "push"
        won = actual > point if selection == "Over" else actual < point
        return actual, "win" if won else "loss"
    return None, None


def profit_units(price: int | None, grade: str | None) -> float | None:
    if grade is None:
        return None
    if grade == "loss":
        return -1.0
    if grade == "push":
        return 0.0
    if price is None or price == 0:
        return None
    return round(price / 100 if price > 0 else 100 / abs(price), 6)


def migrate(legacy: sqlite3.Connection, target: sqlite3.Connection) -> dict[str, int]:
    ensure_audit_schema(target)
    created = utc_now()
    stats = {"events_upserted": 0, "snapshots_resolved": 0, "wagers_inserted": 0,
             "wagers_skipped": 0, "grades_upserted": 0, "conflicts": 0}
    games = {r["game_id"]: r for r in rows(legacy, "SELECT * FROM games")}
    for game in games.values():
        upsert_event(target, game, created)
        stats["events_upserted"] += 1

    snapshot_map: dict[int, int] = {}
    for snap in rows(legacy, "SELECT * FROM snapshots ORDER BY snapshot_time_utc"):
        snapshot_map[int(snap["snapshot_id"])] = upsert_snapshot(target, snap, created)
        stats["snapshots_resolved"] += 1

    for odd in rows(legacy, "SELECT * FROM odds ORDER BY odds_id"):
        game = games.get(odd["game_id"])
        if game is None:
            continue
        sid = snapshot_map[int(odd["snapshot_id"])]
        for payload in legacy_outcomes(game, odd):
            before = target.total_changes
            target.execute("""
              INSERT OR IGNORE INTO wagers
              (snapshot_id,event_id,bookmaker_key,bookmaker_title,bookmaker_last_update_utc,
               market_key,market_last_update_utc,participant,description,selection,point,
               american_price,decimal_price,outcome_key,created_at_utc)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (sid, payload["event_id"], payload["bookmaker_key"], payload["bookmaker_title"],
                  payload["bookmaker_last_update_utc"], payload["market_key"], payload["market_last_update_utc"],
                  payload["participant"], payload["description"], payload["selection"], payload["point"],
                  payload["american_price"], payload["decimal_price"], payload["outcome_key"], created))
            inserted = target.total_changes > before
            wager = target.execute("""
              SELECT * FROM wagers WHERE snapshot_id=? AND event_id=? AND bookmaker_key=?
               AND market_key=? AND outcome_key=?
            """, (sid, payload["event_id"], payload["bookmaker_key"], payload["market_key"], payload["outcome_key"])).fetchone()
            if inserted:
                stats["wagers_inserted"] += 1
            else:
                stats["wagers_skipped"] += 1
            if wager is not None:
                actual, grade = grade_core(game, wager)
                if grade is not None:
                    target.execute("""
                      INSERT INTO grades(wager_id,actual_result,grade,profit_units,graded_at_utc,grading_source,notes)
                      VALUES (?,?,?,?,?,?,?)
                      ON CONFLICT(wager_id) DO UPDATE SET
                       actual_result=excluded.actual_result,grade=excluded.grade,
                       profit_units=excluded.profit_units,graded_at_utc=excluded.graded_at_utc,
                       grading_source=excluded.grading_source,notes=excluded.notes
                    """, (wager["wager_id"], actual, grade, profit_units(wager["american_price"], grade),
                          created, "legacy_v1_final_scores", "verified core-market migration grade"))
                    stats["grades_upserted"] += 1

    target.execute("""
      INSERT INTO migration_sources(source_key,source_database,migrated_at_utc,notes)
      VALUES ('legacy_v1',?,?,?)
      ON CONFLICT(source_key) DO UPDATE SET migrated_at_utc=excluded.migrated_at_utc,notes=excluded.notes
    """, (str(LEGACY_DB), created, json.dumps(stats, sort_keys=True)))
    target.commit()
    return stats


def validate(legacy: sqlite3.Connection, target: sqlite3.Connection) -> dict[str, Any]:
    duplicate_wagers = int(target.execute("""
      SELECT COUNT(*) FROM (
       SELECT snapshot_id,event_id,bookmaker_key,market_key,outcome_key,COUNT(*) c
       FROM wagers GROUP BY 1,2,3,4,5 HAVING c>1
      )
    """).fetchone()[0])
    migrated = int(target.execute(
        "SELECT COUNT(*) FROM wagers WHERE description='migrated from legacy core warehouse'"
    ).fetchone()[0])
    expected_max = count(legacy, "odds") * 6
    result_games_legacy = int(legacy.execute(
        "SELECT COUNT(*) FROM games WHERE home_score IS NOT NULL AND away_score IS NOT NULL"
    ).fetchone()[0])
    result_games_v2 = int(target.execute(
        "SELECT COUNT(*) FROM events WHERE home_score IS NOT NULL AND away_score IS NOT NULL"
    ).fetchone()[0])
    return {
        "legacy_games": count(legacy, "games"),
        "v2_events": count(target, "events"),
        "legacy_snapshots": count(legacy, "snapshots"),
        "v2_snapshots": count(target, "snapshots"),
        "legacy_odds_rows": count(legacy, "odds"),
        "migrated_wagers": migrated,
        "expected_migrated_wagers_upper_bound": expected_max,
        "legacy_games_with_results": result_games_legacy,
        "v2_events_with_results": result_games_v2,
        "duplicate_natural_keys": duplicate_wagers,
        "passed": (
            count(target, "events") >= count(legacy, "games")
            and migrated > 0
            and result_games_v2 >= result_games_legacy
            and duplicate_wagers == 0
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-db", type=Path, default=LEGACY_DB)
    parser.add_argument("--v2-db", type=Path, default=V2_DB)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    global LEGACY_DB, V2_DB, REPORT
    LEGACY_DB, V2_DB, REPORT = args.legacy_db, args.v2_db, args.report
    if not LEGACY_DB.exists():
        raise SystemExit(f"Legacy database not found: {LEGACY_DB}")
    legacy = sqlite3.connect(LEGACY_DB)
    legacy.row_factory = sqlite3.Row
    target = v2.connect(V2_DB)
    report = inventory(legacy, target)
    report["mode"] = "execute" if args.execute else "inventory"
    if args.execute:
        report["migration"] = migrate(legacy, target)
        report["validation"] = validate(legacy, target)
        report["v2_after"] = inventory(legacy, target)["v2_before"]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if args.execute and not report["validation"]["passed"]:
        raise SystemExit("Migration validation failed")


if __name__ == "__main__":
    main()
