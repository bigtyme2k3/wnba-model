"""Semantic QA for WNBA V4 model outputs.

Validates betting calculations, decision consistency, date alignment, duplicate
records, portfolio construction, and legitimate pass-day behavior.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "dashboard"
OUT = DATA / "wnba_v4_output_qa.json"
REPORT = ROOT / "docs" / "V4_OUTPUT_QA_REPORT.md"
ALLOWED_BOOKS = {"DraftKings", "FanDuel", "Fanatics"}
SUPPORTED_STATS = {"PTS", "REB", "AST", "PRA", "PR", "PA", "RA", "3PM", "STL", "BLK", "TOV"}


def load(name: str, default: Any) -> Any:
    path = DATA / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def implied_probability(american: float) -> float:
    return american / (american + 100) if american > 0 else abs(american) / (abs(american) + 100)


def issue(level: str, code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"level": level, "code": code, "message": message, "context": context}


def rows_from(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def key_for(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(k) or "").strip().lower() for k in ("player", "game", "stat", "line", "signal"))


def audit() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    decisions_doc = load("wnba_decision_engine_final.json", {})
    decisions = rows_from(decisions_doc, "top_decisions", "qualified_bets", "rows")
    qualified = rows_from(decisions_doc, "qualified_bets") or [r for r in decisions if r.get("final_action") == "BET"]
    portfolio_doc = load("wnba_portfolio_optimizer_v2.json", {})
    portfolio = rows_from(portfolio_doc, "recommended_card", "bets", "portfolio")
    risk_doc = load("wnba_risk_allocation.json", {})
    risk_rows = rows_from(risk_doc, "allocations", "bets", "recommended_card", "rows")

    target_dates = {}
    for name, doc in {
        "decisions": decisions_doc,
        "portfolio": portfolio_doc,
        "risk": risk_doc,
        "master": load("wnba_master.json", {}),
        "status": load("wnba_v4_status.json", {}),
    }.items():
        if isinstance(doc, dict) and doc.get("target_date"):
            target_dates[name] = str(doc["target_date"])
    if len(set(target_dates.values())) > 1:
        findings.append(issue("error", "DATE_MISMATCH", "Dashboard model outputs reference different target dates", dates=target_dates))

    seen: dict[tuple[str, ...], int] = {}
    for index, row in enumerate(decisions):
        row_id = {"index": index, "player": row.get("player"), "stat": row.get("stat"), "game": row.get("game")}
        key = key_for(row)
        if all(key):
            if key in seen:
                findings.append(issue("error", "DUPLICATE_DECISION", "Duplicate decision row", first_index=seen[key], **row_id))
            seen[key] = index

        for field in ("simulation_probability", "implied_probability"):
            value = row.get(field)
            if value is not None and (not finite(value) or not 0 <= float(value) <= 1):
                findings.append(issue("error", "BAD_PROBABILITY", f"{field} is outside 0-1", field=field, value=value, **row_id))
        for field in ("confidence", "final_score", "consensus_score"):
            value = row.get(field)
            if value is not None and (not finite(value) or not 0 <= float(value) <= 100):
                findings.append(issue("error", "BAD_SCORE", f"{field} is outside 0-100", field=field, value=value, **row_id))

        odds = row.get("american_odds")
        stored_prob = row.get("implied_probability")
        if finite(odds) and float(odds) != 0 and finite(stored_prob):
            expected = implied_probability(float(odds))
            if abs(expected - float(stored_prob)) > 0.0015:
                findings.append(issue("error", "IMPLIED_PROBABILITY_MISMATCH", "Stored implied probability does not match American odds", odds=odds, stored=stored_prob, expected=round(expected, 4), **row_id))

        if row.get("sportsbook") and row.get("sportsbook") not in ALLOWED_BOOKS:
            findings.append(issue("error", "UNSUPPORTED_BOOK", "Decision uses a sportsbook outside the approved set", sportsbook=row.get("sportsbook"), **row_id))
        if row.get("stat") and str(row.get("stat")).upper() not in SUPPORTED_STATS:
            findings.append(issue("error", "UNSUPPORTED_MARKET", "Unsupported stat market reached decision output", value=row.get("stat"), **row_id))

        action = str(row.get("final_action") or "").upper()
        eligible = bool(row.get("eligible_for_bet"))
        failures = row.get("guardrail_failures") or []
        if action == "BET" and not eligible:
            findings.append(issue("error", "INELIGIBLE_BET", "BET action bypassed eligibility guardrails", **row_id))
        if action == "BET" and failures:
            findings.append(issue("error", "BET_WITH_FAILURES", "BET action contains guardrail failures", failures=failures, **row_id))
        if eligible and action != "BET":
            findings.append(issue("warning", "ELIGIBLE_NOT_BET", "Row is eligible but final action is not BET", action=action, **row_id))
        if action == "BET":
            ev = row.get("ev_pct")
            if not finite(ev) or not 2 <= float(ev) <= 20:
                findings.append(issue("error", "BET_EV_OUT_OF_RANGE", "Final BET has EV outside the configured 2-20% range", ev_pct=ev, **row_id))
            probability = row.get("simulation_probability")
            if finite(probability) and float(probability) < 0.56:
                findings.append(issue("error", "BET_PROBABILITY_TOO_LOW", "Final BET is below the configured probability floor", probability=probability, **row_id))
            if int(row.get("history_games") or 0) < 5:
                findings.append(issue("error", "BET_HISTORY_TOO_LOW", "Final BET has fewer than five history games", history_games=row.get("history_games"), **row_id))
            if int(row.get("book_count") or 0) < 2:
                findings.append(issue("error", "BET_BOOK_COUNT_TOO_LOW", "Final BET has fewer than two sportsbook sources", book_count=row.get("book_count"), **row_id))

    summary = decisions_doc.get("summary", {}) if isinstance(decisions_doc, dict) else {}
    expected_rows = summary.get("rows")
    if finite(expected_rows) and int(expected_rows) != len(decisions):
        findings.append(issue("error", "DECISION_COUNT_MISMATCH", "Decision summary row count does not match output", summary_rows=expected_rows, actual_rows=len(decisions)))
    expected_bets = summary.get("bets")
    if finite(expected_bets) and int(expected_bets) != len(qualified):
        findings.append(issue("error", "BET_COUNT_MISMATCH", "Decision summary bet count does not match qualified bets", summary_bets=expected_bets, actual_bets=len(qualified)))

    if len(portfolio) > 5:
        findings.append(issue("error", "PORTFOLIO_CAP_EXCEEDED", "Portfolio contains more than five bets", count=len(portfolio)))
    player_counts: dict[str, int] = {}
    game_counts: dict[str, int] = {}
    total_stake = 0.0
    for row in portfolio:
        player = str(row.get("player") or "UNKNOWN").strip().lower()
        game = str(row.get("game") or "UNKNOWN").strip().lower()
        player_counts[player] = player_counts.get(player, 0) + 1
        game_counts[game] = game_counts.get(game, 0) + 1
        for field in ("stake", "stake_amount", "recommended_stake"):
            if finite(row.get(field)):
                total_stake += float(row[field])
                break
    if any(count > 1 for count in player_counts.values()):
        findings.append(issue("error", "PORTFOLIO_PLAYER_DUPLICATION", "Portfolio contains multiple bets for the same player", counts=player_counts))
    if any(count > 2 for count in game_counts.values()):
        findings.append(issue("error", "PORTFOLIO_GAME_CONCENTRATION", "Portfolio contains more than two bets from one game", counts=game_counts))

    bankroll = None
    for doc in (risk_doc, portfolio_doc):
        if isinstance(doc, dict):
            for field in ("bankroll", "capital", "starting_bankroll"):
                if finite(doc.get(field)):
                    bankroll = float(doc[field])
                    break
        if bankroll is not None:
            break
    if bankroll and total_stake > bankroll:
        findings.append(issue("error", "STAKE_EXCEEDS_BANKROLL", "Portfolio stake exceeds bankroll", total_stake=total_stake, bankroll=bankroll))

    if not qualified and not portfolio:
        findings.append(issue("info", "VALID_PASS_DAY", "No bets qualified and the portfolio is empty; this is a legitimate pass day", decision_rows=len(decisions)))
    elif qualified and not portfolio:
        findings.append(issue("error", "PORTFOLIO_SILENT_FAILURE", "Qualified bets exist but portfolio output is empty", qualified_bets=len(qualified)))
    elif not qualified and portfolio:
        findings.append(issue("error", "PORTFOLIO_WITHOUT_QUALIFIED_BETS", "Portfolio contains bets when the decision engine produced no qualified bets", portfolio_bets=len(portfolio)))

    errors = [f for f in findings if f["level"] == "error"]
    warnings = [f for f in findings if f["level"] == "warning"]
    status = "red" if errors else "yellow" if warnings else "green"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "summary": {
            "decision_rows": len(decisions),
            "qualified_bets": len(qualified),
            "portfolio_bets": len(portfolio),
            "risk_rows": len(risk_rows),
            "errors": len(errors),
            "warnings": len(warnings),
            "info": sum(f["level"] == "info" for f in findings),
            "target_dates": target_dates,
        },
        "findings": findings,
    }


def write_markdown(result: dict[str, Any]) -> None:
    lines = [
        "# WNBA V4 Model Output QA", "",
        f"Generated: `{result['generated_at_utc']}`", "",
        f"**Status:** {result['status'].upper()}", "",
        "## Summary", "",
    ]
    for key, value in result["summary"].items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    lines.extend(["", "## Findings", ""])
    if not result["findings"]:
        lines.append("- No semantic output issues detected.")
    else:
        for finding in result["findings"]:
            context = json.dumps(finding["context"], sort_keys=True, default=str)
            lines.append(f"- **{finding['level'].upper()} — {finding['code']}**: {finding['message']} `{context}`")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = audit()
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_markdown(result)
    print(json.dumps(result["summary"], indent=2))
    print(f"V4 output QA status: {result['status']}")
    if args.strict and result["status"] == "red":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
