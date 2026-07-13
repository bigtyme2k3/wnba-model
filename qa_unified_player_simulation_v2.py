"""Acceptance tests for Unified Player Simulation Engine v2."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_unified_player_simulation_v2 as engine

def rows():
    out=[]
    for i in range(14):
        out.append({'player':'Player One','team':'Example','position':'G','minutes':34+(i%3-1),'game_date':f'2026-06-{30-i:02d}','game_id':str(i),'scoring':{'total_pts':20+(i%5),'three_pm':2+(i%3)},'boxscore':{'reb':5+(i%3),'oreb':1,'dreb':4+(i%3),'ast':7+(i%4),'stl':1+(i%2),'blk':i%2,'tov':2+(i%3)}})
    return out

def minute():return {'player':'Player One','team':'Example','opponent':'Other','projected_minutes':35,'minutes_p10':31,'minutes_p90':38,'confidence':88,'data_quality_status':'complete','injury_status':'ACTIVE'}

def test_distribution_contract():
    r=engine.project('Player One',rows(),minute(),{})
    assert r['simulation_count']==10000
    for stat in engine.ALL_STATS:
        d=r['distributions'][stat]
        assert 0<=d['p10']<=d['p25']<=d['p50']<=d['p75']<=d['p90']
    assert r['distributions']['PRA']['mean']>=r['distributions']['PR']['mean']
    assert r['distributions']['PRA']['mean']>=r['distributions']['PA']['mean']
    assert r['distributions']['PRA']['mean']>=r['distributions']['RA']['mean']

def test_market_and_pairs():
    r=engine.project('Player One',rows(),minute(),{})
    props=[{'player':'Player One','stat':'PTS','line':21.5,'best_over_price':-110,'best_under_price':-110,'best_over_book':'A','best_under_book':'B'},{'player':'Player One','stat':'AST','line':6.5,'best_over_price':-105,'best_under_price':-115,'best_over_book':'A','best_under_book':'B'}]
    markets=engine.compare(r,props)
    assert len(markets)==4
    for m in markets:
        assert 0<=m['hit_probability']<=1
        assert m['recommended_units']<=1
        assert m['action'] in {'BET','LEAN','PASS'}
    pairs=engine.pair_ideas(r,markets)
    for p in pairs:
        assert 0<=p['joint_probability']<=1
        assert p['classification'] in {'POSITIVE_CORRELATION','NEGATIVE_CORRELATION','NEUTRAL'}

def test_deterministic():
    a=engine.project('Player One',rows(),minute(),{})
    b=engine.project('Player One',rows(),minute(),{})
    assert a['distributions']==b['distributions']
    assert a['correlations']==b['correlations']

def main():
    tests=[('distribution contract',test_distribution_contract),('market and pair bounds',test_market_and_pairs),('deterministic simulation',test_deterministic)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[x for x in results if not x['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_unified_player_simulation_v2_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
