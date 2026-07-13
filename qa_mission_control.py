"""Acceptance tests for WNBA Mission Control."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import wnba_mission_control as engine

def test_count_helpers():
    assert engine.count_value([1,2,3])==3
    assert engine.count_value({'a':1})==1
    assert engine.count_value(4)==4

def test_alt_zero_is_detected():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'alt.json'
        path.write_text(json.dumps({'generated_at_utc':'2099-01-01T00:00:00+00:00','target_date':'2026-07-13','summary':{'source_props':214,'standard_rows':61,'alternate_rows':0}}),encoding='utf-8')
        check={'id':'alt_props','name':'ALT Player Props','path':str(path),'keys':['summary.alternate_rows'],'minimum':1,'critical':False,'retry':True}
        row=engine.evaluate(check,'2026-07-13',0)
        assert row['status']=='YELLOW'
        assert row['action']=='RETRY_SOURCE'
        assert any('0 alternate lines' in issue for issue in row['issues'])

def test_critical_missing_blocks():
    check={'id':'games','name':'Games','path':'definitely_missing_file.json','keys':['games'],'minimum':1,'critical':True}
    row=engine.evaluate(check,'2026-07-13',0)
    assert row['status']=='RED'
    assert row['action']=='BLOCK_PUBLISH'

def test_retry_cap():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'alt.json'
        path.write_text(json.dumps({'target_date':'2026-07-13','summary':{'source_props':100,'alternate_rows':0}}),encoding='utf-8')
        check={'id':'alt_props','name':'ALT Player Props','path':str(path),'keys':['summary.alternate_rows'],'minimum':1,'critical':False,'retry':True}
        row=engine.evaluate(check,'2026-07-13',2)
        assert row['action']=='PUBLISH_DEGRADED'

def main():
    tests=[('count helpers',test_count_helpers),('ALT zero detection',test_alt_zero_is_detected),('critical failure blocks',test_critical_missing_blocks),('retry cap',test_retry_cap)]
    results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as exc:results.append({'test':name,'passed':False,'detail':str(exc)})
    failed=[row for row in results if not row['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True)
    json.dump(report,open('data/dashboard/wnba_mission_control_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
