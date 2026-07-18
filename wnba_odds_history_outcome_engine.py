"""Build outcome analytics from completed games and closing sportsbook lines."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("data/warehouse/wnba_odds_history.sqlite")
WAREHOUSE_OUT = Path("data/warehouse/wnba_odds_history_outcomes.json")
DASHBOARD_OUT = Path("data/dashboard/wnba_odds_history_outcomes.json")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def pct(a: int, b: int) -> float | None:
    return round(a * 100 / b, 2) if b else None


def result_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT g.game_id,g.game_date_utc,g.commence_time_utc,g.away_team,g.home_team,
               g.away_score,g.home_score,o.bookmaker_key,o.home_spread,o.total,
               o.home_moneyline,o.away_moneyline
        FROM games g JOIN closing_odds o ON o.game_id=g.game_id
        WHERE g.completed=1 AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
        ORDER BY g.commence_time_utc,g.game_id,o.bookmaker_key
        """
    ).fetchall()
    out = []
    for raw in rows:
        row = dict(raw)
        home_score, away_score = int(row["home_score"]), int(row["away_score"])
        margin, actual_total = home_score - away_score, home_score + away_score
        spread, total = row.get("home_spread"), row.get("total")
        ats_margin = margin + float(spread) if spread is not None else None
        if ats_margin is None:
            ats = "NO_LINE"
        elif abs(ats_margin) < 1e-9:
            ats = "PUSH"
        elif ats_margin > 0:
            ats = "HOME"
        else:
            ats = "AWAY"
        if total is None:
            total_result = "NO_LINE"
        elif abs(actual_total - float(total)) < 1e-9:
            total_result = "PUSH"
        elif actual_total > float(total):
            total_result = "OVER"
        else:
            total_result = "UNDER"
        favorite = "HOME" if spread is not None and float(spread) < 0 else "AWAY" if spread is not None and float(spread) > 0 else "PICK"
        row.update({
            "actual_margin": margin, "actual_total": actual_total,
            "ats_result": ats, "total_result": total_result, "favorite_side": favorite,
            "favorite_covered": ats == favorite if favorite != "PICK" and ats not in {"PUSH", "NO_LINE"} else None,
            "home_won": margin > 0,
        })
        out.append(row)
    return out


def record(rows: list[dict[str, Any]], field: str, values: tuple[str, ...]) -> dict[str, Any]:
    counts = {value.lower(): sum(r.get(field) == value for r in rows) for value in values}
    graded = sum(counts.values()) - counts.get("push", 0)
    counts["graded"] = graded
    for value in values:
        if value != "PUSH":
            counts[f"{value.lower()}_pct"] = pct(counts[value.lower()], graded)
    return counts


def longest_streak(events: list[str], target: str) -> int:
    best = current = 0
    for value in events:
        current = current + 1 if value == target else 0
        best = max(best, current)
    return best


def build(db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    if not db_path.exists():
        raise SystemExit(f"Odds warehouse not found: {db_path}")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = result_rows(con)
    by_book = {}
    for book in ("draftkings", "fanduel"):
        book_rows = [r for r in rows if r["bookmaker_key"] == book]
        favorite_graded = [r for r in book_rows if r.get("favorite_covered") is not None]
        by_book[book] = {
            "games": len(book_rows),
            "ats": record(book_rows, "ats_result", ("HOME", "AWAY", "PUSH")),
            "totals": record(book_rows, "total_result", ("OVER", "UNDER", "PUSH")),
            "favorites": {
                "covers": sum(r["favorite_covered"] is True for r in favorite_graded),
                "losses": sum(r["favorite_covered"] is False for r in favorite_graded),
                "cover_pct": pct(sum(r["favorite_covered"] is True for r in favorite_graded), len(favorite_graded)),
            },
        }

    series: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        series[(row["bookmaker_key"], row["home_team"])].append(row)
        series[(row["bookmaker_key"], row["away_team"])].append(row)
    streaks = []
    for (book, team), games in series.items():
        games.sort(key=lambda x: x["commence_time_utc"])
        ats_events = []
        total_events = []
        for game in games:
            side = "HOME" if game["home_team"] == team else "AWAY"
            ats_events.append("WIN" if game["ats_result"] == side else "LOSS" if game["ats_result"] in {"HOME", "AWAY"} else game["ats_result"])
            total_events.append(game["total_result"])
        streaks.append({
            "bookmaker_key": book, "team": team, "games": len(games),
            "longest_ats_win_streak": longest_streak(ats_events, "WIN"),
            "longest_ats_loss_streak": longest_streak(ats_events, "LOSS"),
            "longest_over_streak": longest_streak(total_events, "OVER"),
            "longest_under_streak": longest_streak(total_events, "UNDER"),
        })
    streaks.sort(key=lambda x: max(x["longest_ats_loss_streak"], x["longest_over_streak"], x["longest_under_streak"]), reverse=True)

    completed_games = con.execute("SELECT COUNT(*) FROM games WHERE completed=1").fetchone()[0]
    total_games = con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    payload = {
        "generated_at_utc": now_utc(), "database": str(db_path),
        "status": "ready" if rows else "waiting_for_results",
        "summary": {
            "warehouse_games": total_games, "completed_games": completed_games,
            "game_book_outcome_rows": len(rows),
            "result_coverage_pct": pct(completed_games, total_games),
        },
        "by_bookmaker": by_book,
        "team_streak_research": streaks,
        "games": rows,
        "limitations": [
            "Results are graded against the latest stored pregame snapshot, not necessarily the true market close.",
            "ROI is not computed until a standardized stake and price-grading policy is selected.",
            "Streak output is descriptive research and does not establish a profitable martingale strategy.",
        ],
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
