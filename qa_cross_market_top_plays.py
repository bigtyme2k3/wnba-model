"""Acceptance checks for Cross-Market Top Plays."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_cross_market_top_plays as engine

def test_scoring_bounds():
    row={'expected_value_per_unit':.12,'hit_probability':.62,'confidence':88,'data_quality_status':'complete','odds':-110,'recommended_units':.8,'injury_status':'ACTIVE'}
    out=engine.score_candidate(row,{'positive_rate':.6,'average_line_clv':.2})
    assert 0<=out['top_play_score']<=100
    assert out['decision'] in {'BET','LEAN','WATCH','PASS'}
    assert out['risk_level'] in {'Low','Medium','High'}

def test_dedupe_keeps_best_ev():
    rows=[{'player':'A','game':'G','stat':'PTS','side':'OVER','line':20.5,'expected_value_per_unit':.05},{'player':'A','game':'G','stat':'PTS','side':'OVER','line':20.5,'expected_value_per_unit':.11}]
    out=engine.dedupe(rows)
    assert len(out)==1 and out[0]['expected_value_per_unit']==.11

def test_allocation_caps():
    rows=[]
    for i in range(10):
        rows.append({'decision':'BET','raw_recommended_units':1,'player':f'P{i}','game':'Same Game' if i<5 else f'G{i}','top_play_score':90})
    out=engine.allocate(rows)
    total=sum(x.get('recommended_units_final',0) for x in out)
    same=sum(x.get('recommended_units_final',0) for x in out if x['game']=='Same Game')
    assert total<=engine.MAX_TOTAL_UNITS+1e-9
    assert same<=engine.MAX_GAME_UNITS+1e-9

def main():
    tests=[('scoring bounded',test_scoring_bounds),('dedupe best EV',test_dedupe_keeps_best_ev),('allocation caps',test_allocation_caps)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[x for x in results if not x['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True)
    json.dump(report,open('data/dashboard/wnba_cross_market_top_plays_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
