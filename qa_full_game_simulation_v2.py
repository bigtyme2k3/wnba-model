"""Acceptance tests for Full-Game Simulation Engine v2."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_full_game_simulation_v2 as engine

def player(name,team,pts):
    d={s:{'mean':1,'p10':0,'p90':3} for s in engine.PLAYER_STATS}
    d['MIN']={'mean':34,'p10':30,'p90':38};d['PTS']={'mean':pts,'p10':pts-6,'p90':pts+7};d['REB']={'mean':6,'p10':3,'p90':10};d['AST']={'mean':5,'p10':2,'p90':9}
    return {'player':name,'team':team,'distributions':d}

def test_game_contract():
    game={'game':'Away @ Home','projected_total':160,'projected_margin':4}
    players=[player('A','Away',20),player('B','Away',15),player('C','Home',22),player('D','Home',16)]
    top=[{'player':'A','game':'Away @ Home','stat':'PTS','side':'OVER','line':18.5},{'player':'C','game':'Away @ Home','stat':'PTS','side':'OVER','line':20.5}]
    r=engine.build_game(game,players,top)
    assert r['simulation_count']==10000
    assert r['score_distribution']['total_mean']>100
    assert 0<=r['score_distribution']['overtime_probability']<=1
    assert len(r['players'])==4
    for pair in r['direct_cross_player_pairs']:
        assert pair['calculation_method']=='DIRECT_FULL_GAME_SIMULATION'
        assert 0<=pair['joint_probability']<=1

def test_deterministic():
    game={'game':'Away @ Home','projected_total':160,'projected_margin':4};players=[player('A','Away',20),player('C','Home',22)]
    a=engine.build_game(game,players,[]);b=engine.build_game(game,players,[])
    assert a['score_distribution']==b['score_distribution']

def main():
    tests=[('game simulation contract',test_game_contract),('deterministic game simulation',test_deterministic)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[x for x in results if not x['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_full_game_simulation_v2_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
