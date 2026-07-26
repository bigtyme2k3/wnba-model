from __future__ import annotations
import json
from pathlib import Path
T=Path('data/trends/automated_trends.json'); C=Path('data/trends/trend_candidates.json'); S=Path('data/dashboard/wnba_trend_discovery_summary.json')
def load(p):
    if not p.exists(): raise SystemExit(f'missing {p}')
    return json.loads(p.read_text(encoding='utf-8'))
def main():
    t=load(T).get('trends',[]); c=load(C).get('candidates',[]); s=load(S)
    assert isinstance(t,list) and isinstance(c,list)
    seen=set()
    for r in t:
        key=json.dumps(r.get('dimensions',{}),sort_keys=True)
        assert key not in seen; seen.add(key)
        assert r['sample_size']>=20
        assert .52<=r['positive_clv_rate']<=1
        assert 0<=r['trend_score']<=100
        assert r['grade'] in {'A','B','C','RESEARCH'}
        assert r['validation_basis']=='CLV_ONLY'
    assert s['qualified_trends']==len(t)
    assert s['research_candidates']>=len(c)
    assert s['status'] in {'READY','STANDBY'}
    print(json.dumps({'status':'PASS','observations':s['observations_analyzed'],'groups_tested':s['groups_tested'],'qualified_trends':len(t),'candidates_written':len(c)},indent=2))
if __name__=='__main__': main()
