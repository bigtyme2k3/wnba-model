"""Build market-only trend intelligence from the WNBA odds-history warehouse.

This engine intentionally does not claim ATS or over/under performance until final
scores are attached to the warehouse. It analyzes information already present in
SQLite: sportsbook disagreement, snapshot movement, opener/closer availability,
and market coverage.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("data/warehouse/wnba_odds_history.sqlite")
WAREHOUSE_OUT = Path("data/warehouse/wnba_odds_history_trends.json")
DASHBOARD_OUT = Path("data/dashboard/wnba_odds_history_trends.json")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def round_or_none(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?", (name,)
    ).fetchone() is not None


def movement_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        WITH ranked AS (
          SELECT
            g.game_id, g.game_date_utc, g.commence_time_utc, g.away_team, g.home_team,
            o.bookmaker_key, s.snapshot_time_utc,
            o.home_spread, o.total, o.home_moneyline, o.away_moneyline,
            ROW_NUMBER() OVER (
              PARTITION BY g.game_id,o.bookmaker_key ORDER BY s.snapshot_time_utc ASC
            ) AS first_rank,
            ROW_NUMBER() OVER (
              PARTITION BY g.game_id,o.bookmaker_key ORDER BY s.snapshot_time_utc DESC
            ) AS last_rank,
            COUNT(*) OVER (PARTITION BY g.game_id,o.bookmaker_key) AS snapshot_count
          FROM odds o
          JOIN games g ON g.game_id=o.game_id
          JOIN snapshots s ON s.snapshot_id=o.snapshot_id
          WHERE s.snapshot_time_utc <= g.commence_time_utc
        ), paired AS (
          SELECT
            game_id, game_date_utc, commence_time_utc, away_team, home_team, bookmaker_key,
            MAX(snapshot_count) AS snapshot_count,
            MAX(CASE WHEN first_rank=1 THEN snapshot_time_utc END) AS open_snapshot_utc,
            MAX(CASE WHEN last_rank=1 THEN snapshot_time_utc END) AS close_snapshot_utc,
            MAX(CASE WHEN first_rank=1 THEN home_spread END) AS open_home_spread,
            MAX(CASE WHEN last_rank=1 THEN home_spread END) AS close_home_spread,
            MAX(CASE WHEN first_rank=1 THEN total END) AS open_total,
            MAX(CASE WHEN last_rank=1 THEN total END) AS close_total,
            MAX(CASE WHEN first_rank=1 THEN home_moneyline END) AS open_home_moneyline,
            MAX(CASE WHEN last_rank=1 THEN home_moneyline END) AS close_home_moneyline,
            MAX(CASE WHEN first_rank=1 THEN away_moneyline END) AS open_away_moneyline,
            MAX(CASE WHEN last_rank=1 THEN away_moneyline END) AS close_away_moneyline
          FROM ranked
          GROUP BY game_id,game_date_utc,commence_time_utc,away_team,home_team,bookmaker_key
        )
        SELECT * FROM paired
        ORDER BY game_date_utc,commence_time_utc,game_id,bookmaker_key
        """
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for field in (
            "open_home_spread", "close_home_spread", "open_total", "close_total",
            "open_home_moneyline", "close_home_moneyline", "open_away_moneyline",
            "close_away_moneyline",
        ):
            item[field] = round_or_none(item.get(field))
        item["spread_move"] = (
            round(item["close_home_spread"] - item["open_home_spread"], 2)
            if item.get("close_home_spread") is not None and item.get("open_home_spread") is not None
            else None
        )
        item["total_move"] = (
            round(item["close_total"] - item["open_total"], 2)
            if item.get("close_total") is not None and item.get("open_total") is not None
            else None
        )
        item["has_true_movement"] = int(item.get("snapshot_count") or 0) >= 2
        out.append(item)
    return out


