"""QA for Sprint 17 Commit 3.1 sportsbook timing normalization."""
from __future__ import annotations
import json
from pathlib import Path

OUT=Path('data/forecast/sportsbook_leader_normalized.json')
DASH=Path('data/dashboard/wnba_sportsbook_leader_normalized_summary.json')
VALID={'SYNCED','ISOLATED','UNRESOLVED'}
BOOKS={'draftkings','fanduel'}


def load(path):
    if not path.exists(): raise SystemExit(f'Missing output: {path}')
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    out=load(OUT); dash=load(DASH)
    records=out.get('records',[]); books=out.get('sportsbooks',[]); markets=out.get('markets',[])
    assert isinstance(records,list) and isinstance(books,list) and isinstance(markets,list)
    assert len({(r.get('event_id'),r.get('market'),r.get('outcome_key')) for r in records})==len(records)
    for r in records:
        assert r.get('status') in VALID
        lag=r.get('reaction_lag_minutes')
        if r['status']=='SYNCED':
            assert lag is not None and 0 <= float(lag) <= 360
            assert r.get('same_direction') is True
            assert r.get('similar_magnitude') is True
        else:
            assert lag is None
    assert {b.get('bookmaker') for b in books} <= BOOKS
    for b in books:
        for key in ('synced_lead_rate','synchronization_rate','positive_clv_rate'):
            assert 0 <= float(b.get(key,0)) <= 1
        assert 0 <= float(b.get('normalized_efficiency_score',0)) <= 100
        for key in ('average_synced_lag_minutes','median_synced_lag_minutes'):
            v=b.get(key)
            if v is not None: assert 0 <= float(v) <= 360
    counts={k:sum(1 for r in records if r['status']==k) for k in VALID}
    assert dash.get('comparison_pairs')==len(records)
    assert dash.get('classification_counts')==counts
    assert dash.get('sportsbooks_ranked')==len(books)
    assert dash.get('markets_ranked')==len(markets)
    expected='READY' if records else 'STANDBY'
    assert dash.get('status')==expected
    print(json.dumps({'status':'PASS','pairs':len(records),**{k.lower():v for k,v in counts.items()},'sportsbooks':len(books),'markets':len(markets)},indent=2))

if __name__=='__main__': main()
