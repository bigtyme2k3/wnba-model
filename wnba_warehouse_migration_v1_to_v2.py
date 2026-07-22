"""Idempotent migration from the legacy WNBA odds DB into Warehouse V2."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import wnba_odds_warehouse_v2 as v2

DEFAULT_LEGACY = Path("data/warehouse/wnba_odds_history.sqlite")
DEFAULT_V2 = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
DEFAULT_REPORT = Path("data/warehouse/wnba_warehouse_migration_report.json")
SOURCE = "legacy_v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def count(con: sqlite3.Connection, name: str) -> int:
    return int(con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) if exists(con, name) else 0


def decimal(price: int | None) -> float | None:
    if not price:
        return None
    return round(1 + (price / 100 if price > 0 else 100 / abs(price)), 6)


def profit(price: int | None, grade: str) -> float | None:
    if grade == "loss": return -1.0
    if grade == "push": return 0.0
    if not price: return None
    return round(price / 100 if price > 0 else 100 / abs(price), 6)


def ensure_meta(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS migration_runs(
      run_id INTEGER PRIMARY KEY AUTOINCREMENT, source_key TEXT NOT NULL,
      source_database TEXT NOT NULL, started_at_utc TEXT NOT NULL,
      finished_at_utc TEXT, status TEXT NOT NULL, report_json TEXT
    );
    CREATE TABLE IF NOT EXISTS migration_conflicts(
      conflict_id INTEGER PRIMARY KEY AUTOINCREMENT, source_key TEXT NOT NULL,
      entity_type TEXT NOT NULL, natural_key TEXT NOT NULL,
      legacy_payload TEXT, target_payload TEXT, detected_at_utc TEXT NOT NULL
    );
    """)


def inventory(legacy: sqlite3.Connection, target: sqlite3.Connection) -> dict[str, Any]:
    legacy_results = int(legacy.execute(
        "SELECT COUNT(*) FROM games WHERE home_score IS NOT NULL AND away_score IS NOT NULL"
    ).fetchone()[0])
    return {
        "legacy": {"games": count(legacy,"games"), "snapshots": count(legacy,"snapshots"),
                   "odds_rows": count(legacy,"odds"), "closing_rows": count(legacy,"closing_odds"),
                   "games_with_results": legacy_results},
        "v2": {"events": count(target,"events"), "snapshots": count(target,"snapshots"),
               "wagers": count(target,"wagers"), "grades": count(target,"grades"),
               "closing_wagers": count(target,"closing_wagers")},
    }


def snapshot_id(target: sqlite3.Connection, snap: sqlite3.Row, created: str) -> int:
    found = target.execute(
        "SELECT snapshot_id FROM snapshots WHERE returned_at_utc=? ORDER BY snapshot_id LIMIT 1",
        (snap["snapshot_time_utc"],),
    ).fetchone()
    if found:
        return int(found[0])
    target.execute("""INSERT INTO snapshots
      (requested_at_utc,returned_at_utc,endpoint_type,event_id,previous_snapshot_utc,
       next_snapshot_utc,requests_last,requests_used,requests_remaining,created_at_utc)
      VALUES (?,?,?,?,?,?,?,?,?,?)""",
      (snap["requested_at_utc"], snap["snapshot_time_utc"], "legacy_core", None,
       snap["previous_snapshot_utc"], snap["next_snapshot_utc"], snap["api_requests_last"],
       snap["api_requests_used"], snap["api_requests_remaining"], created))
    return int(target.execute("SELECT last_insert_rowid()").fetchone()[0])


