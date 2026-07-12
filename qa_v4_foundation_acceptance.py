"""Deterministic production acceptance tests for M07-M09."""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

import wnba_matchup_intelligence as matchup
import wnba_play_by_play_layer as pbp
import wnba_projection_ai as projection

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "dashboard" / "wnba_v4_foundation_acceptance.json"
REPORT = ROOT / "docs" / "V4_FOUNDATION_ACCEPTANCE_REPORT.md"


@contextmanager
def temp_cwd():
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            yield Path(directory)
        finally:
            os.chdir(old)


def check(module: str, name: str, fn: Callable[[], None]) -> dict[str, Any]:
    try:
        fn(); return {"module": module, "test": name, "passed": True, "detail": ""}
    except Exception as exc:
        return {"module": module, "test": name, "passed": False, "detail": str(exc)}


def m07_tests() -> list[dict[str, Any]]:
    def observed_events() -> None:
        with temp_cwd():
            os.makedirs("data/raw", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
            events = [
                {"game": "A @ B", "type": "made shot", "period": 1, "clock": "09:30", "team": "A", "points": 2},
                {"game": "A @ B", "type": "turnover", "period": 1, "clock": "09:00", "team": "B"},
                {"game": "A @ B", "type": "substitution", "period": 1, "clock": "08:30", "team": "A", "description": "P2 for P1"},
                {"game": "A @ B", "type": "defensive rebound", "period": 1, "clock": "08:00", "team": "B"},
            ]
            json.dump({"events": events}, open("data/raw/wnba_play_by_play.json", "w"))
            json.dump({"games": [{"game": "A @ B", "bucket": "today"}]}, open("data/dashboard/wnba_master.json", "w"))
            report = pbp.build("2099-01-01"); row = report["games"][0]
            assert report["summary"]["events"] == 4
            assert row["mode"] == "observed_play_by_play"
            assert row["possessions"] > 0
            assert row["substitution_count"] == 1
            assert len(row["lineup_stints"]) == 1
            assert 0 <= row["data_confidence"] <= 1

    def explicit_fallback() -> None:
        with temp_cwd():
            os.makedirs("data/dashboard", exist_ok=True)
            json.dump({"games": [{"game": "A @ B", "bucket": "today"}]}, open("data/dashboard/wnba_master.json", "w"))
            report = pbp.build("2099-01-01"); row = report["games"][0]
            assert row["fallback_used"] is True
            assert row["mode"] == "schedule_baseline"
            assert "NO_PLAY_BY_PLAY" in row["quality_flags"]
            assert row["observed_event_count"] == 0

    return [check("M07", "normalizes events, possessions and substitutions", observed_events), check("M07", "labels fallback without inventing observed data", explicit_fallback)]


def m08_tests() -> list[dict[str, Any]]:
    def component_trace() -> None:
        with temp_cwd():
            os.makedirs("data/raw", exist_ok=True); os.makedirs("data/warehouse", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
            pd.DataFrame([{"player": "Player One", "team": "B", "opp": "A", "game": "A @ B", "stat": "PTS", "line": 19.5, "pred": 22, "signal": "OVER"}]).to_csv("data/raw/player_points_today.csv", index=False)
            json.dump({"players": [{"player": "Player One", "intelligence": {"role_score": 70}, "recent_form": {"minutes_trend": "UP", "points_trend": "UP"}}]}, open("data/warehouse/wnba_player_intelligence.json", "w"))
            json.dump([{"team": "A", "wins": 4, "losses": 16}], open("data/warehouse/wnba_standings.json", "w"))
            json.dump({"games": [{"game": "A @ B", "bucket": "today", "rest_days": {"B": 0}}]}, open("data/dashboard/wnba_master.json", "w"))
            json.dump({"games": [{"game": "A @ B", "pace_40": 84, "mode": "observed_play_by_play", "data_confidence": 1}]}, open("data/warehouse/wnba_play_by_play_layer.json", "w"))
            json.dump({"adjustments": [{"player": "Player One", "severity": "ACTIVE"}]}, open("data/warehouse/wnba_injury_intelligence.json", "w"))
            report = matchup.build("2099-01-01"); row = report["matchups"][0]
            required = {"opponent_defense", "pace", "rest", "venue", "trend", "injury", "role"}
            assert required <= set(row["components"])
            assert row["back_to_back"] is True
            assert row["home"] is True
            assert row["pace_mode"] == "observed_play_by_play"
            assert len(row["source_trace"]) >= 5
            assert 0 <= row["matchup_score"] <= 100

    return [check("M08", "rest, venue, pace, defense, role and injury trace", component_trace)]


def m09_tests() -> list[dict[str, Any]]:
    def projection_contract() -> None:
        with temp_cwd():
            os.makedirs("data/raw", exist_ok=True); os.makedirs("data/warehouse", exist_ok=True)
            pd.DataFrame([{"player": "Player One", "team": "B", "game": "A @ B", "stat": "PTS", "line": 19.5, "pred": 21, "season_avg": 20, "last10": ""}]).to_csv("data/raw/player_points_today.csv", index=False)
            json.dump({"all_simulations": [{"player": "Player One", "game": "A @ B", "stat": "PTS", "p50": 22, "stddev": 3}]}, open("data/warehouse/wnba_monte_carlo_engine.json", "w"))
            json.dump({"matchups": [{"player": "Player One", "game": "A @ B", "stat": "PTS", "matchup_score": 68, "total_adjustment": 2, "components": {"pace": 1}}]}, open("data/warehouse/wnba_matchup_intelligence.json", "w"))
            json.dump({"players": [{"player": "Player One", "recent_form": {"minutes_avg": 32}}]}, open("data/warehouse/wnba_player_intelligence.json", "w"))
            json.dump({"adjustments": [{"player": "Player One", "severity": "ACTIVE", "projection_factor": 0}]}, open("data/warehouse/wnba_injury_intelligence.json", "w"))
            report = projection.build("2099-01-01"); row = report["projections"][0]
            assert row["ai_projection"] >= 0
            assert row["interval_80"][0] <= row["ai_projection"] <= row["interval_80"][1]
            assert 25 <= row["projection_confidence"] <= 95
            assert {"baseline", "matchup", "pace", "injury", "minutes_usage"} <= set(row["feature_contributions"])
            assert len(row["source_trace"]) >= 5
            assert row["variance"] > 0

    def bounded_injury() -> None:
        with temp_cwd():
            os.makedirs("data/raw", exist_ok=True); os.makedirs("data/warehouse", exist_ok=True)
            pd.DataFrame([{"player": "Player One", "game": "A @ B", "stat": "PTS", "line": 19.5, "pred": 20}]).to_csv("data/raw/player_points_today.csv", index=False)
            json.dump({"adjustments": [{"player": "Player One", "severity": "QUESTIONABLE", "projection_factor": -0.08}]}, open("data/warehouse/wnba_injury_intelligence.json", "w"))
            row = projection.build("2099-01-01")["projections"][0]
            assert row["feature_contributions"]["injury"] <= 0
            assert row["ai_projection"] >= 0

    return [check("M09", "projection trace, uncertainty and confidence", projection_contract), check("M09", "injury adjustment remains bounded", bounded_injury)]


def main() -> None:
    tests = m07_tests() + m08_tests() + m09_tests()
    failed = [x for x in tests if not x["passed"]]
    modules: dict[str, list[dict[str, Any]]] = {}
    for item in tests:
        modules.setdefault(item["module"], []).append(item)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "green" if not failed else "red",
        "summary": {"tests": len(tests), "passed": len(tests) - len(failed), "failed": len(failed)},
        "modules": {module: {"passed": all(x["passed"] for x in items), "tests": items} for module, items in modules.items()},
        "tests": tests,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# V4 M07–M09 Foundation Acceptance", "", f"**Status:** {report['status'].upper()}", "", f"Passed: {report['summary']['passed']}/{report['summary']['tests']}", ""]
    lines += [f"- {'PASS' if x['passed'] else 'FAIL'} — {x['module']} — {x['test']}{': ' + x['detail'] if x['detail'] else ''}" for x in tests]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
