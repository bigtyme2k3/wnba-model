"""Acceptance checks for Sprint 19 Phase 1 edge database."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import wnba_edge_database as edge


def assert_close(actual, expected, tolerance=1e-6):
    assert actual is not None
    assert abs(actual - expected) <= tolerance, (actual, expected)


def main() -> None:
    assert_close(edge.implied_probability(-110), 110 / 210)
    assert_close(edge.implied_probability(150), 100 / 250)
    assert_close(edge.expected_value(0.60, -110), 0.60 * (100 / 110) - 0.40)

    with tempfile.TemporaryDirectory() as tmp:
        previous = os.getcwd()
        os.chdir(tmp)
        try:
            Path("data/history").mkdir(parents=True)
            source = {
                "history_key": "2026-07-27|Player A|A@B|PTS|19.5|OVER",
                "date": "2026-07-27",
                "player": "Player A",
                "team": "A",
                "game": "A@B",
                "stat": "PTS",
                "line": 19.5,
                "pred": 22.0,
                "signal": "OVER",
                "simulation_probability": 0.60,
                "american_odds": -110,
                "sportsbook": "FanDuel",
                "confidence": 74,
                "final_action": "BET",
                "eligible_for_bet": True,
                "stake": 20,
                "outcome": None,
            }
            Path(edge.MODEL_HISTORY).write_text(json.dumps(source) + "\n", encoding="utf-8")
            first = edge.build("2026-07-27")
            assert first["inserted_records"] == 1
            assert first["total_records"] == 1
            assert first["target_records"] == 1

            second = edge.build("2026-07-27")
            assert second["inserted_records"] == 0
            assert second["total_records"] == 1

            source.update({"outcome": "WIN", "actual": 24, "profit_loss": 18.18, "closing_line": 20.5})
            Path(edge.MODEL_HISTORY).write_text(json.dumps(source) + "\n", encoding="utf-8")
            settled = edge.build("2026-07-27")
            assert settled["updated_records"] == 1
            assert settled["settled_records"] == 1
            assert settled["graded_decisions"] == 1
            assert_close(settled["win_rate"], 1.0)
            assert Path("data/warehouse/wnba_edge_database.json").is_file()
            assert Path("data/dashboard/wnba_edge_database.json").is_file()
        finally:
            os.chdir(previous)

    print("Sprint 19 Phase 1 edge database QA passed.")


if __name__ == "__main__":
    main()