def outcomes(game: sqlite3.Row, odd: sqlite3.Row) -> list[tuple[str,str,str,float|None,int|None]]:
    matchup = f"{game['away_team']} @ {game['home_team']}"
    return [
      ("h2h", game["home_team"], game["home_team"], None, odd["home_moneyline"]),
      ("h2h", game["away_team"], game["away_team"], None, odd["away_moneyline"]),
      ("spreads", game["home_team"], game["home_team"], odd["home_spread"], odd["home_spread_price"]),
      ("spreads", game["away_team"], game["away_team"], odd["away_spread"], odd["away_spread_price"]),
      ("totals", matchup, "Over", odd["total"], odd["over_price"]),
      ("totals", matchup, "Under", odd["total"], odd["under_price"]),
    ]


def grade(game: sqlite3.Row, market: str, selection: str, point: float|None) -> tuple[float|None,str|None]:
    hs, away = game["home_score"], game["away_score"]
    if hs is None or away is None: return None, None
    if market == "h2h":
        winner = game["home_team"] if hs > away else game["away_team"] if away > hs else None
        return 1.0 if selection == winner else 0.0, "push" if winner is None else "win" if selection == winner else "loss"
    if market == "spreads" and point is not None:
        selected = hs if selection == game["home_team"] else away
        opponent = away if selection == game["home_team"] else hs
        margin = selected + float(point) - opponent
        return margin, "win" if margin > 0 else "loss" if margin < 0 else "push"
    if market == "totals" and point is not None:
        actual = hs + away
        if actual == point: return actual, "push"
        won = actual > point if selection == "Over" else actual < point
        return actual, "win" if won else "loss"
    return None, None


