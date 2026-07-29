"""Validate graded betting performance, calibration, ROI, and CLV from available ledgers."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "data" / "history"
OUT_JSON = ROOT / "data" / "dashboard" / "wnba_betting_validation.json"
OUT_MD = ROOT / "docs" / "BETTING_ENGINE_VALIDATION_REPORT.md"

CANDIDATES = [
    HISTORY / "best_bets_ledger.csv",
    HISTORY / "best_bets_performance.csv",
    HISTORY / "wnba_graded_bets.csv",
]


def number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            value = str(value).replace("%", "").strip()
            return float(value)
        except ValueError:
            pass
    return None


def text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return "UNKNOWN"


def load_rows() -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    seen = set()
    for path in CANDIDATES:
        if not path.exists():
            continue
        sources.append(str(path.relative_to(ROOT)))
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                key = tuple(sorted((k, str(v)) for k, v in row.items()))
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
    return rows, sources


def normalized_result(row: dict[str, Any]) -> str:
    value = text(row, "result", "status", "outcome", "grade").upper()
    if value in {"W", "WIN", "WON", "1"}: return "WIN"
    if value in {"L", "LOSS", "LOST", "0"}: return "LOSS"
    if value in {"P", "PUSH", "VOID"}: return "PUSH"
    return "UNRESOLVED"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    graded = [r for r in rows if normalized_result(r) in {"WIN", "LOSS", "PUSH"}]
    wins = sum(normalized_result(r) == "WIN" for r in graded)
    losses = sum(normalized_result(r) == "LOSS" for r in graded)
    pushes = sum(normalized_result(r) == "PUSH" for r in graded)
    decisions = wins + losses

    profit = 0.0
    stake = 0.0
    clvs = []
    probs = []
    for row in graded:
        s = number(row, "stake", "stake_amount", "risk", "units")
        p = number(row, "profit", "pnl", "net", "return")
        if s is not None: stake += s
        if p is not None: profit += p
        clv = number(row, "clv", "clv_pct", "closing_line_value")
        if clv is not None: clvs.append(clv)
        prob = number(row, "simulation_probability", "probability", "model_probability", "win_probability")
        if prob is not None:
            probs.append(prob / 100 if prob > 1 else prob)

    by_market: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0})
    by_book: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0})
    for row in graded:
        result = normalized_result(row)
        if result not in {"WIN", "LOSS"}: continue
        market = text(row, "stat", "market", "bet_type")
        book = text(row, "sportsbook", "book")
        by_market[market]["wins" if result == "WIN" else "losses"] += 1
        by_book[book]["wins" if result == "WIN" else "losses"] += 1

    calibration = None
    if probs and decisions:
        resolved = [r for r in graded if normalized_result(r) in {"WIN", "LOSS"}]
        paired = []
        for row in resolved:
            prob = number(row, "simulation_probability", "probability", "model_probability", "win_probability")
            if prob is None: continue
            prob = prob / 100 if prob > 1 else prob
            paired.append((prob, 1.0 if normalized_result(row) == "WIN" else 0.0))
        if paired:
            calibration = {
                "predicted_rate": round(sum(p for p, _ in paired) / len(paired), 4),
                "actual_rate": round(sum(y for _, y in paired) / len(paired), 4),
                "brier_score": round(sum((p-y)**2 for p, y in paired) / len(paired), 4),
            }

    def finalize(grouped: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        out = []
        for name, counts in sorted(grouped.items()):
            total = counts["wins"] + counts["losses"]
            out.append({"name": name, **counts, "graded": total, "win_rate": round(counts["wins"] / total, 4) if total else None})
        return out

    return {
        "graded": len(graded),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": round(wins / decisions, 4) if decisions else None,
        "stake": round(stake, 4),
        "profit": round(profit, 4),
        "roi": round(profit / stake, 4) if stake else None,
        "average_clv": round(sum(clvs) / len(clvs), 4) if clvs else None,
        "clv_samples": len(clvs),
        "calibration": calibration,
        "by_market": finalize(by_market),
        "by_sportsbook": finalize(by_book),
    }


def audit() -> dict[str, Any]:
    rows, sources = load_rows()
    metrics = summarize(rows)
    warnings = []
    if metrics["graded"] == 0: warnings.append("No graded bets were available.")
    if metrics["roi"] is None: warnings.append("ROI unavailable because stake/profit fields were not found.")
    if metrics["average_clv"] is None: warnings.append("CLV unavailable because no CLV fields were found.")
    if metrics["calibration"] is None: warnings.append("Calibration unavailable because model probabilities were not found.")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "yellow" if warnings else "green",
        "sources": sources,
        "warnings": warnings,
        "metrics": metrics,
    }


def write_report(result: dict[str, Any]) -> None:
    m = result["metrics"]
    lines = ["# WNBA Betting Engine Validation", "", f"Generated: `{result['generated_at_utc']}`", f"Status: **{result['status'].upper()}**", "", "## Core Metrics", ""]
    for key in ("graded", "wins", "losses", "pushes", "win_rate", "stake", "profit", "roi", "average_clv", "clv_samples"):
        lines.append(f"- **{key.replace('_',' ').title()}:** {m.get(key)}")
    lines += ["", "## Calibration", "", f"`{json.dumps(m.get('calibration'), sort_keys=True)}`", "", "## By Market", "", "| Market | Graded | Win rate |", "|---|---:|---:|"]
    for row in m["by_market"]:
        lines.append(f"| {row['name']} | {row['graded']} | {row['win_rate']} |")
    lines += ["", "## By Sportsbook", "", "| Sportsbook | Graded | Win rate |", "|---|---:|---:|"]
    for row in m["by_sportsbook"]:
        lines.append(f"| {row['name']} | {row['graded']} | {row['win_rate']} |")
    lines += ["", "## Warnings", ""]
    lines += [f"- {warning}" for warning in result["warnings"]] or ["- None."]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--strict", action="store_true"); args = parser.parse_args()
    result = audit()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_report(result)
    print(json.dumps(result["metrics"], indent=2))
    if args.strict and result["status"] == "red": raise SystemExit(1)


if __name__ == "__main__":
    main()
