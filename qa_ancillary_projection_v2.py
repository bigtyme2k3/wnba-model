"""Acceptance tests for ancillary Projection Engine v2."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_ancillary_projection_v2 as engine

def rows():
    out=[]
    for i in range(12):
        out.append({'player':'Player One','team':'Example','position':'G','minutes':34+(i%3-1),'game_date':f'2026-06-{30-i:02d}','game_id':str(i),'scoring':{'three_pm':2+(i%3)},'boxscore':{'stl':1+(i%2),'blk':i%2,'tov':2+(i%3)}})
    return out

def minute():return {'player':'Player One','team':'Example','opponent':'Other','projected_minutes':35,'minutes_p10':31,'minutes_p90':38,'confidence':88,'data_quality_status':'complete','injury_status':'ACTIVE'}

def test_distributions():
    r=engine.project('Player One',rows(),minute(),{})
    for stat in engine.STATS:
        d=r['projections'][stat];assert 0<=d['p10']<=d['p25']<=d['p50']<=d['p75']<=d['p90']
    assert r['simulation_count']==10000

def test_market_bounds():
    r=engine.project('Player One',rows(),minute(),{})
    m=engine.compare(r,[{'player':'Player One','stat':'3PM','line':2.5,'best_over_price':-110,'best_under_price':-110,'best_over_book':'A','best_under_book':'B'}])
    assert len(m)==2
    for x in m:
        assert 0<=x['hit_probability']<=1
        assert x['recommended_units']<=1
        assert x['action'] in {'BET','LEAN','PASS'}

def test_deterministic():
    a=engine.project('Player One',rows(),minute(),{})
    b=engine.project('Player One',rows(),minute(),{})
    assert a['projected_3pm']==b['projected_3pm']
    assert a['projections']['STL']==b['projections']['STL']

def main():
    tests=[('ordered distributions',test_distributions),('market bounds',test_market_bounds),('deterministic simulation',test_deterministic)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[x for x in results if not x['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_ancillary_projection_v2_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
