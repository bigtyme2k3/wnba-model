"""Acceptance tests for Parlay Optimizer v2."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_parlay_optimizer_v2 as engine

def test_same_player_direct_joint():
    unified={'players':[{'player':'A','team':'X','opponent':'Y','confidence':88,'markets':[{'stat':'PTS','side':'OVER','line':20.5,'odds':-110,'sportsbook':'Book','hit_probability':.62},{'stat':'AST','side':'OVER','line':5.5,'odds':-105,'sportsbook':'Book','hit_probability':.58}],'same_player_pairs':[{'legs':[{'stat':'PTS','side':'OVER','line':20.5},{'stat':'AST','side':'OVER','line':5.5}],'joint_probability':.40,'correlation_lift':.0404}]}]}
    rows=engine.build_same_player(unified)
    assert len(rows)==1
    assert rows[0]['calculation_method']=='DIRECT_JOINT_SIMULATION'
    assert rows[0]['joint_probability']==.4
    assert rows[0]['risk_level'] in {'Low','Medium','High'}

def test_cross_player_is_labeled_estimate():
    top={'portfolio':[{'player':'A','game':'G1','stat':'PTS','side':'OVER','line':20.5,'odds':-110,'sportsbook':'B','hit_probability':.62,'confidence':88,'decision':'BET'},{'player':'B','game':'G2','stat':'REB','side':'OVER','line':6.5,'odds':-105,'sportsbook':'B','hit_probability':.59,'confidence':82,'decision':'LEAN'}]}
    rows=engine.build_cross_player(top)
    assert len(rows)>=1
    assert rows[0]['calculation_method']=='CONSERVATIVE_INDEPENDENCE_ESTIMATE'
    assert rows[0]['risk_level']=='High'
    assert rows[0].get('warning')

def test_duplicate_and_contradiction():
    a={'player':'A','game':'G','stat':'PTS','side':'OVER','line':20.5}
    b=dict(a)
    c={**a,'side':'UNDER'}
    assert engine.duplicate(a,b)
    assert engine.contradictory(a,c)

def main():
    tests=[('same-player direct joint',test_same_player_direct_joint),('cross-player estimate labeling',test_cross_player_is_labeled_estimate),('duplicate and contradiction rules',test_duplicate_and_contradiction)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[x for x in results if not x['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_parlay_optimizer_v2_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
