"""QA for active-slate scanner visibility and action horizons."""
from __future__ import annotations
import json
from datetime import datetime,timedelta
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
    payload=load(OUT);summary=load(DASH)
    generated=parse(payload['generated_at_utc'])
    visibility=generated+timedelta(hours=float(payload.get('visibility_horizon_hours',96)))
    action=generated+timedelta(hours=float(payload.get('action_horizon_hours',48)))
    markets=payload.get('markets',[])
    ids=set();actionable=0;early=0
    for row in markets:
        mid=row.get('market_id')
        assert mid and mid not in ids,f'Duplicate market_id: {mid}'
        ids.add(mid)
        status=row.get('market_status')
        assert status in {'ACTIONABLE','EARLY_MARKET'}
        commence=parse(row['commence_time_utc'])
        assert generated < commence <= visibility,f'Out-of-visibility market: {mid}'
        age=row.get('minutes_since_update')
        assert age is not None and 0 <= float(age) <= float(payload.get('stale_after_minutes',360))
        fresh=float(row.get('freshness_score',-1));assert 0 <= fresh <= 100
        assert row.get('scanner_recommendation') in {'BET_NOW','WATCH','PASS'}
        assert row.get('validation_capture') is True
        if status=='ACTIONABLE':
            actionable+=1
            assert row.get('actionable') is True
            assert commence <= action
        else:
            early+=1
            assert row.get('actionable') is False
            assert action < commence <= visibility
            assert row.get('scanner_recommendation')=='WATCH'
    assert summary.get('markets_available')==len(markets)
    assert summary.get('live_markets')==actionable
    assert summary.get('early_markets')==early
    assert sum(summary.get('recommendation_counts',{}).values())==actionable
    assert sum(summary.get('tier_counts',{}).values())==actionable
    expected='READY' if markets else 'STANDBY'
    assert summary.get('status')==expected
    print(json.dumps({'status':'PASS','markets_available':len(markets),'actionable':actionable,'early_markets':early,'scanner_status':expected},indent=2))

if __name__=='__main__':
    run()
