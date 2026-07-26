"""Sprint 16 Commit 2: validate discovered CLV trends against graded outcomes.

The engine joins trend-matching historical observations to verified warehouse grades,
calculates flat-stake ROI, hit rate, Wilson confidence intervals, and a chronological
70/30 development/holdout split. Trends remain INSUFFICIENT until enough unique
outcomes are available; CLV strength alone is never presented as profitability.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
TRENDS = Path("data/trends/automated_trends.json")
CLV = Path("data/market/clv_results.json")
TIMELINE = Path("data/market/market_timeline.json")
MOVES = Path("data/market/line_movements.json")
SIGNALS = Path("data/market/movement_classifications.json")
OUT = Path("data/trends/outcome_validated_trends.json")
DETAIL = Path("data/trends/trend_outcome_records.json")
DASH = Path("data/dashboard/wnba_trend_outcome_validation_summary.json")
MIN_GRADED = 30
MIN_HOLDOUT = 10


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8")).get(key, [])
    return value if isinstance(value, list) else []


def bucket_minutes(value: Any) -> str:
    minutes = float(value or 0)
    if minutes >= 1440: return "24H_PLUS"
    if minutes >= 720: return "12_TO_24H"
    if minutes >= 360: return "6_TO_12H"
    if minutes >= 180: return "3_TO_6H"
    if minutes >= 60: return "1_TO_3H"
    return "FINAL_HOUR"


def canonical_key(event_id: str, bookmaker: str, market: str, outcome_key: str) -> str:
    raw = "|".join((event_id, bookmaker, market, outcome_key))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def wilson(wins: int, losses: int, z: float = 1.96) -> list[float | None]:
    n = wins + losses
    if not n:
        return [None, None]
    p = wins / n
    den = 1 + z*z/n
    center = (p + z*z/(2*n)) / den
    margin = z * math.sqrt((p*(1-p) + z*z/(4*n))/n) / den
    return [round(max(0, center-margin), 6), round(min(1, center+margin), 6)]


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(r["grade"] == "win" for r in rows)
    losses = sum(r["grade"] == "loss" for r in rows)
    pushes = sum(r["grade"] == "push" for r in rows)
    decisions = wins + losses
    profit = round(sum(float(r.get("profit_units") or 0) for r in rows), 6)
    return {
        "records": len(rows), "wins": wins, "losses": losses, "pushes": pushes,
        "hit_rate": round(wins / decisions, 6) if decisions else None,
        "roi_per_bet": round(profit / len(rows), 6) if rows else None,
        "profit_units": profit, "hit_rate_95ci": wilson(wins, losses),
    }


def matches(dimensions: dict[str, Any], row: dict[str, Any]) -> bool:
    return all(str(row.get(key, "UNKNOWN")) == str(value) for key, value in dimensions.items())


def connect() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Warehouse missing: {DB}")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Warehouse integrity check failed")
    return con


def graded_lookup(con: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    rows = con.execute("""
      SELECT w.event_id,w.bookmaker_key,w.market_key,w.outcome_key,s.returned_at_utc,
             w.american_price,g.grade,g.profit_units,g.grading_source
      FROM grades g JOIN wagers w ON w.wager_id=g.wager_id
      JOIN snapshots s ON s.snapshot_id=w.snapshot_id
      WHERE g.grade IN ('win','loss','push')
    """).fetchall()
    return {(canonical_key(r["event_id"], r["bookmaker_key"], r["market_key"], r["outcome_key"]), r["returned_at_utc"]): dict(r) for r in rows}


def run() -> dict[str, Any]:
    trends = load(TRENDS, "trends")
    clv = [r for r in load(CLV, "records") if not r.get("is_closing_observation")]
    timeline = {r["market_id"]: r for r in load(TIMELINE, "markets")}
    moves = {r["market_id"]: r for r in load(MOVES, "movements")}
    signals = {r["market_id"]: r for r in load(SIGNALS, "classifications")}
    lookup = graded_lookup(connect())

    joined: list[dict[str, Any]] = []
    for row in clv:
        market_id = row["market_id"]
        grade = lookup.get((market_id, row["captured_at_utc"]))
        if not grade:
            continue
        move, signal = moves.get(market_id, {}), signals.get(market_id, {})
        joined.append({
            **row,
            "grade": grade["grade"], "profit_units": grade["profit_units"],
            "grading_source": grade["grading_source"],
            "window": bucket_minutes(row.get("minutes_to_tip")),
            "movement_direction": move.get("direction", "UNKNOWN"),
            "volatility_band": "HIGH" if float(move.get("volatility_score") or 0) >= 70 else ("MEDIUM" if float(move.get("volatility_score") or 0) >= 35 else "LOW"),
            "signal": signal.get("classification", "NORMAL"),
            "outcome_key": timeline.get(market_id, {}).get("outcome_key"),
        })

    validations, details = [], []
    for index, trend in enumerate(trends):
        dimensions = trend.get("dimensions", {})
        rows = sorted((r for r in joined if matches(dimensions, r)), key=lambda r: (r["commence_time_utc"], r["captured_at_utc"], r["market_id"]))
        # Prevent multiple observations of one market from inflating outcome evidence.
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            unique.setdefault(row["market_id"], row)
        rows = list(unique.values())
        cut = max(1, int(len(rows) * 0.70)) if rows else 0
        development, holdout = rows[:cut], rows[cut:]
        full_m, dev_m, hold_m = metrics(rows), metrics(development), metrics(holdout)
        enough = len(rows) >= MIN_GRADED and len(holdout) >= MIN_HOLDOUT
        profitable = enough and (hold_m["roi_per_bet"] or 0) > 0 and (hold_m["hit_rate_95ci"][0] or 0) > 0.5
        status = "VALIDATED" if profitable else ("REJECTED" if enough else "INSUFFICIENT")
        rec = {
            "trend_id": f"trend_{index+1:04d}", "dimensions": dimensions,
            "clv_grade": trend.get("grade"), "clv_score": trend.get("trend_score"),
            "validation_basis": "VERIFIED_OUTCOMES_CHRONOLOGICAL_HOLDOUT",
            "status": status, "full_sample": full_m, "development_70pct": dev_m,
            "holdout_30pct": hold_m,
            "criteria": {"minimum_graded_markets": MIN_GRADED, "minimum_holdout_markets": MIN_HOLDOUT,
                         "positive_holdout_roi": True, "holdout_hit_rate_ci_low_above_50pct": True},
        }
        validations.append(rec)
        details.extend({"trend_id": rec["trend_id"], **r} for r in rows)

    order = {"VALIDATED": 0, "REJECTED": 1, "INSUFFICIENT": 2}
    validations.sort(key=lambda r: (order[r["status"]], -(r["holdout_30pct"]["roi_per_bet"] or -999), -r["full_sample"]["records"]))
    generated = now()
    OUT.parent.mkdir(parents=True, exist_ok=True); DASH.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated_at_utc": generated, "methodology": "One earliest stored observation per market; verified grades; chronological 70/30 holdout.", "trends": validations}, indent=2), encoding="utf-8")
    DETAIL.write_text(json.dumps({"generated_at_utc": generated, "records": details}, indent=2), encoding="utf-8")
    summary = {
        "generated_at_utc": generated,
        "status": "READY" if trends else "STANDBY",
        "discovered_trends": len(trends), "graded_observations_available": len(joined),
        "unique_graded_markets_used": len({r["market_id"] for r in joined}),
        "validated": sum(r["status"] == "VALIDATED" for r in validations),
        "rejected": sum(r["status"] == "REJECTED" for r in validations),
        "insufficient": sum(r["status"] == "INSUFFICIENT" for r in validations),
        "top_validations": validations[:25],
        "warning": "Outcome validation reduces but does not eliminate overfitting. VALIDATED means the historical holdout passed the stated rules, not guaranteed future profit.",
    }
    DASH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2)); return summary


if __name__ == "__main__":
    run()
