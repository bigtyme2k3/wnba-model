"""Acceptance tests for projection performance."""
from __future__ import annotations
import json
from pathlib import Path
import wnba_projection_performance as engine

def test_summary_math():
    rows=[{'actual':10,'absolute_error':2,'bias':2,'inside_p10_p90':True,'outcome':'WIN','profit_loss':.91},{'actual':8,'absolute_error':1,'bias':-1,'inside_p10_p90':False,'outcome':'LOSS','profit_loss':-1}]
    s=engine.summarize(rows)
    assert s['graded']==2 and s['mae']==1.5
    assert s['bias']==.5
    assert s['p10_p90_coverage']==.5
    assert s['hit_rate']==.5

def test_threshold_guards():
    stats=[{'group':'PTS','graded':49,'bias':1,'p10_p90_coverage':.8},{'group':'REB','graded':100,'bias':-.5,'p10_p90_coverage':.7},{'group':'AST','graded':200,'bias':.2,'p10_p90_coverage':.81}]
    r=engine.recommendations(stats)
    assert r[0]['status']=='LOCKED'
    assert r[1]['status']=='WEIGHT_REVIEW'
    assert r[2]['status']=='CALIBRATION_ELIGIBLE'

def test_actual_stat_identity():
    row={'minutes':33,'scoring':{'total_pts':20,'three_pm':3},'boxscore':{'reb':7,'oreb':2,'dreb':5,'ast':6,'stl':2,'blk':1,'tov':4}}
    a=engine.actuals(row)
    assert a['PRA']==33 and a['PR']==27 and a['PA']==26 and a['RA']==13
    assert a['OREB']+a['DREB']==a['REB']

def main():
    tests=[('summary math',test_summary_math),('threshold guards',test_threshold_guards),('actual stat identity',test_actual_stat_identity)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[x for x in results if not x['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_projection_performance_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
