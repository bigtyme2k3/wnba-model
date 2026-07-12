"""Production acceptance tests for V4 modules M11-M15.

The tests are deterministic and use synthetic fixtures so no live slate or API
availability can hide a regression. A JSON report is written for V4 Health.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import wnba_decision_engine_final as decision
import wnba_game_market_model as game_model
import wnba_portfolio_optimizer_v2 as portfolio
import wnba_risk_allocation as risk

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "dashboard" / "wnba_v4_acceptance.json"
REPORT = ROOT / "docs" / "V4_ACCEPTANCE_REPORT.md"


@contextmanager
def temporary_cwd():
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            yield Path(directory)
        finally:
            os.chdir(old)


def result(module: str, name: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"module": module, "test": name, "passed": passed, "detail": detail}


def check(module: str, name: str, fn: Callable[[], None]) -> dict[str, Any]:
    try:
        fn()
        return result(module, name, True)
    except Exception as exc:
        return result(module, name, False, str(exc))


def test_m11_m12() -> list[dict[str, Any]]:
    tests = []

    def game_schema() -> None:
        with temporary_cwd():
            os.makedirs("data/dashboard", exist_ok=True)
            master = {
                "games": [{"game": "Away @ Home", "bucket": "today", "spread": -3.5, "total": 161.5}]
            }
            matchup = {
                "games": [{"game": "Away @ Home", "projected_margin": -1.0, "projected_total": 166.0}]
            }
            json.dump(master, open("data/dashboard/wnba_master.json", "w"))
            json.dump(matchup, open("data/dashboard/wnba_matchup_intelligence.json", "w"))
            report = game_model.build("2099-01-01")
            assert report["summary"]["games"] == 1
            row = report["games"][0]
            required = {
                "market_spread", "projected_margin", "spread_pick", "spread_probability",
                "market_total", "projected_total", "total_pick", "total_probability", "top_picks",
            }
            assert required <= set(row), required - set(row)
            assert row["spread_source"] == "upstream_projection"
            assert row["total_source"] == "upstream_projection"
            assert 0 <= row["spread_probability"] <= 1
            assert 0 <= row["total_probability"] <= 1
            assert len(row["top_picks"]) <= 3

    def no_fake_edge() -> None:
        with temporary_cwd():
            os.makedirs("data/dashboard", exist_ok=True)
            json.dump({"games": [{"game": "Away @ Home", "bucket": "today", "spread": -3.5, "total": 161.5}]}, open("data/dashboard/wnba_master.json", "w"))
            row = game_model.build("2099-01-01")["games"][0]
            assert row["spread_source"] == "market_baseline"
            assert row["total_source"] == "market_baseline"
            assert row["spread_probability"] == 0.5
            assert row["total_probability"] == 0.5
            assert row["spread_pick"] == "PASS"
            assert row["total_pick"] == "PASS"
            assert row["top_picks"] == []

    tests.append(check("M11/M12", "game projection schema and bounded probabilities", game_schema))
    tests.append(check("M11/M12", "market baseline never invents an edge", no_fake_edge))
    return tests


def test_m13() -> list[dict[str, Any]]:
    def odds_math() -> None:
        assert abs(decision.american_to_implied(100) - 0.5) < 1e-9
        assert abs(decision.american_to_implied(-110) - (110 / 210)) < 1e-9
        assert abs(decision.american_to_implied(200) - (100 / 300)) < 1e-9

    def eligibility_contract() -> None:
        source = Path(decision.__file__).read_text(encoding="utf-8")
        assert '"prequalified_for_bet": prequalified' in source
        assert '"eligible_for_bet": eligible_for_bet' in source
        assert 'if eligible_for_bet:' in source
        assert 'action = "BET"' in source

    return [
        check("M13", "American odds implied probability", odds_math),
        check("M13", "final BET eligibility contract", eligibility_contract),
    ]


def qualified_row(index: int, game: str, player: str, probability: float = 0.62) -> dict[str, Any]:
    return {
        "player": player,
        "game": game,
        "team": game.split(" @ ")[-1],
        "stat": "PTS",
        "signal": "OVER",
        "line": 18.5,
        "final_action": "BET",
        "eligible_for_bet": True,
        "simulation_probability": probability,
        "american_odds": -110,
        "final_score": 85 - index,
        "ev_pct": 7 + index / 10,
    }


def test_m14() -> list[dict[str, Any]]:
    def diversified_card() -> None:
        fixture = {"qualified_bets": [
            qualified_row(0, "A @ B", "P1"),
            qualified_row(1, "A @ B", "P2"),
            qualified_row(2, "A @ B", "P3"),
            qualified_row(3, "C @ D", "P4"),
            qualified_row(4, "E @ F", "P5"),
            qualified_row(5, "G @ H", "P6"),
        ]}
        original = portfolio.load
        portfolio.load = lambda path, default: fixture if "decision_engine" in path else default
        try:
            with temporary_cwd():
                report = portfolio.build("2099-01-01", bankroll=500)
        finally:
            portfolio.load = original
        card = report["recommended_card"]
        assert len(card) <= 5
        assert len({x["player"] for x in card}) == len(card)
        counts: dict[str, int] = {}
        for row in card:
            counts[row["game"]] = counts.get(row["game"], 0) + 1
        assert all(count <= 2 for count in counts.values())
        assert report["summary"]["exposure_pct"] <= 8
        assert all(x["kelly_fraction"] <= 0.025 for x in card)

    def valid_pass_day() -> None:
        original = portfolio.load
        portfolio.load = lambda path, default: {"qualified_bets": []} if "decision_engine" in path else default
        try:
            with temporary_cwd():
                report = portfolio.build("2099-01-01", bankroll=500)
        finally:
            portfolio.load = original
        assert report["summary"]["qualified_candidates"] == 0
        assert report["summary"]["card_size"] == 0
        assert report["recommended_card"] == []

    return [
        check("M14", "diversification and exposure limits", diversified_card),
        check("M14", "valid no-bet pass day", valid_pass_day),
    ]


def test_m15() -> list[dict[str, Any]]:
    def allocation_caps() -> None:
        fixture = {"recommended_card": [
            {**qualified_row(0, "A @ B", "P1"), "recommended_stake": 40},
            {**qualified_row(1, "C @ D", "P2"), "recommended_stake": 10},
        ]}
        original = risk.load
        risk.load = lambda path, default: fixture if "portfolio_optimizer" in path else default
        try:
            with temporary_cwd():
                report = risk.build("2099-01-01", capital=500)
        finally:
            risk.load = original
        assert all(row["capped_amount"] <= 15 for row in report["allocation"])
        assert report["summary"]["total_exposure"] <= 90
        assert report["summary"]["exposure_pct"] <= 0.18
        assert all(math.isfinite(row["unit_multiple"]) for row in report["allocation"])

    return [check("M15", "position and card exposure caps", allocation_caps)]


def main() -> None:
    tests = test_m11_m12() + test_m13() + test_m14() + test_m15()
    failed = [x for x in tests if not x["passed"]]
    modules = {}
    for item in tests:
        modules.setdefault(item["module"], []).append(item)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "green" if not failed else "red",
        "summary": {"tests": len(tests), "passed": len(tests) - len(failed), "failed": len(failed)},
        "modules": {key: {"passed": all(x["passed"] for x in value), "tests": value} for key, value in modules.items()},
        "tests": tests,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# V4 M11–M15 Acceptance Report", "", f"**Status:** {report['status'].upper()}", "", f"Passed: {report['summary']['passed']}/{report['summary']['tests']}", ""]
    lines += [f"- {'PASS' if x['passed'] else 'FAIL'} — {x['module']} — {x['test']}{': ' + x['detail'] if x['detail'] else ''}" for x in tests]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
