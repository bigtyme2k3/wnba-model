from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wnba_projection_contract import (
    canonical_stat,
    projection_evidence,
    projection_field_violations,
)

DB = Path("data/warehouse/wnba_forward_validation.sqlite")
DASH = Path("data/dashboard")
WARE = Path("data/warehouse")
OUTS = [DASH / "wnba_forward_validation.json", WARE / "wnba_forward_validation.json"]
SOURCES = [
    ("daily_edge", DASH / "wnba_daily_edges.json", "top_edges"),
    ("ensemble", DASH / "wnba_ensemble_intelligence.json", "ranked_edges"),
    ("simulation", DASH / "wnba_monte_carlo_scenarios.json", "all_simulations"),
]
READY_SOURCE_STATUSES = {"ok", "ready"}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def first_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if row.get(key) not in (None, ""):
            return num(row.get(key))
    return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def key(source: str, row: dict[str, Any]) -> str:
    raw = "|".join(map(str, [
        source,
        row.get("target_date"),
        row.get("game"),
        row.get("player"),
        row.get("market") or row.get("stat"),
        row.get("side") or row.get("model_signal"),
        row.get("line"),
        row.get("sportsbook"),
    ]))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def projection_violations(row: dict[str, Any]) -> list[dict[str, Any]]:
    stat = canonical_stat(row.get("market") or row.get("stat"))
    evidence = projection_evidence(row)
    if evidence is None:
        return [{"field": None, "value": None, "reason": "missing_projection"}]
    if not stat:
        return [{"field": evidence[0], "value": evidence[1], "reason": "missing_stat_for_projection"}]
    return projection_field_violations(row, stat)


