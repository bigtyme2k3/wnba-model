"""Research repeatable WNBA betting trends and simulated loss-streak staking behavior.

This module is descriptive only. It does not recommend or execute progressive staking.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "data" / "history"
OUT_JSON = ROOT / "data" / "dashboard" / "wnba_trend_research.json"
OUT_MD = ROOT / "docs" / "TREND_RESEARCH_REPORT.md"
CANDIDATES = [HISTORY / "best_bets_ledger.csv", HISTORY / "best_bets_performance.csv", HISTORY / "wnba_graded_bets.csv"]


def text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return "UNKNOWN"


def number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace("%", "").strip())
        except ValueError:
            pass
    return None


def result(row: dict[str, Any]) -> str:
    value = text(row, "result", "status", "outcome", "grade").upper()
    if value in {"W", "WIN", "WON", "1"}: return "WIN"
    if value in {"L", "LOSS", "LOST", "0"}: return "LOSS"
    if value in {"P", "PUSH", "VOID"}: return "PUSH"
    return "UNRESOLVED"


def load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen = set()
    for path in CANDIDATES:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                key = tuple(sorted((k, str(v)) for k, v in row.items()))
                if key not in seen:
                    seen.add(key)
                    row["_source"] = str(path.relative_to(ROOT))
                    rows.append(row)
    return rows


def group_summary(rows: list[dict[str, Any]], key_fn, min_samples: int = 8) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if result(row) in {"WIN", "LOSS"}:
            groups[key_fn(row)].append(row)
    output = []
    for name, group in groups.items():
        if len(group) < min_samples:
            continue
        wins = sum(result(r) == "WIN" for r in group)
        profits = [number(r, "profit", "pnl", "net") for r in group]
        stakes = [number(r, "stake", "stake_amount", "risk", "units") for r in group]
        profit = sum(v for v in profits if v is not None)
        stake = sum(v for v in stakes if v is not None)
        output.append({
            "segment": name,
            "samples": len(group),
            "wins": wins,
            "losses": len(group) - wins,
            "win_rate": round(wins / len(group), 4),
            "profit": round(profit, 4),
            "roi": round(profit / stake, 4) if stake else None,
        })
    return sorted(output, key=lambda r: ((r["roi"] if r["roi"] is not None else -999), r["samples"]), reverse=True)


def streak_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda r: text(r, "date", "target_date", "game_date", "created_at"))
    longest_loss = 0
    current_loss = 0
    runs = []
    for row in ordered:
        grade = result(row)
        if grade == "LOSS":
            current_loss += 1
            longest_loss = max(longest_loss, current_loss)
        elif grade == "WIN":
            if current_loss:
                runs.append(current_loss)
            current_loss = 0
    if current_loss:
        runs.append(current_loss)
    return {
        "longest_losing_streak": longest_loss,
        "loss_streak_count": len(runs),
        "average_completed_loss_streak": round(sum(runs) / len(runs), 3) if runs else 0,
        "streak_distribution": {str(n): runs.count(n) for n in sorted(set(runs))},
    }


def progressive_staking_simulation(rows: list[dict[str, Any]], base_unit: float = 1.0, cap_steps: int = 4) -> dict[str, Any]:
    """Compare flat staking with a capped doubling sequence for risk illustration only."""
    ordered = sorted(rows, key=lambda r: text(r, "date", "target_date", "game_date", "created_at"))
    flat_bankroll = 0.0
    progressive_bankroll = 0.0
    progressive_peak = 0.0
    progressive_drawdown = 0.0
    step = 0
    max_stake = base_unit
    resolved = 0
    for row in ordered:
        grade = result(row)
        if grade not in {"WIN", "LOSS"}:
            continue
        resolved += 1
        odds = number(row, "american_odds", "odds")
        decimal_profit = 1.0
        if odds is not None:
            decimal_profit = odds / 100 if odds > 0 else 100 / abs(odds)
        flat_bankroll += base_unit * decimal_profit if grade == "WIN" else -base_unit
        stake = base_unit * (2 ** min(step, cap_steps - 1))
        max_stake = max(max_stake, stake)
        progressive_bankroll += stake * decimal_profit if grade == "WIN" else -stake
        if grade == "WIN":
            step = 0
        else:
            step = min(step + 1, cap_steps - 1)
        progressive_peak = max(progressive_peak, progressive_bankroll)
        progressive_drawdown = max(progressive_drawdown, progressive_peak - progressive_bankroll)
    return {
        "resolved_bets": resolved,
        "base_unit": base_unit,
        "cap_steps": cap_steps,
        "flat_net_units": round(flat_bankroll, 4),
        "capped_progressive_net_units": round(progressive_bankroll, 4),
        "capped_progressive_max_stake_units": round(max_stake, 4),
        "capped_progressive_max_drawdown_units": round(progressive_drawdown, 4),
        "warning": "Progressive staking increases exposure after losses and can amplify drawdowns. Results are descriptive, not a recommendation.",
    }


def audit() -> dict[str, Any]:
    rows = load_rows()
    resolved = [r for r in rows if result(r) in {"WIN", "LOSS"}]
    segments = {
        "market": group_summary(resolved, lambda r: text(r, "stat", "market", "bet_type")),
        "sportsbook": group_summary(resolved, lambda r: text(r, "sportsbook", "book")),
        "team": group_summary(resolved, lambda r: text(r, "team", "player_team", "team_abbr")),
        "side": group_summary(resolved, lambda r: text(r, "signal", "side", "selection")),
    }
    warnings = []
    if not resolved:
        warnings.append("No resolved historical bets were available for trend analysis.")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "yellow" if warnings else "green",
        "resolved_bets": len(resolved),
        "warnings": warnings,
        "segments": segments,
        "streak_profile": streak_profile(resolved),
        "staking_simulation": progressive_staking_simulation(resolved),
    }


def write_report(report: dict[str, Any]) -> None:
    lines = [
        "# WNBA Trend Research Report",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Resolved bets: **{report['resolved_bets']}**",
        "",
        "## Losing-Streak Profile",
        "",
        f"`{json.dumps(report['streak_profile'], sort_keys=True)}`",
        "",
        "## Staking Risk Illustration",
        "",
        f"`{json.dumps(report['staking_simulation'], sort_keys=True)}`",
    ]
    for category, rows in report["segments"].items():
        lines += ["", f"## Trends by {category.title()}", "", "| Segment | Samples | Win rate | ROI |", "|---|---:|---:|---:|"]
        if rows:
            for row in rows:
                lines.append(f"| {row['segment']} | {row['samples']} | {row['win_rate']} | {row['roi']} |")
        else:
            lines.append("| No segment met the minimum sample threshold | 0 |  |  |")
    lines += ["", "## Warnings", ""]
    lines += [f"- {w}" for w in report["warnings"]] or ["- None."]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = audit()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_report(report)
    print(json.dumps({"status": report["status"], "resolved_bets": report["resolved_bets"]}, indent=2))
    if args.strict and report["status"] == "red":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