def disagreement_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        WITH latest AS (
          SELECT
            g.game_id,g.game_date_utc,g.commence_time_utc,g.away_team,g.home_team,
            o.bookmaker_key,o.home_spread,o.total,o.home_moneyline,o.away_moneyline,
            s.snapshot_time_utc,
            ROW_NUMBER() OVER (
              PARTITION BY g.game_id,o.bookmaker_key ORDER BY s.snapshot_time_utc DESC
            ) AS rn
          FROM odds o
          JOIN games g ON g.game_id=o.game_id
          JOIN snapshots s ON s.snapshot_id=o.snapshot_id
          WHERE s.snapshot_time_utc <= g.commence_time_utc
        )
        SELECT
          game_id,game_date_utc,commence_time_utc,away_team,home_team,
          MAX(CASE WHEN bookmaker_key='draftkings' THEN home_spread END) AS dk_home_spread,
          MAX(CASE WHEN bookmaker_key='fanduel' THEN home_spread END) AS fd_home_spread,
          MAX(CASE WHEN bookmaker_key='draftkings' THEN total END) AS dk_total,
          MAX(CASE WHEN bookmaker_key='fanduel' THEN total END) AS fd_total,
          MAX(CASE WHEN bookmaker_key='draftkings' THEN home_moneyline END) AS dk_home_moneyline,
          MAX(CASE WHEN bookmaker_key='fanduel' THEN home_moneyline END) AS fd_home_moneyline,
          MAX(CASE WHEN bookmaker_key='draftkings' THEN away_moneyline END) AS dk_away_moneyline,
          MAX(CASE WHEN bookmaker_key='fanduel' THEN away_moneyline END) AS fd_away_moneyline
        FROM latest WHERE rn=1
        GROUP BY game_id,game_date_utc,commence_time_utc,away_team,home_team
        ORDER BY game_date_utc,commence_time_utc,game_id
        """
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for field in list(item):
            if field.startswith(("dk_", "fd_")):
                item[field] = round_or_none(item[field])
        item["spread_gap"] = (
            round(item["fd_home_spread"] - item["dk_home_spread"], 2)
            if item.get("fd_home_spread") is not None and item.get("dk_home_spread") is not None
            else None
        )
        item["total_gap"] = (
            round(item["fd_total"] - item["dk_total"], 2)
            if item.get("fd_total") is not None and item.get("dk_total") is not None
            else None
        )
        item["home_ml_gap"] = (
            round(item["fd_home_moneyline"] - item["dk_home_moneyline"], 2)
            if item.get("fd_home_moneyline") is not None and item.get("dk_home_moneyline") is not None
            else None
        )
        item["away_ml_gap"] = (
            round(item["fd_away_moneyline"] - item["dk_away_moneyline"], 2)
            if item.get("fd_away_moneyline") is not None and item.get("dk_away_moneyline") is not None
            else None
        )
        out.append(item)
    return out


def average_abs(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [abs(float(row[field])) for row in rows if row.get(field) is not None]
    return round(sum(values) / len(values), 3) if values else None


def build(db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    if not db_path.exists():
        raise SystemExit(f"Odds warehouse not found: {db_path}")
    con = connect(db_path)
    for required in ("games", "snapshots", "odds"):
        if not table_exists(con, required):
            raise SystemExit(f"Warehouse missing required table: {required}")

    movements = movement_rows(con)
    disagreements = disagreement_rows(con)
    true_movement = [row for row in movements if row["has_true_movement"]]
    large_spread = sorted(
        [row for row in true_movement if row.get("spread_move") is not None],
        key=lambda x: abs(float(x["spread_move"])), reverse=True,
    )[:25]
    large_total = sorted(
        [row for row in true_movement if row.get("total_move") is not None],
        key=lambda x: abs(float(x["total_move"])), reverse=True,
    )[:25]
    book_gaps = sorted(
        disagreements,
        key=lambda x: max(abs(float(x.get("spread_gap") or 0)), abs(float(x.get("total_gap") or 0))),
        reverse=True,
    )[:25]

    games = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    completed = con.execute("SELECT COUNT(*) FROM games WHERE completed=1").fetchone()[0]
    snapshot_count = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    odds_count = con.execute("SELECT COUNT(*) FROM odds").fetchone()[0]
    payload = {
        "generated_at_utc": now_utc(),
        "database": str(db_path),
        "status": "market_trends_ready" if odds_count else "empty",
        "summary": {
            "games": games,
            "snapshots": snapshot_count,
            "odds_rows": odds_count,
            "games_with_results": completed,
            "games_without_results": games - completed,
            "book_comparison_games": len(disagreements),
            "game_book_series": len(movements),
            "series_with_multiple_snapshots": len(true_movement),
            "avg_abs_spread_book_gap": average_abs(disagreements, "spread_gap"),
            "avg_abs_total_book_gap": average_abs(disagreements, "total_gap"),
            "avg_abs_spread_move": average_abs(true_movement, "spread_move"),
            "avg_abs_total_move": average_abs(true_movement, "total_move"),
        },
        "market_disagreement": {
            "largest_current_gaps": book_gaps,
            "all_games": disagreements,
        },
        "line_movement": {
            "largest_spread_moves": large_spread,
            "largest_total_moves": large_total,
            "all_game_book_series": movements,
        },
        "outcome_analytics": {
            "status": "waiting_for_final_scores" if completed == 0 else "partial_results_available",
            "enabled_metrics": [] if completed == 0 else ["ats", "totals", "moneyline"],
            "note": "ATS, over/under, ROI and martingale tests are not produced until final scores are attached.",
        },
        "definitions": {
            "spread_gap": "FanDuel home spread minus DraftKings home spread at the latest pregame snapshot.",
            "total_gap": "FanDuel total minus DraftKings total at the latest pregame snapshot.",
            "spread_move": "Latest pregame home spread minus earliest stored pregame home spread for one sportsbook.",
            "total_move": "Latest pregame total minus earliest stored pregame total for one sportsbook.",
        },
    }
    for path in (WAREHOUSE_OUT, DASHBOARD_OUT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    build(args.db)


if __name__ == "__main__":
    main()
