"""Validation Week Commit 2: grade preserved live prediction captures.

The ledger contains model-state captures, not executed wagers. This engine attaches the
actual closing market and final game result, then grades supported core markets using
the captured line and price. Unsupported markets remain explicitly ungraded.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
TRACKER = Path("data/validation/live_prediction_tracker.json")
OUT = Path("data/validation/live_prediction_results.json")
DASH = Path("data/dashboard/wnba_live_result_grader_summary.json")
SUPPORTED = {"h2h", "spreads", "totals"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def same_text(a: Any, b: Any) -> bool:
    return str(a or "").strip().casefold() == str(b or "").strip().casefold()


def profit_units(price: Any, grade: str | None) -> float | None:
    p = num(price)
    if grade == "LOSS":
        return -1.0
    if grade == "PUSH":
        return 0.0
    if grade != "WIN" or not p or p == 0:
        return None
    return round(p / 100 if p > 0 else 100 / abs(p), 6)


def grade_core(row: dict[str, Any], home_score: float, away_score: float) -> tuple[str | None, float | None]:
    market = str(row.get("market") or "")
    selection = row.get("selection")
    line = num(row.get("current_line"))
    home = row.get("home_team")
    away = row.get("away_team")

    if market == "h2h":
        if home_score == away_score:
            return "PUSH", home_score
        winner = home if home_score > away_score else away
        return ("WIN" if same_text(selection, winner) else "LOSS"), home_score - away_score

    if market == "spreads" and line is not None:
        if same_text(selection, home):
            margin = home_score + line - away_score
        elif same_text(selection, away):
            margin = away_score + line - home_score
        else:
            return None, None
        return ("WIN" if margin > 0 else "LOSS" if margin < 0 else "PUSH"), margin

    if market == "totals" and line is not None:
        total = home_score + away_score
        if same_text(selection, "Over"):
            margin = total - line
        elif same_text(selection, "Under"):
            margin = line - total
        else:
            return None, None
        return ("WIN" if margin > 0 else "LOSS" if margin < 0 else "PUSH"), total

    return None, None


def closing_for(con: sqlite3.Connection, row: dict[str, Any]) -> sqlite3.Row | None:
    query = """
    SELECT point, american_price, bookmaker_last_update_utc, market_last_update_utc
    FROM closing_wagers
    WHERE event_id=? AND lower(bookmaker_key)=lower(?) AND market_key=?
      AND lower(participant)=lower(?) AND lower(selection)=lower(?)
    ORDER BY wager_id DESC LIMIT 1
    """
    return con.execute(query, (
        row.get("event_id"), row.get("bookmaker"), row.get("market"),
        row.get("participant") or "", row.get("selection") or "",
    )).fetchone()


def run() -> dict[str, Any]:
    generated = now()
    payload = load(TRACKER)
    records = payload.get("records", [])
    records = records if isinstance(records, list) else []

    if not DB.exists():
        raise SystemExit(f"Missing Warehouse V2 database: {DB}")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    graded_now = 0
    closing_added = 0
    unsupported = 0
    results: list[dict[str, Any]] = []

    for original in records:
        row = dict(original)
        event = con.execute(
            "SELECT completed,home_score,away_score,updated_at_utc FROM events WHERE event_id=?",
            (row.get("event_id"),),
        ).fetchone()
        close = closing_for(con, row)
        prior_close = row.get("actual_closing_price") is not None or row.get("actual_closing_line") is not None
        if close:
            row["actual_closing_line"] = close["point"]
            row["actual_closing_price"] = close["american_price"]
            row["closing_market_update_utc"] = close["market_last_update_utc"] or close["bookmaker_last_update_utc"]
            if not prior_close:
                closing_added += 1

        projected = num(row.get("projected_closing_line"))
        actual_close = num(row.get("actual_closing_line"))
        row["closing_line_absolute_error"] = (
            round(abs(projected - actual_close), 6)
            if projected is not None and actual_close is not None else None
        )

        finished = bool(event and (event["completed"] or (event["home_score"] is not None and event["away_score"] is not None)))
        if finished:
            home_score = float(event["home_score"])
            away_score = float(event["away_score"])
            row["final_home_score"] = home_score
            row["final_away_score"] = away_score
            if row.get("market") in SUPPORTED:
                old_grade = row.get("grade")
                grade, actual = grade_core(row, home_score, away_score)
                row["grade"] = grade
                row["actual_result"] = actual
                row["profit_units"] = profit_units(row.get("current_price"), grade)
                row["validation_status"] = "GRADED" if grade else "UNRESOLVED"
                row["graded_at_utc"] = generated if grade else None
                row["grading_source"] = "Warehouse V2 verified final score"
                if grade and not old_grade:
                    graded_now += 1
            else:
                row["validation_status"] = "UNSUPPORTED"
                row["grading_source"] = "Outcome grading not available for this market type"
                unsupported += 1
        elif close:
            row["validation_status"] = "CLOSING_CAPTURED"
        else:
            row["validation_status"] = "OPEN"
        results.append(row)

    con.close()
    results.sort(key=lambda x: (str(x.get("captured_at_utc")), str(x.get("market_id"))))

    counts = {k: sum(x.get("validation_status") == k for x in results) for k in [
        "OPEN", "CLOSING_CAPTURED", "GRADED", "UNSUPPORTED", "UNRESOLVED"
    ]}
    grades = {k: sum(x.get("grade") == k for x in results) for k in ["WIN", "LOSS", "PUSH"]}
    decided = grades["WIN"] + grades["LOSS"]
    profit = round(sum(float(x.get("profit_units") or 0) for x in results if x.get("grade")), 6)

    output = {
        "generated_at_utc": generated,
        "methodology": "Grades preserved model-state captures against Warehouse V2 closing markets and verified final scores; records are not executed wagers.",
        "records": results,
    }
    summary = {
        "generated_at_utc": generated,
        "status": "READY" if results else "STANDBY",
        "records_total": len(results),
        "closing_markets_added": closing_added,
        "records_graded_now": graded_now,
        "validation_status_counts": counts,
        "grade_counts": grades,
        "decided_hit_rate": round(grades["WIN"] / decided, 6) if decided else None,
        "research_profit_units": profit,
        "events_graded": len({x.get("event_id") for x in results if x.get("grade")}),
        "unsupported_records": unsupported,
        "recent_graded": [x for x in reversed(results) if x.get("grade")][:25],
        "warning": "Performance is simulated from captured model states and does not represent executed bets or realized profit.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    DASH.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    DASH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