def migrate(legacy: sqlite3.Connection, target: sqlite3.Connection, source_path: Path) -> dict[str,int]:
    ensure_meta(target)
    created = now()
    run_id = target.execute("INSERT INTO migration_runs(source_key,source_database,started_at_utc,status) VALUES (?,?,?,'running')",
                            (SOURCE,str(source_path),created)).lastrowid
    stats = {"events_upserted":0,"snapshots_resolved":0,"wagers_inserted":0,"wagers_skipped":0,"grades_upserted":0}
    games = {r["game_id"]: r for r in legacy.execute("SELECT * FROM games")}
    for g in games.values():
        completed = int(g["home_score"] is not None and g["away_score"] is not None)
        target.execute("""INSERT INTO events
          (event_id,sport_key,commence_time_utc,game_date_utc,home_team,away_team,completed,home_score,away_score,updated_at_utc)
          VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET
          commence_time_utc=excluded.commence_time_utc,game_date_utc=excluded.game_date_utc,
          home_team=excluded.home_team,away_team=excluded.away_team,
          completed=MAX(events.completed,excluded.completed),home_score=COALESCE(events.home_score,excluded.home_score),
          away_score=COALESCE(events.away_score,excluded.away_score),updated_at_utc=excluded.updated_at_utc""",
          (g["game_id"],g["sport_key"],g["commence_time_utc"],g["game_date_utc"],g["home_team"],g["away_team"],
           completed,g["home_score"],g["away_score"],created))
        stats["events_upserted"] += 1
    snap_map = {}
    for s in legacy.execute("SELECT * FROM snapshots ORDER BY snapshot_time_utc"):
        snap_map[int(s["snapshot_id"])] = snapshot_id(target,s,created); stats["snapshots_resolved"] += 1
    for o in legacy.execute("SELECT * FROM odds ORDER BY odds_id"):
        g = games.get(o["game_id"])
        if not g: continue
        sid = snap_map[int(o["snapshot_id"])]
        for market,participant,selection,point,price in outcomes(g,o):
            if price is None: continue
            key = f"{SOURCE}|{market}|{participant}|{selection}|{'' if point is None else float(point):g}"
            before = target.total_changes
            target.execute("""INSERT OR IGNORE INTO wagers
              (snapshot_id,event_id,bookmaker_key,bookmaker_title,bookmaker_last_update_utc,
               market_key,market_last_update_utc,participant,description,selection,point,
               american_price,decimal_price,outcome_key,created_at_utc)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (sid,o["game_id"],o["bookmaker_key"],o["bookmaker_title"],o["bookmaker_last_update_utc"],
               market,o["bookmaker_last_update_utc"],participant,"migrated from legacy core warehouse",
               selection,point,price,decimal(price),key,created))
            inserted = target.total_changes > before
            stats["wagers_inserted" if inserted else "wagers_skipped"] += 1
            w = target.execute("SELECT * FROM wagers WHERE snapshot_id=? AND event_id=? AND bookmaker_key=? AND market_key=? AND outcome_key=?",
                               (sid,o["game_id"],o["bookmaker_key"],market,key)).fetchone()
            actual,result = grade(g,market,selection,point)
            if w and result:
                target.execute("""INSERT INTO grades(wager_id,actual_result,grade,profit_units,graded_at_utc,grading_source,notes)
                  VALUES (?,?,?,?,?,?,?) ON CONFLICT(wager_id) DO UPDATE SET
                  actual_result=excluded.actual_result,grade=excluded.grade,profit_units=excluded.profit_units,
                  graded_at_utc=excluded.graded_at_utc,grading_source=excluded.grading_source,notes=excluded.notes""",
                  (w["wager_id"],actual,result,profit(price,result),created,"legacy_v1_final_scores","verified migration grade"))
                stats["grades_upserted"] += 1
    target.execute("UPDATE migration_runs SET finished_at_utc=?,status='complete',report_json=? WHERE run_id=?",
                   (now(),json.dumps(stats,sort_keys=True),run_id))
    target.commit()
    return stats


def validate(legacy: sqlite3.Connection, target: sqlite3.Connection) -> dict[str,Any]:
    dupes = int(target.execute("""SELECT COUNT(*) FROM (SELECT snapshot_id,event_id,bookmaker_key,market_key,outcome_key,COUNT(*) c
      FROM wagers GROUP BY 1,2,3,4,5 HAVING c>1)""").fetchone()[0])
    migrated = int(target.execute("SELECT COUNT(*) FROM wagers WHERE description='migrated from legacy core warehouse'").fetchone()[0])
    legacy_results = int(legacy.execute("SELECT COUNT(*) FROM games WHERE home_score IS NOT NULL AND away_score IS NOT NULL").fetchone()[0])
    v2_results = int(target.execute("SELECT COUNT(*) FROM events WHERE home_score IS NOT NULL AND away_score IS NOT NULL").fetchone()[0])
    passed = count(target,"events") >= count(legacy,"games") and migrated > 0 and v2_results >= legacy_results and dupes == 0
    return {"legacy_games":count(legacy,"games"),"v2_events":count(target,"events"),
            "legacy_snapshots":count(legacy,"snapshots"),"v2_snapshots":count(target,"snapshots"),
            "legacy_odds_rows":count(legacy,"odds"),"migrated_wagers":migrated,
            "legacy_games_with_results":legacy_results,"v2_events_with_results":v2_results,
            "duplicate_natural_keys":dupes,"passed":passed}


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--legacy-db",type=Path,default=DEFAULT_LEGACY)
    p.add_argument("--v2-db",type=Path,default=DEFAULT_V2); p.add_argument("--report",type=Path,default=DEFAULT_REPORT)
    p.add_argument("--execute",action="store_true"); a=p.parse_args()
    if not a.legacy_db.exists(): raise SystemExit(f"Legacy database not found: {a.legacy_db}")
    legacy=sqlite3.connect(a.legacy_db); legacy.row_factory=sqlite3.Row
    target=v2.connect(a.v2_db)
    report={"generated_at_utc":now(),"mode":"execute" if a.execute else "inventory","before":inventory(legacy,target)}
    if a.execute:
        report["migration"]=migrate(legacy,target,a.legacy_db); report["validation"]=validate(legacy,target)
        report["after"]=inventory(legacy,target)
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    if a.execute and not report["validation"]["passed"]: raise SystemExit("Migration validation failed")

if __name__ == "__main__": main()
