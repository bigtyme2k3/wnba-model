"""Link opening, bet-time, and closing lines to Sprint 19 edge records."""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

EDGE_HISTORY = "data/history/wnba_edge_database.jsonl"
SNAPSHOTS = "data/history/wnba_line_snapshots.jsonl"
REPORT_PATHS = (
    "data/warehouse/wnba_clv_edge_report.json",
    "data/dashboard/wnba_clv_edge_report.json",
)


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(clean(row), separators=(",", ":"), allow_nan=False) + "\n")


def finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    return value


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def market_key(row: Dict[str, Any]) -> str:
    return "|".join(
        norm(row.get(field))
        for field in ("date", "player", "game", "market", "selection")
    )


def snapshot_key(row: Dict[str, Any], edge: Dict[str, Any]) -> str:
    return "|".join(
        norm(value)
        for value in (
            row.get("date"),
            row.get("player"),
            row.get("game"),
            row.get("stat") or row.get("market"),
            row.get("signal") or edge.get("selection"),
        )
    )


def implied_probability(american_odds: Any) -> Optional[float]:
    odds = finite(american_odds)
    if odds is None or odds == 0:
        return None
    return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)


def selected_price(snapshot: Dict[str, Any], selection: Any) -> Optional[float]:
    side = str(selection or "").upper()
    if side in {"OVER", "YES"}:
        return finite(snapshot.get("over_price"))
    if side in {"UNDER", "NO"}:
        return finite(snapshot.get("under_price"))
    return finite(snapshot.get("price") or snapshot.get("american_odds"))


def directional_line_clv(entry: Any, closing: Any, selection: Any) -> Optional[float]:
    start = finite(entry)
    end = finite(closing)
    if start is None or end is None:
        return None
    side = str(selection or "").upper()
    return end - start if side in {"OVER", "YES"} else start - end


def clv_grade(line_clv: Any, probability_clv: Any) -> str:
    line_value = finite(line_clv) or 0.0
    price_value = finite(probability_clv) or 0.0
    if line_value > 0 or price_value > 0:
        return "POSITIVE"
    if line_value < 0 or price_value < 0:
        return "NEGATIVE"
    return "NEUTRAL"


def choose_snapshots(edge: Dict[str, Any], snapshots: List[Dict[str, Any]]) -> Dict[str, Optional[Dict[str, Any]]]:
    wanted_book = norm(edge.get("sportsbook"))
    same_book = [row for row in snapshots if not wanted_book or norm(row.get("book")) == wanted_book]
    candidates = same_book or snapshots
    ordered = sorted(candidates, key=lambda row: str(row.get("captured_at_utc") or ""))
    entry_candidates = [row for row in ordered if norm(row.get("stage")) in {"open", "bet", "snapshot"}]
    close_candidates = [row for row in ordered if norm(row.get("stage")) in {"close", "closing"}]
    opening = entry_candidates[0] if entry_candidates else (ordered[0] if ordered else None)
    bet_time = None
    if entry_candidates:
        bet_time = next((row for row in entry_candidates if norm(row.get("stage")) == "bet"), entry_candidates[-1])
    closing = close_candidates[-1] if close_candidates else None
    return {"opening": opening, "bet_time": bet_time, "closing": closing}


