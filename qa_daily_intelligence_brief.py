"""QA for Sprint 17 Commit 5 daily intelligence brief."""
from __future__ import annotations

import json
from pathlib import Path

BRIEF=Path('data/forecast/daily_intelligence_brief.json')
MARKDOWN=Path('data/forecast/daily_intelligence_brief.md')
DASH=Path('data/dashboard/wnba_daily_intelligence_brief.json')
LIVE=Path('data/forecast/live_opportunity_scanner.json')


def load(path: Path):
    if not path.exists():
        raise AssertionError(f'Missing output: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def run():
    brief=load(BRIEF); dash=load(DASH); live=load(LIVE)
    assert MARKDOWN.exists() and MARKDOWN.read_text(encoding='utf-8').strip(), 'Markdown brief is empty'
    assert brief==dash, 'Dashboard and canonical brief differ'
    assert brief.get('status') in {'READY','STANDBY'}
    markets=live.get('markets',[])
    assert brief.get('slate',{}).get('live_markets')==len(markets)
    if markets:
        assert brief['status']=='READY'
    else:
        assert brief['status']=='STANDBY'
        assert brief.get('top_opportunities')==[]
        assert brief.get('market_alerts')==[]
    ids=[]
    for section in ('top_opportunities','market_alerts'):
        for row in brief.get(section,[]):
            assert row.get('market_id'), f'{section} row missing market_id'
            score=row.get('score')
            if score is not None:
                assert 0 <= float(score) <= 100
            assert row.get('action') in {'BET_NOW','WATCH','PASS'}
            ids.append((section,row['market_id']))
    top_ids=[x.get('market_id') for x in brief.get('top_opportunities',[])]
    assert len(top_ids)==len(set(top_ids)), 'Duplicate top opportunity IDs'
    assert isinstance(brief.get('headline'),str) and brief['headline'].strip()
    assert isinstance(brief.get('warning'),str) and brief['warning'].strip()
    summary={
        'status':'PASS',
        'brief_status':brief['status'],
        'live_markets':len(markets),
        'top_opportunities':len(brief.get('top_opportunities',[])),
        'market_alerts':len(brief.get('market_alerts',[])),
    }
    print(json.dumps(summary,indent=2))
    return summary


if __name__=='__main__':
    run()
