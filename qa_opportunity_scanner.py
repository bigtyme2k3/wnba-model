"""QA for Sprint 17 Commit 4 opportunity scanner."""
from __future__ import annotations
import json
from pathlib import Path

OUT=Path('data/forecast/opportunity_scanner.json')
DASH=Path('data/dashboard/wnba_opportunity_scanner_summary.json')
TIERS={'ELITE','STRONG','WATCH','LOW','AVOID'}
RECS={'BET_NOW','WATCH','PASS'}

def load(path):
    if not path.exists(): raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding='utf-8'))

def run():
    out=load(OUT); summary=load(DASH)
    rows=out.get('opportunities',[])
    assert isinstance(rows,list)
    ids=[x.get('market_id') for x in rows]
    assert len(ids)==len(set(ids)), 'duplicate market ids'
    for r in rows:
        assert r.get('tier') in TIERS
        assert r.get('scanner_recommendation') in RECS
        score=float(r.get('opportunity_score'))
        assert 0<=score<=100
        comps=r.get('components') or {}
        for value in comps.values(): assert 0<=float(value)<=100
        if r.get('scanner_recommendation')=='BET_NOW':
            assert r.get('forecast_status')=='MODEL_READY'
            assert r.get('entry_action')=='BET_NOW'
            assert score>=80
        if r.get('entry_action')=='PASS': assert score<=39
        if r.get('forecast_status')!='MODEL_READY': assert score<=49
    assert summary.get('markets_scanned')==len(rows)
    tier_counts={k:sum(x.get('tier')==k for x in rows) for k in TIERS}
    rec_counts={k:sum(x.get('scanner_recommendation')==k for x in rows) for k in RECS}
    assert summary.get('tier_counts')==tier_counts
    assert summary.get('recommendation_counts')==rec_counts
    expected='READY' if rows else 'STANDBY'
    assert summary.get('status')==expected
    result={'status':'PASS','markets':len(rows),'bet_now':rec_counts['BET_NOW'],'watch':rec_counts['WATCH'],'pass':rec_counts['PASS'],'elite':tier_counts['ELITE'],'strong':tier_counts['STRONG']}
    print(json.dumps(result,indent=2)); return result

if __name__=='__main__': run()
