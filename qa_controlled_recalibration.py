"""Acceptance tests for controlled recalibration."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_controlled_recalibration as engine

def rows(n,bias=1.0):
    out=[]
    for i in range(n):
        actual=10+(i%3);mean=actual+bias
        out.append({'date':f'2026-06-{(i%28)+1:02d}','captured_at_utc':str(i),'mean':mean,'actual':actual,'p10':mean-3,'p90':mean+3})
    return out

def test_locked_threshold():
    p=engine.proposal_for('PTS',rows(99))
    assert p['status']=='LOCKED'
    assert p['production_applied'] is False

def test_bounded_proposal():
    p=engine.proposal_for('PTS',rows(140,2.0))
    assert .95<=p['proposed']['mean_multiplier']<=1.05
    assert .95<=p['proposed']['variance_multiplier']<=1.05
    assert p['status'] in {'TESTING','APPROVED','REJECTED'}

def test_variance_locked_before_200():
    p=engine.proposal_for('REB',rows(150,.5))
    assert p['proposed']['variance_multiplier']==1.0

def main():
    tests=[('sample threshold lock',test_locked_threshold),('bounded proposal',test_bounded_proposal),('variance threshold lock',test_variance_locked_before_200)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[r for r in results if not r['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_controlled_recalibration_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
