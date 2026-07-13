"""Acceptance tests for full-game simulation performance."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_full_game_performance as engine

def test_pair_calibration():
    rows=[{'status':'GRADED','predicted_probability':.25,'actual_hit':True},{'status':'GRADED','predicted_probability':.27,'actual_hit':False},{'status':'GRADED','predicted_probability':.45,'actual_hit':True}]
    bands=engine.pair_calibration(rows)
    assert len(bands)==2
    for row in bands:
        assert 0<=row['predicted']<=1
        assert 0<=row['actual']<=1

def test_actual_stat():
    row={'scoring':{'total_pts':20,'three_pm':3},'boxscore':{'reb':7,'ast':6,'stl':2,'blk':1,'tov':4}}
    assert engine.actual_stat(row,'PRA')==33
    assert engine.actual_stat(row,'RA')==13
    assert engine.actual_stat(row,'3PM')==3

def test_team_parser():
    assert engine.teams('Away @ Home')==('Away','Home')
    assert engine.teams('Away vs Home')==('Away','Home')

def main():
    tests=[('pair calibration bands',test_pair_calibration),('actual stat identities',test_actual_stat),('game team parser',test_team_parser)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[r for r in results if not r['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_full_game_performance_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
