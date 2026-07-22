"""Grade warehouse v2 wagers and export line-movement intelligence.

Results JSON accepted shapes:
1) {"games": [{"event_id":..., "home_score":..., "away_score":...}]}
2) [{"id":..., "home_score":..., "away_score":...}]

Game h2h/spreads/totals are graded automatically. Player and quarter markets remain
ungraded until verified stat/period results are supplied; they are never inferred.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wnba_odds_warehouse_v2 import DEFAULT_DB, connect

DEFAULT_RESULTS = Path("data/warehouse/wnba_results.json")
OUTPUT = Path("data/warehouse/wnba_odds_warehouse_v2_intelligence.json")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_games(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ("games", "data", "results"):
            if isinstance(raw.get(key), list):
                return [x for x in raw[key] if isinstance(x, dict)]
    return []


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def result_id(game: dict[str, Any]) -> str | None:
    value = game.get("event_id") or game.get("id") or game.get("game_id")
    return str(value) if value else None


def profit(price: int | None, grade: str) -> float:
    if grade == "push":
        return 0.0
    if grade != "win" or not price:
        return -1.0
    return round(price / 100 if price > 0 else 100 / abs(price), 6)


def grade_game_wager(row: sqlite3.Row, home: str, away: str,
                     home_score: float, away_score: float) -> tuple[str, float, str] | None:
    market = row["market_key"]
    selection = row["selection"]
    point = number(row["point"])
    if market == "h2h":
        if home_score == away_score:
            return "push", 0.0, "final winner"
        winner = home if home_score > away_score else away
        grade = "win" if selection == winner else "loss"
        return grade, home_score if selection == home else away_score, "final winner"
    if market == "spreads" and point is not None:
        selected_score = home_score if selection == home else away_score if selection == away else None
        opponent_score = away_score if selection == home else home_score if selection == away else None
        if selected_score is None or opponent_score is None:
            return None
        adjusted = selected_score + point
        grade = "win" if adjusted > opponent_score else "loss" if adjusted < opponent_score else "push"
        return grade, selected_score - opponent_score, "final margin"
    if market == "totals" and point is not None:
        total = home_score + away_score
        if selection.lower() == "over":
            grade = "win" if total > point else "loss" if total < point else "push"
        elif selection.lower() == "under":
            grade = "win" if total < point else "loss" if total > point else "push"
        else:
            return None
        return grade, total, "final total"
    return None


def import_results(con: sqlite3.Connection, games: list[dict[str, Any]], source: str) -> dict[str, int]:
    counts = {"games_matched": 0, "wagers_graded": 0}
    for game in games:
        event_id = result_id(game)
        hs = number(game.get("home_score") or game.get("home_points"))
        aws = number(game.get("away_score") or game.get("away_points"))
        if not event_id or hs is None or aws is None:
            continue
        event = con.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        if event is None:
            continue
        counts["games_matched"] += 1
        con.execute("UPDATE events SET completed=1,home_score=?,away_score=?,updated_at_utc=? WHERE event_id=?",
                    (hs, aws, now(), event_id))
        rows = con.execute("SELECT * FROM wagers WHERE event_id=?", (event_id,)).fetchall()
        for row in rows:
            graded = grade_game_wager(row, event["home_team"], event["away_team"], hs, aws)
            if graded is None:
                continue
            grade, actual, notes = graded
            con.execute("""INSERT INTO grades
              (wager_id,actual_result,grade,profit_units,graded_at_utc,grading_source,notes)
              VALUES (?,?,?,?,?,?,?) ON CONFLICT(wager_id) DO UPDATE SET
              actual_result=excluded.actual_result,grade=excluded.grade,
              profit_units=excluded.profit_units,graded_at_utc=excluded.graded_at_utc,
              grading_source=excluded.grading_source,notes=excluded.notes""",
              (row["wager_id"], actual, grade, profit(row["american_price"], grade),
               now(), source, notes))
            counts["wagers_graded"] += 1
    con.commit()
    return counts


def movement(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute("""SELECT w.event_id,w.bookmaker_key,w.market_key,w.outcome_key,
      w.participant,w.selection,w.point,w.american_price,s.returned_at_utc,e.commence_time_utc
      FROM wagers w JOIN snapshots s ON s.snapshot_id=w.snapshot_id
      JOIN events e ON e.event_id=w.event_id
      WHERE s.returned_at_utc<=e.commence_time_utc
      ORDER BY w.event_id,w.bookmaker_key,w.market_key,w.outcome_key,s.returned_at_utc""").fetchall()
    groups: dict[tuple[str, str, str, str], list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault((row["event_id"], row["bookmaker_key"], row["market_key"], row["outcome_key"]), []).append(row)
    output = []
    for key, values in groups.items():
        opening, closing = values[0], values[-1]
        open_point, close_point = number(opening["point"]), number(closing["point"])
        output.append({
            "event_id": key[0], "bookmaker": key[1], "market": key[2],
            "participant": opening["participant"], "selection": opening["selection"],
            "snapshots": len(values), "opening_time": opening["returned_at_utc"],
            "closing_time": closing["returned_at_utc"], "opening_line": open_point,
            "closing_line": close_point, "line_move": None if open_point is None or close_point is None else round(close_point-open_point, 4),
            "opening_price": opening["american_price"], "closing_price": closing["american_price"],
            "price_move": None if opening["american_price"] is None or closing["american_price"] is None else closing["american_price"]-opening["american_price"],
        })
    return output


def intelligence(con: sqlite3.Connection) -> dict[str, Any]:
    records = movement(con)
    performance = [dict(r) for r in con.execute("""SELECT w.bookmaker_key AS bookmaker,
      w.market_key AS market,COUNT(*) AS bets,
      SUM(CASE WHEN g.grade='win' THEN 1 ELSE 0 END) AS wins,
      SUM(CASE WHEN g.grade='loss' THEN 1 ELSE 0 END) AS losses,
      SUM(CASE WHEN g.grade='push' THEN 1 ELSE 0 END) AS pushes,
      ROUND(SUM(g.profit_units),6) AS profit_units,
      ROUND(SUM(g.profit_units)/COUNT(*),6) AS roi_per_bet
      FROM grades g JOIN wagers w ON w.wager_id=g.wager_id
      WHERE g.grade IS NOT NULL GROUP BY w.bookmaker_key,w.market_key
      ORDER BY roi_per_bet DESC""").fetchall()]
    payload = {"generated_at_utc": now(), "line_movements": records,
               "performance_by_book_market": performance,
               "movement_records": len(records), "performance_groups": len(performance)}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["grade", "intelligence", "all"])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--source", default="verified_results")
    args = parser.parse_args()
    con = connect(args.db)
    report: dict[str, Any] = {}
    if args.action in {"grade", "all"}:
        report["grading"] = import_results(con, load_games(args.results), args.source)
    if args.action in {"intelligence", "all"}:
        report["intelligence"] = intelligence(con)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
