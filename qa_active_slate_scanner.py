"""QA for Sprint 17 Commit 4.1 active-slate scanner."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT=Path('data/forecast/live_opportunity_scanner.json')
DASH=Path('data/dashboard/wnba_live_scanner_summary.json')


def parse(v):
    return datetime.fromisoformat(str(v).replace('Z','+00:00'))

def load(path):
    if not path.exists():
        raise AssertionError(f'Missing output: {path}')
    return json.loads(path.read_text(encoding='utf-8'))

def run():
    payload=load(OUT); summary=load(DASH)
    generated=parse(payload['generated_at_utc'])
    horizon=generated+timedelta(hours=float(payload.get('horizon_hours',48)))
    markets=payload.get('markets',[])
    ids=set()
    for row in markets:
        mid=row.get('market_id')
        assert mid and mid not in ids, f'Duplicate market_id: {mid}'
        ids.add(mid)
        assert row.get('market_status')=='LIVE_SLATE'
        commence=parse(row['commence_time_utc'])
        assert generated < commence <= horizon, f'Out-of-window market: {mid}'
        age=row.get('minutes_since_update')
        assert age is not None and 0 <= float(age) <= float(payload.get('stale_after_minutes',360))
        fresh=float(row.get('freshness_score',-1))
        assert 0 <= fresh <= 100
        assert row.get('scanner_recommendation') in {'BET_NOW','WATCH','PASS'}
    assert summary.get('live_markets')==len(markets)
    assert sum(summary.get('recommendation_counts',{}).values())==len(markets)
    assert sum(summary.get('tier_counts',{}).values())==len(markets)
    expected='READY' if markets else 'STANDBY'
    assert summary.get('status')==expected
    print(json.dumps({'status':'PASS','live_markets':len(markets),'events':summary.get('events',0),'scanner_status':expected},indent=2))

if __name__=='__main__':
    run()
