"""Build the canonical Sprint 19 betting-edge database.

The database is a durable, deduplicated record of every archived model decision.
It combines model projections, market prices, expected value, grading, and CLV
fields without placing bets.

Outputs:
- data/history/wnba_edge_database.jsonl
- data/warehouse/wnba_edge_database.json
- data/dashboard/wnba_edge_database.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

MODEL_HISTORY = "data/history/wnba_model_history.jsonl"
EDGE_HISTORY = "data/history/wnba_edge_database.jsonl"


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
    return rows


def finite_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def probability(value: Any) -> Optional[float]:
    number = finite_float(value)
    if number is None:
        return None
    if number > 1:
        number /= 100.0
    return min(1.0, max(0.0, number))


def implied_probability(american_odds: Any) -> Optional[float]:
    odds = finite_float(american_odds)
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def expected_value(model_probability: Any, american_odds: Any) -> Optional[float]:
    p = probability(model_probability)
    odds = finite_float(american_odds)
    if p is None or odds is None or odds == 0:
        return None
    profit_per_dollar = odds / 100.0 if odds > 0 else 100.0 / abs(odds)
    return p * profit_per_dollar - (1.0 - p)


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    return value


def edge_key(row: Dict[str, Any]) -> str:
    return str(
        row.get("history_key")
        or "|".join(
            str(row.get(field) or "")
            for field in ("date", "player", "game", "stat", "line", "signal")
        )
    )


def model_probability_for(row: Dict[str, Any]) -> Optional[float]:
    for field in (
        "simulation_probability",
        "model_probability",
        "probability",
        "confidence",
        "final_score",
        "consensus_score",
    ):
        result = probability(row.get(field))
        if result is not None:
            return result
    return None


def normalized_record(row: Dict[str, Any], now: str) -> Dict[str, Any]:
    odds = finite_float(row.get("american_odds"))
    model_prob = model_probability_for(row)
    implied_prob = implied_probability(odds)
    calculated_ev = expected_value(model_prob, odds)
    supplied_ev = finite_float(row.get("ev_pct", row.get("raw_ev_pct")))
    if supplied_ev is not None and abs(supplied_ev) > 1:
        supplied_ev /= 100.0
    ev = calculated_ev if calculated_ev is not None else supplied_ev

    projection = finite_float(row.get("pred", row.get("projection")))
    market_line = finite_float(row.get("line"))
    projection_edge = finite_float(row.get("edge"))
    if projection_edge is None and projection is not None and market_line is not None:
        projection_edge = projection - market_line

    stake = finite_float(row.get("stake", row.get("recommended_stake")))
    profit_loss = finite_float(row.get("profit_loss", row.get("profit")))
    roi = None
    if stake and profit_loss is not None:
        roi = profit_loss / stake

    closing_line = finite_float(row.get("closing_line"))
    clv = finite_float(row.get("clv"))
    if clv is None and closing_line is not None and market_line is not None:
        signal = str(row.get("signal") or "").upper()
        clv = closing_line - market_line if signal in {"OVER", "YES"} else market_line - closing_line

    return clean(
        {
            "edge_key": edge_key(row),
            "date": row.get("date"),
            "captured_at_utc": row.get("captured_at_utc") or now,
            "updated_at_utc": now,
            "player": row.get("player"),
            "team": row.get("team"),
            "game": row.get("game"),
            "market": row.get("stat", row.get("market")),
            "selection": row.get("signal", row.get("selection")),
            "model_projection": projection,
            "sportsbook_line": market_line,
            "projection_edge": projection_edge,
            "projection_edge_pct": finite_float(row.get("edge_pct")),
            "american_odds": odds,
            "sportsbook": row.get("sportsbook") or row.get("book"),
            "book_count": row.get("book_count"),
            "implied_probability": implied_prob,
            "model_probability": model_prob,
            "probability_edge": (model_prob - implied_prob) if model_prob is not None and implied_prob is not None else None,
            "expected_value": ev,
            "expected_value_pct": ev * 100.0 if ev is not None else None,
            "confidence": probability(row.get("confidence", row.get("final_score"))),
            "consensus_score": finite_float(row.get("consensus_score")),
            "engine_agreement": row.get("engine_agreement"),
            "recommendation": row.get("final_action") or row.get("recommendation"),
            "eligible_for_bet": bool(row.get("eligible_for_bet", False)),
            "stake": stake,
            "status": "SETTLED" if row.get("outcome") in {"WIN", "LOSS", "PUSH", "VOID"} else "OPEN",
            "result": row.get("outcome") or row.get("result"),
            "actual": finite_float(row.get("actual")),
            "profit_loss": profit_loss,
            "roi": roi,
            "closing_line": closing_line,
            "clv": clv,
            "decision_reason": row.get("decision_reason"),
            "guardrail_failures": row.get("guardrail_failures", []),
            "source_history_key": row.get("history_key"),
        }
    )


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(clean(row), separators=(",", ":"), allow_nan=False) + "\n")


def build(target: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    existing = {edge_key(row): row for row in load_jsonl(EDGE_HISTORY)}
    source_rows = load_jsonl(MODEL_HISTORY)

    inserted = 0
    updated = 0
    for source in source_rows:
        key = edge_key(source)
        record = normalized_record(source, now)
        prior = existing.get(key)
        if prior is None:
            existing[key] = record
            inserted += 1
        elif prior != record:
            existing[key] = {**prior, **record, "captured_at_utc": prior.get("captured_at_utc") or record.get("captured_at_utc")}
            updated += 1

    rows = sorted(existing.values(), key=lambda row: (str(row.get("date") or ""), str(row.get("edge_key") or "")))
    write_jsonl(EDGE_HISTORY, rows)

    target_rows = [row for row in rows if row.get("date") == target]
    settled = [row for row in rows if row.get("status") == "SETTLED"]
    decisions = [row for row in settled if row.get("result") in {"WIN", "LOSS"}]
    wins = sum(row.get("result") == "WIN" for row in decisions)
    total_stake = sum(finite_float(row.get("stake")) or 0.0 for row in decisions)
    total_profit = sum(finite_float(row.get("profit_loss")) or 0.0 for row in settled)
    ev_rows = [row for row in rows if finite_float(row.get("expected_value")) is not None]

    by_market: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        market = str(row.get("market") or "UNKNOWN")
        bucket = by_market.setdefault(market, {"records": 0, "settled": 0, "wins": 0, "losses": 0, "profit_loss": 0.0})
        bucket["records"] += 1
        if row.get("status") == "SETTLED":
            bucket["settled"] += 1
            bucket["wins"] += int(row.get("result") == "WIN")
            bucket["losses"] += int(row.get("result") == "LOSS")
            bucket["profit_loss"] += finite_float(row.get("profit_loss")) or 0.0
    for bucket in by_market.values():
        graded = bucket["wins"] + bucket["losses"]
        bucket["win_rate"] = round(bucket["wins"] / graded, 4) if graded else 0.0
        bucket["profit_loss"] = round(bucket["profit_loss"], 2)

    report = clean(
        {
            "generated_at_utc": now,
            "target_date": target,
            "source": MODEL_HISTORY,
            "database": EDGE_HISTORY,
            "inserted_records": inserted,
            "updated_records": updated,
            "total_records": len(rows),
            "target_records": len(target_rows),
            "open_records": sum(row.get("status") == "OPEN" for row in rows),
            "settled_records": len(settled),
            "graded_decisions": len(decisions),
            "win_rate": wins / len(decisions) if decisions else 0.0,
            "total_stake": total_stake,
            "profit_loss": total_profit,
            "roi": total_profit / total_stake if total_stake else 0.0,
            "average_expected_value": sum(row["expected_value"] for row in ev_rows) / len(ev_rows) if ev_rows else 0.0,
            "by_market": by_market,
            "top_edges": sorted(
                target_rows,
                key=lambda row: finite_float(row.get("expected_value")) or -999.0,
                reverse=True,
            )[:50],
            "recent_records": rows[-100:],
        }
    )

    for path in ("data/warehouse/wnba_edge_database.json", "data/dashboard/wnba_edge_database.json"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    report = build(args.date)
    print(
        "Edge database:",
        {
            "total_records": report["total_records"],
            "inserted_records": report["inserted_records"],
            "updated_records": report["updated_records"],
            "target_records": report["target_records"],
        },
    )


if __name__ == "__main__":
    main()
