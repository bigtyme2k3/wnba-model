"""Generate a manual recovery report for pending ALT picks and apply verified overrides.

This is a controlled escape hatch for historical ALT archive rows that automated
box-score recovery cannot resolve. Manual overrides never change frozen pregame
inputs; they only attach a verified actual/result to a still-pending archive row.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
DIAGNOSTICS = Path("data/dashboard/wnba_alt_pending_diagnostics.json")
OVERRIDES = Path("data/manual/wnba_alt_result_overrides.json")
CSV_REPORT = Path("data/dashboard/wnba_alt_pending_manual_recovery.csv")
JSON_REPORT = Path("data/dashboard/wnba_alt_pending_manual_recovery.json")
WAREHOUSE_REPORT = Path("data/warehouse/wnba_alt_pending_manual_recovery.json")

FINAL = {"WIN", "LOSS", "PUSH", "VOID"}


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def derived_outcome(side: Any, actual: Any, line: Any) -> str:
    a = num(actual)
    l = num(line)
    if a is None or l is None:
        return "PENDING"
    if a == l:
        return "PUSH"
    side_u = str(side or "").upper()
    if side_u == "OVER":
        return "WIN" if a > l else "LOSS"
    if side_u == "UNDER":
        return "WIN" if a < l else "LOSS"
    return "VOID"


def one_unit_profit(result: str, odds: Any) -> float | None:
    price = num(odds)
    if result in {"PUSH", "VOID"}:
        return 0.0
    if result == "LOSS":
        return -1.0
    if result == "PENDING" or price in (None, 0):
        return None
    return round(100 / abs(price), 4) if price < 0 else round(price / 100, 4)


def pending_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in history if str(r.get("outcome") or "PENDING").upper() not in FINAL]


def recovery_reason_map() -> dict[str, dict[str, Any]]:
    payload = load_json(DIAGNOSTICS, {"inspector": []})
    out: dict[str, dict[str, Any]] = {}
    for item in payload.get("inspector", []):
        if not isinstance(item, dict):
            continue
        key = "|".join([
            str(item.get("date") or "")[:10], norm(item.get("player")), norm(item.get("stat")),
            norm(item.get("side")), str(item.get("line") if item.get("line") is not None else ""),
        ])
        out[key] = item
    return out


def row_key(row: dict[str, Any]) -> str:
    line = row.get("alt_line") if row.get("alt_line") is not None else row.get("line")
    return "|".join([
        str(row.get("date") or "")[:10], norm(row.get("player")), norm(row.get("stat")),
        norm(row.get("side")), str(line if line is not None else ""),
    ])


def build_report(history: list[dict[str, Any]]) -> dict[str, Any]:
    diag = recovery_reason_map()
    rows = []
    for row in pending_rows(history):
        info = diag.get(row_key(row), {})
        rows.append({
            "candidate_id": row.get("candidate_id"),
            "date": row.get("date"),
            "player": row.get("player"),
            "team": row.get("team"),
            "game": row.get("game") or row.get("opponent"),
            "stat": row.get("stat"),
            "side": row.get("side"),
            "line": row.get("alt_line") if row.get("alt_line") is not None else row.get("line"),
            "sportsbook": row.get("best_book"),
            "odds": row.get("best_odds"),
            "score": row.get("streak_score"),
            "reason": info.get("reason") or row.get("grading_reason") or "Pending manual verification",
            "reason_key": info.get("reason_key") or "unknown",
            "expected_game_id": info.get("expected_game_id"),
            "actual_to_fill": "",
            "verified_source_to_fill": "",
            "notes_to_fill": "",
        })
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pending_rows": len(rows),
        "manual_override_file": str(OVERRIDES),
        "rows": rows,
    }


def write_report(report: dict[str, Any]) -> None:
    JSON_REPORT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    JSON_REPORT.write_text(text, encoding="utf-8")
    WAREHOUSE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    WAREHOUSE_REPORT.write_text(text, encoding="utf-8")
    fields = [
        "candidate_id", "date", "player", "team", "game", "stat", "side", "line", "sportsbook", "odds",
        "score", "reason_key", "reason", "expected_game_id", "actual_to_fill", "verified_source_to_fill", "notes_to_fill",
    ]
    with CSV_REPORT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report["rows"])


def override_matches(row: dict[str, Any], override: dict[str, Any]) -> bool:
    cid = str(override.get("candidate_id") or "").strip()
    if cid:
        return cid == str(row.get("candidate_id") or "")
    checks = {
        "date": str(row.get("date") or "")[:10],
        "player": norm(row.get("player")),
        "stat": norm(row.get("stat")),
        "side": norm(row.get("side")),
        "line": str(row.get("alt_line") if row.get("alt_line") is not None else row.get("line")),
    }
    expected = {
        "date": str(override.get("date") or "")[:10],
        "player": norm(override.get("player")),
        "stat": norm(override.get("stat")),
        "side": norm(override.get("side")),
        "line": str(override.get("line") if override.get("line") is not None else ""),
    }
    return all(expected[k] and expected[k] == checks[k] for k in checks)


def apply_overrides(history: list[dict[str, Any]]) -> dict[str, Any]:
    payload = load_json(OVERRIDES, {"overrides": []})
    overrides = [x for x in payload.get("overrides", []) if isinstance(x, dict)]
    applied = 0
    skipped = []
    now = datetime.now(timezone.utc).isoformat()
    for override in overrides:
        matches = [r for r in history if str(r.get("outcome") or "PENDING").upper() not in FINAL and override_matches(r, override)]
        if len(matches) != 1:
            skipped.append({"candidate_id": override.get("candidate_id"), "match_count": len(matches), "reason": "override must match exactly one pending archive row"})
            continue
        actual = num(override.get("actual"))
        if actual is None:
            skipped.append({"candidate_id": override.get("candidate_id"), "match_count": 1, "reason": "actual is required"})
            continue
        row = matches[0]
        result = str(override.get("outcome") or "").upper() or derived_outcome(row.get("side"), actual, row.get("alt_line"))
        if result not in FINAL:
            skipped.append({"candidate_id": row.get("candidate_id"), "match_count": 1, "reason": f"invalid derived outcome: {result}"})
            continue
        row["actual"] = actual
        row["outcome"] = result
        row["profit_loss"] = one_unit_profit(result, row.get("best_odds"))
        row["graded_at_utc"] = now
        row["actual_source"] = "manual_verified_override"
        row["manual_verified_source"] = override.get("verified_source")
        row["manual_override_note"] = override.get("notes")
        row["grading_reason"] = None
        applied += 1
    if applied:
        write_jsonl(ARCHIVE, history)
    return {"overrides": len(overrides), "applied": applied, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    history = read_jsonl(ARCHIVE)
    if args.apply:
        print("Manual ALT overrides:", apply_overrides(history))
        history = read_jsonl(ARCHIVE)
    if args.report or not args.apply:
        report = build_report(history)
        write_report(report)
        print({"pending_rows": report["pending_rows"], "csv": str(CSV_REPORT), "json": str(JSON_REPORT)})


if __name__ == "__main__":
    main()
