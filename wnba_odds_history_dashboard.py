"""Build dashboard-ready analytics from the compact WNBA odds history SQLite warehouse."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path("data/warehouse/wnba_odds_history.sqlite")
OUT = Path("data/dashboard/wnba_odds_history_dashboard.json")
WAREHOUSE_OUT = Path("data/warehouse/wnba_odds_history_dashboard.json")
RESULTS_OUT = Path("data/dashboard/wnba_odds_history_results.json")
PLAN_OUT = Path("data/warehouse/wnba_odds_history_backfill_plan.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def scalar(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = con.execute(sql, params).fetchone()
    return row[0] if row else None


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def sample_milestone(graded_games: int) -> dict[str, Any]:
    levels = [
        (50, "exploration", "Explore broad patterns, but do not trust small splits."),
        (100, "initial_testing", "Begin testing simple, pre-defined hypotheses."),
        (200, "season_scale", "Use for stronger season-level research and validation."),
    ]
    reached = [level for level in levels if graded_games >= level[0]]
    current = reached[-1] if reached else (0, "pipeline_validation", "The pipeline works, but the sample is still small.")
    next_level = next((level for level in levels if graded_games < level[0]), None)
    return {
        "current": {"games": current[0], "name": current[1], "meaning": current[2]},
        "next": None if next_level is None else {
            "games": next_level[0],
            "name": next_level[1],
            "games_needed": next_level[0] - graded_games,
            "meaning": next_level[2],
        },
        "research_ready": graded_games >= 100,
        "season_scale_ready": graded_games >= 200,
    }


def build(db_path: Path = DB) -> dict[str, Any]:
    if not db_path.exists():
        raise SystemExit(f"Warehouse database not found: {db_path}")

    con = sqlite3.connect(db_path)
    integrity = scalar(con, "PRAGMA integrity_check")
    games = int(scalar(con, "SELECT COUNT(*) FROM games") or 0)
    snapshots = int(scalar(con, "SELECT COUNT(*) FROM snapshots") or 0)
    odds_rows = int(scalar(con, "SELECT COUNT(*) FROM odds") or 0)
    completed_games = int(scalar(con, "SELECT COUNT(*) FROM games WHERE completed=1 AND home_score IS NOT NULL AND away_score IS NOT NULL") or 0)
    collected_snapshot_days = int(scalar(con, "SELECT COUNT(DISTINCT substr(snapshot_time_utc,1,10)) FROM snapshots") or 0)

    books = rows(con, """
        SELECT bookmaker_key,
               COUNT(*) AS odds_rows,
               COUNT(DISTINCT game_id) AS games,
               ROUND(100.0 * COUNT(DISTINCT game_id) / NULLIF((SELECT COUNT(*) FROM games),0), 1) AS game_coverage_pct,
               SUM(home_spread IS NOT NULL) AS spread_rows,
               SUM(total IS NOT NULL) AS total_rows,
               SUM(home_moneyline IS NOT NULL) AS moneyline_rows
        FROM odds
        GROUP BY bookmaker_key
        ORDER BY bookmaker_key
    """)

    seasons = rows(con, """
        SELECT substr(game_date_utc,1,4) AS season,
               COUNT(DISTINCT game_id) AS games,
               COUNT(DISTINCT snapshot_id) AS snapshots,
               COUNT(*) AS odds_rows
        FROM games JOIN odds USING(game_id)
        GROUP BY substr(game_date_utc,1,4)
        ORDER BY season
    """)

    market_coverage = {
        "spreads": int(scalar(con, "SELECT COUNT(*) FROM odds WHERE home_spread IS NOT NULL") or 0),
        "totals": int(scalar(con, "SELECT COUNT(*) FROM odds WHERE total IS NOT NULL") or 0),
        "moneylines": int(scalar(con, "SELECT COUNT(*) FROM odds WHERE home_moneyline IS NOT NULL") or 0),
    }

    recent_games = rows(con, """
        SELECT g.game_id, g.game_date_utc, g.commence_time_utc, g.away_team, g.home_team,
               g.completed, g.away_score, g.home_score,
               COUNT(DISTINCT o.snapshot_id) AS snapshots,
               COUNT(DISTINCT o.bookmaker_key) AS books,
               MAX(s.snapshot_time_utc) AS latest_snapshot_utc
        FROM games g
        LEFT JOIN odds o ON o.game_id=g.game_id
        LEFT JOIN snapshots s ON s.snapshot_id=o.snapshot_id
        GROUP BY g.game_id
        ORDER BY g.commence_time_utc DESC
        LIMIT 25
    """)

    line_movement = rows(con, """
        WITH ranked AS (
          SELECT g.game_id, g.game_date_utc, g.away_team, g.home_team,
                 o.bookmaker_key, o.home_spread, o.total, s.snapshot_time_utc,
                 ROW_NUMBER() OVER (PARTITION BY g.game_id,o.bookmaker_key ORDER BY s.snapshot_time_utc ASC) AS first_rank,
                 ROW_NUMBER() OVER (PARTITION BY g.game_id,o.bookmaker_key ORDER BY s.snapshot_time_utc DESC) AS last_rank
          FROM odds o
          JOIN games g ON g.game_id=o.game_id
          JOIN snapshots s ON s.snapshot_id=o.snapshot_id
          WHERE s.snapshot_time_utc <= g.commence_time_utc
        ), paired AS (
          SELECT f.game_id, f.game_date_utc, f.away_team, f.home_team, f.bookmaker_key,
                 f.home_spread AS opening_spread, l.home_spread AS closing_spread,
                 f.total AS opening_total, l.total AS closing_total,
                 f.snapshot_time_utc AS opening_snapshot_utc,
                 l.snapshot_time_utc AS closing_snapshot_utc
          FROM ranked f
          JOIN ranked l ON l.game_id=f.game_id AND l.bookmaker_key=f.bookmaker_key
          WHERE f.first_rank=1 AND l.last_rank=1
        )
        SELECT *,
               CASE WHEN opening_spread IS NOT NULL AND closing_spread IS NOT NULL THEN ROUND(closing_spread-opening_spread,1) END AS spread_move,
               CASE WHEN opening_total IS NOT NULL AND closing_total IS NOT NULL THEN ROUND(closing_total-opening_total,1) END AS total_move
        FROM paired
        ORDER BY game_date_utc DESC, game_id, bookmaker_key
        LIMIT 100
    """)

    first_snapshot = scalar(con, "SELECT MIN(snapshot_time_utc) FROM snapshots")
    last_snapshot = scalar(con, "SELECT MAX(snapshot_time_utc) FROM snapshots")
    first_game_date = scalar(con, "SELECT MIN(game_date_utc) FROM games")
    last_game_date = scalar(con, "SELECT MAX(game_date_utc) FROM games")
    requests_used = scalar(con, "SELECT MAX(api_requests_used) FROM snapshots")
    requests_remaining = scalar(con, "SELECT api_requests_remaining FROM snapshots ORDER BY snapshot_time_utc DESC LIMIT 1")

    results = load_json(RESULTS_OUT)
    result_summary = results.get("summary", {})
    graded_games = int(result_summary.get("games_with_results", completed_games) or 0)
    result_coverage_pct = round(100.0 * graded_games / games, 2) if games else 0.0

    plan = load_json(PLAN_OUT)
    planned_dates = plan.get("planned_dates") or plan.get("batch_dates") or []
    if not planned_dates and isinstance(plan.get("requests"), list):
        planned_dates = [r.get("date") or r.get("snapshot_date") for r in plan["requests"]]
        planned_dates = [d for d in planned_dates if d]

    book_keys = {str(book.get("bookmaker_key")) for book in books}
    warehouse_status = {
        "games_collected": games,
        "games_graded": graded_games,
        "games_without_results": max(games - graded_games, 0),
        "result_coverage_pct": result_coverage_pct,
        "collected_snapshot_days": collected_snapshot_days,
        "first_game_date": first_game_date,
        "last_game_date": last_game_date,
        "sample_milestone": sample_milestone(graded_games),
        "next_batch": {
            "requests": int(plan.get("batch_requests", len(planned_dates)) or 0),
            "start": planned_dates[0] if planned_dates else None,
            "end": planned_dates[-1] if planned_dates else None,
            "dates": planned_dates,
            "estimated_credits": plan.get("estimated_credits"),
        },
        "health_checks": {
            "database_integrity": integrity == "ok",
            "has_both_books": "draftkings" in book_keys and "fanduel" in book_keys,
            "has_results": graded_games > 0,
            "result_coverage_at_least_80_pct": result_coverage_pct >= 80.0,
            "result_coverage_at_least_95_pct": result_coverage_pct >= 95.0,
            "research_sample_at_least_100": graded_games >= 100,
            "season_scale_sample_at_least_200": graded_games >= 200,
        },
        "readiness_rule": "Judge readiness by graded games and result coverage, not warehouse game count alone.",
    }

    payload = {
        "generated_at_utc": utc_now(),
        "status": "ok" if integrity == "ok" else "error",
        "database": str(db_path),
        "integrity": integrity,
        "summary": {
            "games": games,
            "games_with_results": graded_games,
            "games_without_results": max(games - graded_games, 0),
            "result_coverage_pct": result_coverage_pct,
            "snapshots": snapshots,
            "collected_snapshot_days": collected_snapshot_days,
            "odds_rows": odds_rows,
            "first_snapshot_utc": first_snapshot,
            "last_snapshot_utc": last_snapshot,
            "first_game_date": first_game_date,
            "last_game_date": last_game_date,
            "api_requests_used_account": requests_used,
            "api_requests_remaining": requests_remaining,
            "bookmakers": len(books),
            "seasons": len(seasons),
        },
        "warehouse_status": warehouse_status,
        "bookmaker_coverage": books,
        "market_coverage": market_coverage,
        "seasons": seasons,
        "recent_games": recent_games,
        "line_movement": line_movement,
        "notes": {
            "scope": "DraftKings and FanDuel only",
            "markets": ["h2h", "spreads", "totals"],
            "closing_definition": "Latest stored snapshot at or before commence time",
            "movement_ready": snapshots > 1,
            "minimum_graded_games_for_basic_testing": 100,
            "preferred_graded_games_for_season_level_research": 200,
            "preferred_result_coverage_pct": 95,
        },
    }
    con.close()
    for path in (OUT, WAREHOUSE_OUT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(payload["warehouse_status"], indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    args = parser.parse_args()
    build(args.db)


if __name__ == "__main__":
    main()
