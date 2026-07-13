"""Acceptance tests for the immutable Model Picks Ledger."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_model_picks_ledger as engine

def test_pick_identity_is_stable():
    row={'player':'A','game':'X @ Y','stat':'PTS','side':'OVER','line':20.5,'sportsbook':'Book'}
    assert engine.pick_id('2026-07-13',row)==engine.pick_id('2026-07-13',dict(row))

def test_flat_unit_math():
    rows=[{'outcome':'WIN','profit_loss':.9091,'line_clv':1,'absolute_projection_error':2},{'outcome':'LOSS','profit_loss':-1,'line_clv':-1,'absolute_projection_error':1},{'outcome':'PUSH','profit_loss':0,'line_clv':0,'absolute_projection_error':0}]
    s=engine.summarize(rows)
    assert s['graded']==3
    assert s['wins']==1 and s['losses']==1 and s['pushes']==1
    assert s['win_rate']==.5
    assert s['positive_clv_rate']==round(1/3,4)
    assert s['mae']==1.0

def test_confidence_tiers():
    assert engine.confidence_tier(95)=='90-100'
    assert engine.confidence_tier(85)=='80-89'
    assert engine.confidence_tier(75)=='70-79'
    assert engine.confidence_tier(60)=='Below 70'

def test_aggregate_contract():
    rows=[{'stat':'PTS','outcome':'WIN','profit_loss':1},{'stat':'PTS','outcome':'LOSS','profit_loss':-1},{'stat':'REB','outcome':'PENDING'}]
    out=engine.aggregate(rows,'stat')
    assert {r['group'] for r in out}=={'PTS','REB'}
    pts=next(r for r in out if r['group']=='PTS')
    assert pts['picks']==2 and pts['graded']==2

def main():
    tests=[('stable pick identity',test_pick_identity_is_stable),('flat unit math',test_flat_unit_math),('confidence tiers',test_confidence_tiers),('group aggregation',test_aggregate_contract)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[r for r in results if not r['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True)
    json.dump(report,open('data/dashboard/wnba_model_picks_ledger_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