def build(target: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    edges = read_jsonl(EDGE_HISTORY)
    snapshots = read_jsonl(SNAPSHOTS)

    snapshot_index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in snapshots:
        pseudo_edge = {
            "date": row.get("date"),
            "player": row.get("player"),
            "game": row.get("game"),
            "market": row.get("stat") or row.get("market"),
            "selection": row.get("signal"),
        }
        snapshot_index[market_key(pseudo_edge)].append(row)

    linked = 0
    closing_available = 0
    changed = 0
    for edge in edges:
        options = snapshot_index.get(market_key(edge), [])
        if not options:
            continue
        selected = choose_snapshots(edge, options)
        opening = selected["opening"]
        bet_time = selected["bet_time"]
        closing = selected["closing"]
        linked += 1
        if closing is not None:
            closing_available += 1

        entry_line = finite(edge.get("sportsbook_line"))
        if entry_line is None and bet_time is not None:
            entry_line = finite(bet_time.get("line"))
        opening_line = finite(opening.get("line")) if opening else None
        closing_line = finite(closing.get("line")) if closing else None

        entry_price = finite(edge.get("american_odds"))
        if entry_price is None and bet_time is not None:
            entry_price = selected_price(bet_time, edge.get("selection"))
        opening_price = selected_price(opening, edge.get("selection")) if opening else None
        closing_price = selected_price(closing, edge.get("selection")) if closing else None

        line_clv = directional_line_clv(entry_line, closing_line, edge.get("selection"))
        opening_line_move = directional_line_clv(opening_line, entry_line, edge.get("selection"))
        entry_implied = implied_probability(entry_price)
        closing_implied = implied_probability(closing_price)
        probability_clv = (
            closing_implied - entry_implied
            if entry_implied is not None and closing_implied is not None
            else None
        )

        updates = clean({
            "opening_line": opening_line,
            "opening_price": opening_price,
            "bet_time_line": entry_line,
            "bet_time_price": entry_price,
            "closing_line": closing_line,
            "closing_price": closing_price,
            "opening_to_bet_line_move": opening_line_move,
            "line_clv": line_clv,
            "price_clv": probability_clv,
            "clv": line_clv if line_clv is not None else probability_clv,
            "clv_grade": clv_grade(line_clv, probability_clv) if closing is not None else "PENDING",
            "clv_status": "GRADED" if closing is not None else "AWAITING_CLOSE",
            "opening_captured_at_utc": opening.get("captured_at_utc") if opening else None,
            "bet_time_captured_at_utc": bet_time.get("captured_at_utc") if bet_time else None,
            "closing_captured_at_utc": closing.get("captured_at_utc") if closing else None,
            "clv_updated_at_utc": now,
        })
        material_before = {key: edge.get(key) for key in updates if key != "clv_updated_at_utc"}
        material_after = {key: value for key, value in updates.items() if key != "clv_updated_at_utc"}
        if material_before != material_after:
            edge.update(updates)
            changed += 1

    write_jsonl(EDGE_HISTORY, edges)

    graded = [row for row in edges if row.get("clv_status") == "GRADED"]
    target_rows = [row for row in graded if row.get("date") == target]
    positive = [row for row in graded if row.get("clv_grade") == "POSITIVE"]
    negative = [row for row in graded if row.get("clv_grade") == "NEGATIVE"]
    neutral = [row for row in graded if row.get("clv_grade") == "NEUTRAL"]

    def aggregate(field: str) -> Dict[str, Dict[str, Any]]:
        output: Dict[str, Dict[str, Any]] = {}
        for row in graded:
            key = str(row.get(field) or "UNKNOWN")
            bucket = output.setdefault(key, {"records": 0, "positive": 0, "negative": 0, "neutral": 0, "wins": 0, "losses": 0})
            bucket["records"] += 1
            grade = str(row.get("clv_grade") or "").lower()
            if grade in bucket:
                bucket[grade] += 1
            bucket["wins"] += int(row.get("result") == "WIN")
            bucket["losses"] += int(row.get("result") == "LOSS")
        for bucket in output.values():
            bucket["positive_rate"] = bucket["positive"] / bucket["records"] if bucket["records"] else 0.0
            decisions = bucket["wins"] + bucket["losses"]
            bucket["win_rate"] = bucket["wins"] / decisions if decisions else 0.0
        return clean(output)

    report = clean({
        "generated_at_utc": now,
        "target_date": target,
        "edge_records": len(edges),
        "snapshot_records": len(snapshots),
        "linked_records": linked,
        "closing_available": closing_available,
        "updated_records": changed,
        "graded_records": len(graded),
        "target_graded_records": len(target_rows),
        "coverage_rate": len(graded) / len(edges) if edges else 0.0,
        "positive_clv": len(positive),
        "negative_clv": len(negative),
        "neutral_clv": len(neutral),
        "positive_clv_rate": len(positive) / len(graded) if graded else 0.0,
        "average_line_clv": sum(finite(row.get("line_clv")) or 0.0 for row in graded) / len(graded) if graded else 0.0,
        "average_price_clv": sum(finite(row.get("price_clv")) or 0.0 for row in graded) / len(graded) if graded else 0.0,
        "by_market": aggregate("market"),
        "by_sportsbook": aggregate("sportsbook"),
        "top_positive_clv": sorted(positive, key=lambda row: finite(row.get("line_clv")) or finite(row.get("price_clv")) or -999, reverse=True)[:50],
        "largest_negative_clv": sorted(negative, key=lambda row: finite(row.get("line_clv")) or finite(row.get("price_clv")) or 999)[:50],
    })
    for path in REPORT_PATHS:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    report = build(args.date)
    print("CLV edge linker:", {key: report[key] for key in ("edge_records", "linked_records", "graded_records", "updated_records")})


if __name__ == "__main__":
    main()
