"""Acceptance tests for Minutes Projection Engine v2."""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import wnba_minutes_projection_v2 as engine


@contextmanager
def temp_cwd():
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            yield Path(directory)
        finally:
            os.chdir(old)


def sample_rows(minutes, starter=True, team="Example"):
    rows=[]
    for i,value in enumerate(minutes):
        rows.append({
            "player":"Player One","team":team,"minutes":value,"starter":starter,
            "game_date":f"2026-06-{30-i:02d}","home_away":"home" if i%2==0 else "away",
            "game_id":str(i),
        })
    return rows


def test_stable_starter_projection():
    rows=sample_rows([35,36,35,34,36,35,34,35,36,35,34,35])
    result=engine.project_player("Player One",rows,"2026-07-01",{"team":"Example","opponent":"Other","home_away":"home","spread":2.5,"blowout_probability":0.09},None)
    assert 33 <= result["projected_minutes"] <= 38
    assert result["minutes_p10"] < result["minutes_p50"] < result["minutes_p90"]
    assert result["confidence"] >= 75
    assert result["data_quality_status"] == "complete"


def test_out_player_is_zero():
    rows=sample_rows([32,33,34,32,33,34,32,33,34,32])
    injury={"severity":"OUT","projected_minutes":0,"minutes_delta":-33}
    result=engine.project_player("Player One",rows,"2026-07-01",{"team":"Example","opponent":"Other","home_away":"away","spread":5,"blowout_probability":0.18},injury)
    assert result["projected_minutes"] == 0
    assert result["minutes_p10"] == 0
    assert result["minutes_p90"] == 0
    assert result["injury_status"] == "OUT"


def test_missing_context_is_neutral():
    rows=sample_rows([25,26,24,25,26],starter=False)
    result=engine.project_player("Player One",rows,"2026-07-01",{"team":"Example","opponent":None,"home_away":None,"spread":None,"blowout_probability":None},None)
    assert result["adjustments"]["blowout"] == 0
    assert result["adjustments"]["home_away"] == 0
    assert 0 <= result["confidence"] <= 100


def main():
    tests=[
        ("stable starter projection",test_stable_starter_projection),
        ("out player forced to zero",test_out_player_is_zero),
        ("missing context remains neutral",test_missing_context_is_neutral),
    ]
    results=[]
    for name,fn in tests:
        try:
            fn();results.append({"test":name,"passed":True,"detail":""})
        except Exception as exc:
            results.append({"test":name,"passed":False,"detail":str(exc)})
    failed=[row for row in results if not row["passed"]]
    report={"status":"green" if not failed else "red","summary":{"tests":len(results),"passed":len(results)-len(failed),"failed":len(failed)},"tests":results}
    Path("data/dashboard").mkdir(parents=True,exist_ok=True)
    import json
    json.dump(report,open("data/dashboard/wnba_minutes_projection_v2_acceptance.json","w"),indent=2)
    print(report["summary"])
    if failed:raise SystemExit(1)


if __name__=="__main__":main()
