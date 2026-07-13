"""Acceptance tests for model explainability."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_model_explainability as engine

def test_feature_direction():
    assert engine.feature('A',1,'x','s')['direction']=='positive'
    assert engine.feature('A',-1,'x','s')['direction']=='negative'
    assert engine.feature('A',0,'x','s')['direction']=='neutral'

def test_explanation_contract():
    row={'rank':1,'player':'A','game':'X vs Y','market_type':'PLAYER_PROP','stat':'PTS','side':'OVER','line':20.5,'odds':-110,'sportsbook':'Book','decision':'BET','top_play_score':88,'expected_value_per_unit':.12,'hit_probability':.63,'confidence':87,'data_quality_status':'complete','injury_status':'ACTIVE','ranking_components':{'volatility_penalty':0}}
    u={'distributions':{'PTS':{'mean':24}},'matchup_adjustments_pct':{'PTS':6}}
    m={'projected_minutes':35,'samples':{'l5_average':32},'rest_days':2,'context':{'blowout_probability':.1}}
    a={'streak_score':88,'l10_pct':.8}
    result=engine.explanation(row,u,m,a)
    assert result['projection']==24
    assert result['biggest_positives']
    assert isinstance(result['biggest_risks'],list)
    assert all(f['source'] for f in result['features'])
    assert result['summary']

def test_missing_is_explicit():
    row={'player':'A','stat':'PTS','side':'OVER','line':20.5,'expected_value_per_unit':None,'hit_probability':None,'confidence':None,'data_quality_status':'unknown'}
    result=engine.explanation(row,None,None,None)
    assert 'Expected value' in result['unavailable_inputs']
    assert 'Hit probability' in result['unavailable_inputs']

def main():
    tests=[('feature direction',test_feature_direction),('explanation contract',test_explanation_contract),('missing input policy',test_missing_is_explicit)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[r for r in results if not r['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_model_explainability_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