def stored_projection_violations(row: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except Exception:
        return [{"field": "payload_json", "value": None, "reason": "invalid_payload_json"}]
    if not isinstance(payload, dict):
        return [{"field": "payload_json", "value": None, "reason": "invalid_payload_shape"}]
    return projection_violations(payload)


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS forward_predictions(
    prediction_id TEXT PRIMARY KEY, source TEXT, target_date TEXT, frozen_at_utc TEXT,
    game TEXT, player TEXT, market TEXT, side TEXT, line REAL, sportsbook TEXT, odds REAL,
    edge_score REAL, ensemble_score REAL, model_probability REAL, simulation_probability REAL,
    payload_json TEXT, result TEXT, actual_value REAL, graded_at_utc TEXT, profit_units REAL,
    chronology_valid INTEGER DEFAULT 1, UNIQUE(source,target_date,game,player,market,side,line,sportsbook))""")
    conn.commit()


def freeze(target_date: str) -> dict[str, Any]:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    ensure(conn)
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    existing = 0
    rejected: list[dict[str, Any]] = []
    by_source: dict[str, int] = {}
    for source, path, field in SOURCES:
        data = load(path, {})
        status = str(data.get("status") or "").lower() if isinstance(data, dict) else ""
        source_target = str(data.get("target_date") or "")[:10] if isinstance(data, dict) else ""
        rows = data.get(field, []) if isinstance(data, dict) else []
        count = 0
        if status not in READY_SOURCE_STATUSES or (target_date and source_target != target_date):
            by_source[source] = 0
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            target = str(row.get("target_date") or source_target or target_date)[:10]
            if target_date and target != target_date:
                continue
            violations = projection_violations(row)
            if violations:
                rejected.append({
                    "source": source,
                    "player": row.get("player"),
                    "market": row.get("market") or row.get("stat"),
                    "violations": violations,
                })
                continue
            prediction_id = key(source, {**row, "target_date": target})
            values = (
                prediction_id, source, target, now, row.get("game"), row.get("player"),
                row.get("market") or row.get("stat"), str(row.get("side") or row.get("model_signal") or "").upper(),
                num(row.get("line")), row.get("sportsbook"), num(row.get("odds")), num(row.get("edge_score")),
                num(row.get("ensemble_score")), first_number(row, "calibrated_probability", "adaptive_probability", "model_probability"),
                first_number(row, "simulation_probability", "signal_probability"),
                json.dumps(row, separators=(",", ":"), allow_nan=False),
            )
            cursor = conn.execute("""INSERT OR IGNORE INTO forward_predictions(
                prediction_id,source,target_date,frozen_at_utc,game,player,market,side,line,sportsbook,odds,
                edge_score,ensemble_score,model_probability,simulation_probability,payload_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            if cursor.rowcount:
                inserted += 1
                count += 1
            else:
                existing += 1
        by_source[source] = count
    conn.commit()
    conn.close()
    return {
        "mode": "freeze",
        "target_date": target_date,
        "inserted": inserted,
        "existing": existing,
        "invalid_projection_rows_rejected": len(rejected),
        "invalid_projection_sample": rejected[:20],
        "by_source": by_source,
        "frozen_at_utc": now,
    }


def result_rows() -> list[dict[str, Any]]:
    data = load(DASH / "wnba_results_grading.json", {})
    rows: list[dict[str, Any]] = []
    for field in ("graded_props", "results", "rows", "grades"):
        if isinstance(data.get(field), list):
            rows.extend(row for row in data[field] if isinstance(row, dict))
    return rows


def profit(result: str, odds: float | None) -> float | None:
    if result == "LOSS":
        return -1.0
    if result in {"PUSH", "VOID"}:
        return 0.0
    if result != "WIN":
        return None
    return odds / 100 if odds and odds > 0 else 100 / abs(odds) if odds else 0.9091


def grade(target_date: str) -> dict[str, Any]:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    ensure(conn)
    matched = 0
    for grade_row in result_rows():
        player = norm(grade_row.get("player") or grade_row.get("player_name"))
        market = norm(grade_row.get("market") or grade_row.get("stat") or grade_row.get("prop_type"))
        actual = first_number(grade_row, "actual", "actual_value", "value")
        result = str(grade_row.get("result") or grade_row.get("grade") or "").upper()
        if result not in {"WIN", "LOSS", "PUSH", "VOID"}:
            continue
        query = """SELECT prediction_id,odds FROM forward_predictions
                   WHERE result IS NULL AND lower(trim(player))=? AND lower(trim(market))=?"""
        args: list[Any] = [player, market]
        if target_date:
            query += " AND target_date=?"
            args.append(target_date)
        for row in conn.execute(query, args).fetchall():
            conn.execute(
                "UPDATE forward_predictions SET result=?,actual_value=?,graded_at_utc=?,profit_units=? WHERE prediction_id=?",
                (result, actual, datetime.now(timezone.utc).isoformat(), profit(result, num(row["odds"])), row["prediction_id"]),
            )
            matched += 1
    conn.commit()
    conn.close()
    return {"mode": "grade", "target_date": target_date, "graded_predictions": matched}


def report() -> dict[str, Any]:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    ensure(conn)
    all_rows = [dict(row) for row in conn.execute("SELECT * FROM forward_predictions ORDER BY rowid").fetchall()]
    conn.close()

    rows: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for row in all_rows:
        violations = stored_projection_violations(row)
        if violations:
            quarantined.append({
                "prediction_id": row.get("prediction_id"),
                "source": row.get("source"),
                "target_date": row.get("target_date"),
                "player": row.get("player"),
                "market": row.get("market"),
                "violations": [
                    {"field": item.get("field"), "reason": item.get("reason")}
                    for item in violations
                ],
            })
        else:
            rows.append(row)

    settled = [row for row in rows if row.get("result") in {"WIN", "LOSS", "PUSH", "VOID"}]
    decisions = [row for row in settled if row["result"] in {"WIN", "LOSS"}]
    wins = sum(row["result"] == "WIN" for row in decisions)
    units = sum(float(row.get("profit_units") or 0) for row in settled)
    quarantine_reasons = Counter(
        item.get("reason") or "unknown"
        for row in quarantined
        for item in row.get("violations", [])
    )
    quarantine_sources = Counter(str(row.get("source") or "unknown") for row in quarantined)
    missing_quarantine = sum(
        any(item.get("reason") == "missing_projection" for item in row.get("violations", []))
        for row in quarantined
    )
    by_source: dict[str, dict[str, Any]] = {}
    for source in sorted(set(row["source"] for row in rows)):
        source_decisions = [row for row in decisions if row["source"] == source]
        by_source[source] = {
            "frozen": sum(row["source"] == source for row in rows),
            "graded": len(source_decisions),
            "hit_rate": round(sum(row["result"] == "WIN" for row in source_decisions) / len(source_decisions), 4) if source_decisions else None,
        }

    payload = {
        "sprint": 12,
        "phase": "live-forward-validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "summary": {
            "frozen_predictions": len(rows),
            "quarantined_predictions": len(quarantined),
            "settled_predictions": len(settled),
            "decision_records": len(decisions),
            "wins": wins,
            "losses": len(decisions) - wins,
            "hit_rate": round(wins / len(decisions), 4) if decisions else None,
            "units": round(units, 3),
            "roi": round(units / len(decisions), 4) if decisions else None,
            "chronology_valid": all(row.get("chronology_valid") == 1 for row in rows),
            "all_reported_projections_valid": True,
            "historical_invalid_projections_quarantined": len(quarantined),
            "historical_missing_projections_quarantined": missing_quarantine,
            "historical_implausible_projections_quarantined": len(quarantined) - missing_quarantine,
        },
        "projection_quarantine": {
            "policy": "Invalid historical rows remain immutable in SQLite but are excluded from reporting and calibration evidence.",
            "count": len(quarantined),
            "by_source": dict(quarantine_sources),
            "by_reason": dict(quarantine_reasons),
            "sample": quarantined[:20],
        },
        "by_source": by_source,
        "recent_predictions": rows[-100:],
        "warning": "Only predictions frozen before outcomes are eligible for live-forward validation.",
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(payload, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print(json.dumps(payload["summary"], indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["freeze", "grade", "both", "report"], default="both")
    parser.add_argument("--date", default="")
    args = parser.parse_args()
    output: dict[str, Any] = {}
    if args.mode in {"freeze", "both"}:
        output["freeze"] = freeze(args.date)
    if args.mode in {"grade", "both"}:
        output["grade"] = grade(args.date)
    output["report"] = report()
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
