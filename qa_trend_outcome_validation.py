"""QA for Sprint 16 Commit 2 outcome validation."""
from __future__ import annotations
import json
from pathlib import Path

OUT=Path('data/trends/outcome_validated_trends.json')
DETAIL=Path('data/trends/trend_outcome_records.json')
DASH=Path('data/dashboard/wnba_trend_outcome_validation_summary.json')
VALID={'VALIDATED','REJECTED','INSUFFICIENT'}


def load(path):
    if not path.exists(): raise AssertionError(f'missing {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    out, detail, dash = load(OUT), load(DETAIL), load(DASH)
    trends=out.get('trends',[]); records=detail.get('records',[])
    assert isinstance(trends,list) and isinstance(records,list)
    assert dash.get('status') in {'READY','STANDBY'}
    ids=[x.get('trend_id') for x in trends]
    assert len(ids)==len(set(ids)), 'duplicate trend ids'
    for row in trends:
        assert row.get('status') in VALID
        assert row.get('validation_basis')=='VERIFIED_OUTCOMES_CHRONOLOGICAL_HOLDOUT'
        for key in ('full_sample','development_70pct','holdout_30pct'):
            m=row[key]
            assert m['records']>=0 and m['wins']>=0 and m['losses']>=0 and m['pushes']>=0
            assert m['wins']+m['losses']+m['pushes']==m['records']
            if m['hit_rate'] is not None: assert 0<=m['hit_rate']<=1
            lo,hi=m['hit_rate_95ci']
            if lo is not None: assert 0<=lo<=hi<=1
        if row['status']=='VALIDATED':
            h=row['holdout_30pct']
            assert h['records']>=10
            assert (h['roi_per_bet'] or 0)>0
            assert (h['hit_rate_95ci'][0] or 0)>0.5
    assert dash['discovered_trends']==len(trends)
    assert dash['validated']==sum(x['status']=='VALIDATED' for x in trends)
    assert dash['rejected']==sum(x['status']=='REJECTED' for x in trends)
    assert dash['insufficient']==sum(x['status']=='INSUFFICIENT' for x in trends)
    trend_ids=set(ids)
    assert all(r.get('trend_id') in trend_ids for r in records)
    print(json.dumps({'status':'PASS','trends':len(trends),'records':len(records),'validated':dash['validated'],'rejected':dash['rejected'],'insufficient':dash['insufficient']},indent=2))

if __name__=='__main__': main()
