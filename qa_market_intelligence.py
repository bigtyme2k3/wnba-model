"""Acceptance tests for market intelligence."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_market_intelligence as engine

def test_line_clv_direction():
    assert engine.line_clv('OVER',20.5,21.5)==1.0
    assert engine.line_clv('UNDER',21.5,20.5)==1.0
    assert engine.line_clv('OVER',22.5,21.5)==-1.0

def test_odds_clv():
    value=engine.odds_clv(-110,-130)
    assert value is not None and value>0

def test_movement_classes():
    assert engine.classify_movement('OVER',20.5,20.5,22.5)=='STEAM_TOWARD_MODEL'
    assert engine.classify_movement('OVER',22.5,22.5,20.5)=='STEAM_AWAY_FROM_MODEL'
    assert engine.classify_movement('OVER',20.5,20.5,20.5)=='STABLE'

def test_aggregate():
    rows=[{'stat':'PTS','line_clv':1,'odds_clv_probability':.02,'outcome':'WIN','profit_loss':.9},{'stat':'PTS','line_clv':-1,'odds_clv_probability':-.01,'outcome':'LOSS','profit_loss':-1}]
    out=engine.aggregate(rows,'stat')[0]
    assert out['count']==2
    assert out['positive_clv_rate']==.5
    assert out['wins']==1 and out['losses']==1

def main():
    tests=[('line CLV side normalization',test_line_clv_direction),('odds CLV direction',test_odds_clv),('movement classification',test_movement_classes),('historical aggregation',test_aggregate)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[r for r in results if not r['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True)
    json.dump(report,open('data/dashboard/wnba_market_intelligence_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
