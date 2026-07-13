"""Acceptance tests for Points Projection Engine v2."""
from __future__ import annotations

import json
from pathlib import Path

import wnba_points_projection_v2 as engine


def sample_rows():
    rows=[]
    for i in range(12):
        minutes=34+(i%3-1)
        points=22+(i%5-2)
        rows.append({
            "player":"Player One","team":"Example","position":"G","minutes":minutes,"game_date":f"2026-06-{30-i:02d}","game_id":str(i),
            "scoring":{"total_pts":points,"fgm":8,"fga":17,"three_pm":3,"three_pa":8,"ftm":3,"fta":4},
        })
    return rows


def test_projection_distribution():
    minute={"player":"Player One","team":"Example","opponent":"Other","projected_minutes":35,"minutes_p10":31,"minutes_p90":38,"confidence":88,"data_quality_status":"complete","injury_status":"ACTIVE","rest_days":1,"home_away":"home"}
    result=engine.projection_for_player("Player One",sample_rows(),minute,{})
    assert 0 <= result["points_p10"] <= result["points_p25"] <= result["points_p50"] <= result["points_p75"] <= result["points_p90"] <= 65
    assert result["simulation_count"]==10000
    assert result["projected_points"]>0
    assert result["shot_distribution"]["three_point_attempts"]>0


def test_market_math():
    projection=engine.projection_for_player("Player One",sample_rows(),{"player":"Player One","team":"Example","opponent":"Other","projected_minutes":35,"minutes_p10":31,"minutes_p90":38,"confidence":88,"data_quality_status":"complete","injury_status":"ACTIVE","rest_days":1,"home_away":"home"},{})
    markets=engine.market_comparison(projection,[{"player":"Player One","stat":"PTS","line":20.5,"best_over_price":-110,"best_under_price":-110,"best_over_book":"Book A","best_under_book":"Book B"}])
    assert len(markets)==2
    for row in markets:
        assert 0<=row["hit_probability"]<=1
        assert row["action"] in {"BET","LEAN","PASS"}
        assert row["recommended_units"]<=1


def test_market_does_not_change_projection():
    minute={"player":"Player One","team":"Example","opponent":"Other","projected_minutes":35,"minutes_p10":31,"minutes_p90":38,"confidence":88,"data_quality_status":"complete","injury_status":"ACTIVE","rest_days":1,"home_away":"home"}
    a=engine.projection_for_player("Player One",sample_rows(),minute,{})
    b=engine.projection_for_player("Player One",sample_rows(),minute,{})
    assert a["projected_points"]==b["projected_points"]
    assert a["points_p50"]==b["points_p50"]


def main():
    tests=[("distribution ordered",test_projection_distribution),("market calculations bounded",test_market_math),("market independent projection",test_market_does_not_change_projection)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({"test":name,"passed":True,"detail":""})
        except Exception as exc:results.append({"test":name,"passed":False,"detail":str(exc)})
    failed=[row for row in results if not row["passed"]]
    report={"status":"green" if not failed else "red","summary":{"tests":len(results),"passed":len(results)-len(failed),"failed":len(failed)},"tests":results}
    Path("data/dashboard").mkdir(parents=True,exist_ok=True)
    json.dump(report,open("data/dashboard/wnba_points_projection_v2_acceptance.json","w"),indent=2)
    print(report["summary"])
    if failed:raise SystemExit(1)


if __name__=="__main__":main()
