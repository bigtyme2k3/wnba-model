"""Deterministic acceptance tests for the player game-log warehouse."""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import wnba_player_game_log_warehouse as warehouse


@contextmanager
def temp_cwd():
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            yield Path(directory)
        finally:
            os.chdir(old)


def test_quarter_points_free_throws_and_fouls() -> None:
    with temp_cwd():
        os.makedirs("data/warehouse", exist_ok=True)
        events = [
            {"game":"A @ B","player":"Player One","team":"B","period":1,"event_type":"SHOT_MADE","points":2,"description":"Player One makes 2-pt shot"},
            {"game":"A @ B","player":"Player One","team":"B","period":1,"event_type":"FREE_THROW","points":1,"description":"Player One makes free throw"},
            {"game":"A @ B","player":"Player One","team":"B","period":2,"event_type":"SHOT_MADE","points":3,"description":"Player One makes 3-pt shot"},
            {"game":"A @ B","player":"Player One","team":"B","period":3,"event_type":"FOUL","points":0,"description":"Player One shooting foul"},
            {"game":"A @ B","player":"Player One","team":"B","period":4,"event_type":"FOUL","points":0,"description":"Player One technical foul"},
        ]
        json.dump({"events":events}, open("data/warehouse/wnba_play_by_play_layer.json","w"))
        report = warehouse.build("2099-01-01")
        row = report["records"][0]
        assert row["scoring"]["q1_pts"] == 3
        assert row["scoring"]["q2_pts"] == 3
        assert row["scoring"]["first_half_pts"] == 6
        assert row["scoring"]["total_pts"] == 6
        assert row["scoring"]["ftm"] == 1
        assert row["scoring"]["free_throw_points"] == 1
        assert row["fouls"]["shooting"] == 1
        assert row["fouls"]["technical"] == 1
        assert row["fouls"]["total_committed"] == 2
        assert row["data_quality"]["quarter_points_match_total"] is True
        assert row["data_quality"]["quarter_data_status"] == "complete"


def test_boxscore_fallback_does_not_invent_quarters() -> None:
    records = {}
    warehouse.merge_boxscores(records, [{"game":"A @ B","player":"Player Two","pts":18,"ftm":4,"fta":5,"pf":3,"reb":7,"ast":2}])
    row = next(iter(records.values()))
    warehouse.finalize(row)
    assert row["scoring"]["total_pts"] == 18
    assert row["scoring"]["free_throw_points"] == 4
    assert row["fouls"]["total_committed"] == 3
    assert row["scoring"]["q1_pts"] is None
    assert row["data_quality"]["quarter_data_status"] == "unavailable"


def main() -> None:
    tests = [
        ("quarter points, free throws and fouls", test_quarter_points_free_throws_and_fouls),
        ("boxscore fallback does not invent quarters", test_boxscore_fallback_does_not_invent_quarters),
    ]
    results=[]
    for name, fn in tests:
        try:
            fn(); results.append({"test":name,"passed":True,"detail":""})
        except Exception as exc:
            results.append({"test":name,"passed":False,"detail":str(exc)})
    failed=[r for r in results if not r["passed"]]
    report={"status":"green" if not failed else "red","summary":{"tests":len(results),"passed":len(results)-len(failed),"failed":len(failed)},"tests":results}
    Path("data/dashboard").mkdir(parents=True,exist_ok=True)
    json.dump(report,open("data/dashboard/wnba_player_game_log_acceptance.json","w"),indent=2)
    print(report["summary"])
    if failed: raise SystemExit(1)


if __name__ == "__main__":
    main()
