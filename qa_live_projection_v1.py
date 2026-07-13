"""Acceptance tests for Live Projection Engine v1."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_live_projection_v1 as engine

def prior():
    d={s:{'mean':5,'p10':2,'p90':9} for s in engine.STATS}
    d['MIN']={'mean':34,'p10':30,'p90':38};d['PTS']={'mean':20,'p10':13,'p90':29};d['REB']={'mean':6,'p10':3,'p90':10};d['AST']={'mean':5,'p10':2,'p90':9}
    return {'distributions':d}

def row(fouls=2):
    return {'player':'Player One','team':'Team','minutes':18,'fouls':fouls,'PTS':11,'REB':3,'AST':4,'3PM':2,'STL':1,'BLK':0,'TOV':2,'PRA':18,'PR':14,'PA':15,'RA':7}

def test_weight_progression():
    early=engine.project_player(row(),prior(),.20,32)
    late=engine.project_player(row(),prior(),.80,8)
    assert early['prior_weight']>late['prior_weight']
    assert early['live_weight']<late['live_weight']

def test_foul_penalty():
    clean=engine.project_player(row(2),prior(),.5,20)
    trouble=engine.project_player(row(5),prior(),.5,20)
    assert trouble['projected_final_minutes']<clean['projected_final_minutes']
    assert trouble['foul_trouble'] is True

def test_distribution_contract():
    result=engine.project_player(row(),prior(),.5,20)
    for stat in engine.STATS:
        d=result['distributions'][stat]
        assert 0<=d['p10']<=d['p50']<=d['p90']

def main():
    tests=[('prior decays with progress',test_weight_progression),('foul trouble lowers minutes',test_foul_penalty),('ordered live distributions',test_distribution_contract)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[r for r in results if not r['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_live_projection_v1_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
