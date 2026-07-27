"""Acceptance checks for Sprint 19 Phase 2 CLV linking."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import wnba_clv_edge_linker as clv


def close(actual, expected, tolerance=1e-6):
    assert actual is not None
    assert abs(actual - expected) <= tolerance, (actual, expected)


def main() -> None:
    close(clv.implied_probability(-110), 110 / 210)
    close(clv.implied_probability(150), 100 / 250)
    close(clv.directional_line_clv(19.5, 20.5, "OVER"), 1.0)
    close(clv.directional_line_clv(19.5, 18.5, "UNDER"), 1.0)
    assert clv.clv_grade(1.0, None) == "POSITIVE"
    assert clv.clv_grade(-1.0, None) == "NEGATIVE"

    with tempfile.TemporaryDirectory() as tmp:
        previous = os.getcwd()
        os.chdir(tmp)
        try:
            Path("data/history").mkdir(parents=True)
            edge = {
                "edge_key": "x",
                "date": "2026-07-27",
                "player": "Player A",
                "game": "A@B",
                "market": "PTS",
                "selection": "OVER",
                "sportsbook_line": 19.5,
                "american_odds": -110,
                "sportsbook": "FanDuel",
                "result": "WIN",
            }
            snapshots = [
                {"date":"2026-07-27","stage":"open","captured_at_utc":"2026-07-27T12:00:00Z","player":"Player A","game":"A@B","stat":"PTS","signal":"OVER","line":18.5,"over_price":-105,"book":"FanDuel"},
                {"date":"2026-07-27","stage":"bet","captured_at_utc":"2026-07-27T18:00:00Z","player":"Player A","game":"A@B","stat":"PTS","signal":"OVER","line":19.5,"over_price":-110,"book":"FanDuel"},
                {"date":"2026-07-27","stage":"close","captured_at_utc":"2026-07-27T22:00:00Z","player":"Player A","game":"A@B","stat":"PTS","signal":"OVER","line":20.5,"over_price":-120,"book":"FanDuel"},
            ]
            Path(clv.EDGE_HISTORY).write_text(json.dumps(edge)+"\n", encoding="utf-8")
            Path(clv.SNAPSHOTS).write_text("\n".join(json.dumps(x) for x in snapshots)+"\n", encoding="utf-8")
            first = clv.build("2026-07-27")
            assert first["graded_records"] == 1
            assert first["positive_clv"] == 1
            assert first["target_graded_records"] == 1
            stored = json.loads(Path(clv.EDGE_HISTORY).read_text().strip())
            close(stored["opening_line"], 18.5)
            close(stored["bet_time_line"], 19.5)
            close(stored["closing_line"], 20.5)
            close(stored["line_clv"], 1.0)
            assert stored["clv_grade"] == "POSITIVE"
            second = clv.build("2026-07-27")
            assert second["graded_records"] == 1
            assert len(Path(clv.EDGE_HISTORY).read_text().splitlines()) == 1
            assert Path("data/warehouse/wnba_clv_edge_report.json").is_file()
            assert Path("data/dashboard/wnba_clv_edge_report.json").is_file()
        finally:
            os.chdir(previous)
    print("Sprint 19 Phase 2 CLV QA passed.")


if __name__ == "__main__":
    main()
