"""Corrected semantic QA for WNBA V4 betting outputs."""
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
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def implied_probability(american: float) -> float:
    return 100 / (american + 100) if american > 0 else abs(american) / (abs(american) + 100)


def finding(level: str, code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"level": level, "code": code, "message": message, "context": context}


def audit() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    decision_doc = load("wnba_decision_engine_final.json", {})
    displayed = rows(decision_doc, "top_decisions", "qualified_bets")
    full = rows(decision_doc, "rows", "all_decisions")
    decision_rows = full or displayed
    qualified = rows(decision_doc, "qualified_bets") or [r for r in decision_rows if str(r.get("final_action") or "").upper() == "BET"]
    portfolio_doc = load("wnba_portfolio_optimizer_v2.json", {})
    portfolio = rows(portfolio_doc, "recommended_card", "bets", "portfolio")
    risk_doc = load("wnba_risk_allocation.json", {})
    risk_rows = rows(risk_doc, "allocations", "bets", "recommended_card", "rows")

    dates = {}
    for name, doc in {
        "decisions": decision_doc,
        "portfolio": portfolio_doc,
        "risk": risk_doc,
        "master": load("wnba_master.json", {}),
        "status": load("wnba_v4_status.json", {}),
    }.items():
        if isinstance(doc, dict) and doc.get("target_date"):
            dates[name] = str(doc["target_date"])
    if len(set(dates.values())) > 1:
        findings.append(finding("error", "DATE_MISMATCH", "Outputs reference different target dates", dates=dates))

    seen: dict[tuple[str, ...], int] = {}
    for index, row in enumerate(decision_rows):
        context = {"index": index, "player": row.get("player"), "stat": row.get("stat"), "game": row.get("game")}
        key = tuple(str(row.get(k) or "").strip().lower() for k in ("player", "game", "stat", "line", "signal"))
        if all(key):
            if key in seen:
                findings.append(finding("error", "DUPLICATE_DECISION", "Duplicate decision row", first_index=seen[key], **context))
            seen[key] = index

        for field in ("simulation_probability", "implied_probability"):
            value = row.get(field)
            if value is not None and (not finite(value) or not 0 <= float(value) <= 1):
                findings.append(finding("error", "BAD_PROBABILITY", f"{field} outside 0-1", field=field, value=value, **context))
        for field in ("confidence", "final_score", "consensus_score"):
            value = row.get(field)
            if value is not None and (not finite(value) or not 0 <= float(value) <= 100):
                findings.append(finding("error", "BAD_SCORE", f"{field} outside 0-100", field=field, value=value, **context))

        odds, stored = row.get("american_odds"), row.get("implied_probability")
        if finite(odds) and float(odds) != 0 and finite(stored):
            expected = implied_probability(float(odds))
            if abs(expected - float(stored)) > 0.0015:
                findings.append(finding("error", "IMPLIED_PROBABILITY_MISMATCH", "Stored implied probability does not match American odds", odds=odds, stored=stored, expected=round(expected, 4), **context))

        if row.get("sportsbook") and row.get("sportsbook") not in ALLOWED_BOOKS:
            findings.append(finding("error", "UNSUPPORTED_BOOK", "Unapproved sportsbook in decision output", sportsbook=row.get("sportsbook"), **context))
        if row.get("stat") and str(row.get("stat")).upper() not in SUPPORTED_STATS:
            findings.append(finding("error", "UNSUPPORTED_MARKET", "Unsupported market in decision output", value=row.get("stat"), **context))

        action = str(row.get("final_action") or "").upper()
        eligible = bool(row.get("eligible_for_bet"))
        failures = row.get("guardrail_failures") or []
        if action == "BET" and not eligible:
            findings.append(finding("error", "INELIGIBLE_BET", "BET bypassed eligibility guardrails", **context))
        if action == "BET" and failures:
            findings.append(finding("error", "BET_WITH_FAILURES", "BET contains guardrail failures", failures=failures, **context))
        if eligible and action != "BET":
            findings.append(finding("warning", "ELIGIBLE_NOT_BET", "Eligible row was not promoted to BET", action=action, **context))
        if action == "BET":
            ev = row.get("ev_pct")
            if not finite(ev) or not 2 <= float(ev) <= 20:
                findings.append(finding("error", "BET_EV_OUT_OF_RANGE", "BET EV outside 2-20%", ev_pct=ev, **context))
            if finite(row.get("simulation_probability")) and float(row["simulation_probability"]) < 0.56:
                findings.append(finding("error", "BET_PROBABILITY_TOO_LOW", "BET below probability floor", **context))
            if int(row.get("history_games") or 0) < 5:
                findings.append(finding("error", "BET_HISTORY_TOO_LOW", "BET has insufficient history", **context))
            if int(row.get("book_count") or 0) < 2:
                findings.append(finding("error", "BET_BOOK_COUNT_TOO_LOW", "BET has fewer than two books", **context))

    summary = decision_doc.get("summary", {}) if isinstance(decision_doc, dict) else {}
    expected_rows = summary.get("rows")
    if full and finite(expected_rows) and int(expected_rows) != len(full):
        findings.append(finding("error", "DECISION_COUNT_MISMATCH", "Summary does not match full decision output", summary_rows=expected_rows, actual_rows=len(full)))
    expected_bets = summary.get("bets")
    if finite(expected_bets) and int(expected_bets) != len(qualified):
        findings.append(finding("error", "BET_COUNT_MISMATCH", "Summary does not match qualified bets", summary_bets=expected_bets, actual_bets=len(qualified)))

    if len(portfolio) > 5:
        findings.append(finding("error", "PORTFOLIO_CAP_EXCEEDED", "Portfolio exceeds five bets", count=len(portfolio)))
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
                total_stake += float(row[field]); break
    if any(v > 1 for v in player_counts.values()):
        findings.append(finding("error", "PORTFOLIO_PLAYER_DUPLICATION", "Multiple bets for one player", counts=player_counts))
    if any(v > 2 for v in game_counts.values()):
        findings.append(finding("error", "PORTFOLIO_GAME_CONCENTRATION", "More than two bets from one game", counts=game_counts))

    bankroll = None
    for doc in (risk_doc, portfolio_doc):
        if isinstance(doc, dict):
            for field in ("bankroll", "capital", "starting_bankroll"):
                if finite(doc.get(field)):
                    bankroll = float(doc[field]); break
        if bankroll is not None:
            break
    if bankroll and total_stake > bankroll:
        findings.append(finding("error", "STAKE_EXCEEDS_BANKROLL", "Portfolio stake exceeds bankroll", total_stake=total_stake, bankroll=bankroll))

    if not qualified and not portfolio:
        findings.append(finding("info", "VALID_PASS_DAY", "No bets qualified and portfolio is empty", evaluated_rows=int(expected_rows) if finite(expected_rows) else len(decision_rows)))
    elif qualified and not portfolio:
        findings.append(finding("error", "PORTFOLIO_SILENT_FAILURE", "Qualified bets exist but portfolio is empty", qualified_bets=len(qualified)))
    elif not qualified and portfolio:
        findings.append(finding("error", "PORTFOLIO_WITHOUT_QUALIFIED_BETS", "Portfolio exists without qualified bets", portfolio_bets=len(portfolio)))

    errors = [x for x in findings if x["level"] == "error"]
    warnings = [x for x in findings if x["level"] == "warning"]
    status = "red" if errors else "yellow" if warnings else "green"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "summary": {"evaluated_rows": int(expected_rows) if finite(expected_rows) else len(decision_rows), "inspected_rows": len(decision_rows), "qualified_bets": len(qualified), "portfolio_bets": len(portfolio), "risk_rows": len(risk_rows), "errors": len(errors), "warnings": len(warnings), "info": sum(x["level"] == "info" for x in findings), "target_dates": dates},
        "findings": findings,
    }


def write_report(result: dict[str, Any]) -> None:
    lines = ["# WNBA V4 Model Output QA", "", f"Generated: `{result['generated_at_utc']}`", "", f"**Status:** {result['status'].upper()}", "", "## Summary", ""]
    lines += [f"- **{k.replace('_', ' ').title()}:** {v}" for k, v in result["summary"].items()]
    lines += ["", "## Findings", ""]
    for item in result["findings"]:
        lines.append(f"- **{item['level'].upper()} — {item['code']}**: {item['message']} `{json.dumps(item['context'], sort_keys=True, default=str)}`")
    if not result["findings"]:
        lines.append("- No semantic output issues detected.")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--strict", action="store_true"); args = parser.parse_args()
    result = audit(); DATA.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_report(result)
    print(json.dumps(result["summary"], indent=2)); print(f"V4 output QA status: {result['status']}")
    if args.strict and result["status"] == "red":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
