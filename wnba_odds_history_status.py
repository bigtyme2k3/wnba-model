"""Build a compact status report for the WNBA historical odds warehouse."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path("data/warehouse/wnba_odds_history.sqlite")
RESULTS = Path("data/dashboard/wnba_odds_history_results.json")
PLAN = Path("data/warehouse/wnba_odds_history_backfill_plan.json")
OUT = Path("data/dashboard/wnba_odds_history_status.json")
WAREHOUSE_OUT = Path("data/warehouse/wnba_odds_history_status.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def scalar(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = con.execute(sql, params).fetchone()
    return row[0] if row else None


def milestone(games_with_results: int) -> dict[str, Any]:
    levels = [
        (50, "exploration", "Enough to explore broad patterns; do not trust small splits."),
        (100, "initial_testing", "Enough to begin testing simple, pre-defined hypotheses."),
        (200, "season_scale", "Large enough for stronger season-level research and validation."),
    ]
    reached = [item for item in levels if games_with_results >= item[0]]
    next_level = next((item for item in levels if games_with_results < item[0]), None)
    current = reached[-1] if reached else (0, "pipeline_validation", "Pipeline works, but the sample is still small.")
    return {
        "current": {"games": current[0], "name": current[1], "meaning": current[2]},
        "next": None if next_level is None else {
            "games": next_level[0],
            "name": next_level[1],
            "games_needed": next_level[0] - games_with_results,
            "meaning": next_level[2],
        },
        "research_ready": games_with_results >= 100,
        "season_scale_ready": games_with_results >= 200,
    }


def build(db_path: Path = DB) -> dict[str, Any]:
    if not db_path.exists():
        raise SystemExit(f"Warehouse database not found: {db_path}")

    con = sqlite3.connect(db_path)
    integrity = scalar(con, "PRAGMA integrity_check")
    games = int(scalar(con, "SELECT COUNT(*) FROM games") or 0)
    snapshots = int(scalar(con, "SELECT COUNT(*) FROM snapshots") or 0)
    odds_rows = int(scalar(con, "SELECT COUNT(*) FROM odds") or 0)
    completed = int(scalar(con, "SELECT COUNT(*) FROM games WHERE completed=1 AND home_score IS NOT NULL AND away_score IS NOT NULL") or 0)
    collected_days = int(scalar(con, "SELECT COUNT(DISTINCT substr(snapshot_time_utc,1,10)) FROM snapshots") or 0)
    first_game_date = scalar(con, "SELECT MIN(game_date_utc) FROM games")
    last_game_date = scalar(con, "SELECT MAX(game_date_utc) FROM games")

    book_rows = con.execute(
        """SELECT bookmaker_key, COUNT(DISTINCT game_id) AS games
           FROM odds GROUP BY bookmaker_key ORDER BY bookmaker_key"""
    ).fetchall()
    book_coverage = {
        str(book): {
            "games": int(count),
            "coverage_pct": round(100.0 * int(count) / games, 2) if games else 0.0,
        }
        for book, count in book_rows
    }

    results = load_json(RESULTS)
    result_summary = results.get("summary", {})
    games_with_results = int(result_summary.get("games_with_results", completed) or 0)
    result_coverage = round(100.0 * games_with_results / games, 2) if games else 0.0

    plan = load_json(PLAN)
    planned_dates = plan.get("planned_dates") or plan.get("batch_dates") or []
    if not planned_dates and isinstance(plan.get("requests"), list):
        planned_dates = [r.get("date") or r.get("snapshot_date") for r in plan["requests"]]
        planned_dates = [d for d in planned_dates if d]

    next_batch = {
        "requests": int(plan.get("batch_requests", len(planned_dates)) or 0),
        "dates": planned_dates,
        "start": planned_dates[0] if planned_dates else None,
        "end": planned_dates[-1] if planned_dates else None,
        "estimated_credits": plan.get("estimated_credits"),
    }

    health_checks = {
        "database_integrity": integrity == "ok",
        "has_games": games > 0,
        "has_both_books": "draftkings" in book_coverage and "fanduel" in book_coverage,
        "has_results": games_with_results > 0,
        "result_coverage_at_least_80_pct": result_coverage >= 80.0,
        "research_sample_at_least_100": games_with_results >= 100,
    }

    payload = {
        "generated_at_utc": utc_now(),
        "status": "ok" if all((health_checks["database_integrity"], health_checks["has_games"])) else "warning",
        "database": str(db_path),
        "summary": {
            "games": games,
            "games_with_results": games_with_results,
            "games_without_results": max(games - games_with_results, 0),
            "result_coverage_pct": result_coverage,
            "snapshots": snapshots,
            "collected_snapshot_days": collected_days,
            "odds_rows": odds_rows,
            "first_game_date": first_game_date,
            "last_game_date": last_game_date,
        },
        "bookmaker_coverage": book_coverage,
        "sample_milestone": milestone(games_with_results),
        "next_batch": next_batch,
        "health_checks": health_checks,
        "guidance": {
            "minimum_for_basic_testing": 100,
            "preferred_for_season_level_research": 200,
            "preferred_result_coverage_pct": 95,
            "rule": "Judge readiness by graded games and coverage, not warehouse game count alone.",
        },
    }
    con.close()

    for path in (OUT, WAREHOUSE_OUT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")

    print(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    args = parser.parse_args()
    build(args.db)


if __name__ == "__main__":
    main()
