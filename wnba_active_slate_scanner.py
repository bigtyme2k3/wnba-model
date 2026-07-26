"""Sprint 17 Commit 4.1: restrict opportunity scanning to the actionable slate.

Only markets starting in the next 48 hours are eligible. Historical, stale and
far-future records are counted for diagnostics but never recommended.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PRED=Path('data/forecast/closing_line_predictions.json')
OPPS=Path('data/forecast/opportunity_scanner.json')
OUT=Path('data/forecast/live_opportunity_scanner.json')
DASH=Path('data/dashboard/wnba_live_scanner_summary.json')
HORIZON_HOURS=48
STALE_MINUTES=360


def now_dt() -> datetime:
    return datetime.now(timezone.utc)

def iso(dt: datetime) -> str:
    return dt.isoformat().replace('+00:00','Z')

def parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except ValueError:
        return None

def load(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw=json.loads(path.read_text(encoding='utf-8'))
    value=raw.get(key,[]) if isinstance(raw,dict) else []
    return value if isinstance(value,list) else []

def latest_time(row: dict[str, Any]) -> datetime | None:
    return parse(row.get('current_time_utc') or row.get('captured_at_utc') or row.get('snapshot_time_utc'))

def freshness(age_minutes: float | None) -> float:
    if age_minutes is None:
        return 0.0
    return round(max(0.0, min(100.0, 100.0-(age_minutes/STALE_MINUTES)*100.0)),2)

def classify(commence: datetime | None, updated: datetime | None, current: datetime) -> str:
    if commence is None or commence <= current:
        return 'HISTORICAL'
    if commence > current + timedelta(hours=HORIZON_HOURS):
        return 'UPCOMING'
    age=(current-updated).total_seconds()/60 if updated else None
    if age is None or age > STALE_MINUTES:
        return 'STALE'
    return 'LIVE_SLATE'

def run() -> dict[str, Any]:
    current=now_dt()
    predictions=load(PRED,'predictions') or load(PRED,'forecasts')
    ranked={x.get('market_id'):x for x in load(OPPS,'opportunities') if x.get('market_id')}

    # Keep the newest record if duplicate market IDs ever appear upstream.
    latest: dict[str, dict[str, Any]]={}
    for p in predictions:
        mid=p.get('market_id')
        if not mid:
            continue
        prior=latest.get(mid)
        if prior is None or (latest_time(p) or datetime.min.replace(tzinfo=timezone.utc)) > (latest_time(prior) or datetime.min.replace(tzinfo=timezone.utc)):
            latest[mid]=p

    status_counts={k:0 for k in ['LIVE_SLATE','UPCOMING','STALE','HISTORICAL']}
    live=[]
    for mid,p in latest.items():
        commence=parse(p.get('commence_time_utc'))
        updated=latest_time(p)
        status=classify(commence,updated,current)
        status_counts[status]+=1
        if status!='LIVE_SLATE':
            continue
        base=dict(ranked.get(mid,{}) or p)
        age=round(max(0.0,(current-updated).total_seconds()/60),2) if updated else None
        base.update({
            'market_id':mid,
            'market_status':status,
            'last_update_utc':iso(updated) if updated else None,
            'minutes_since_update':age,
            'freshness_score':freshness(age),
            'hours_to_tip':round((commence-current).total_seconds()/3600,3) if commence else None,
        })
        # Freshness is an operational requirement, so degrade otherwise strong records.
        raw_score=float(base.get('opportunity_score') or 0)
        adjusted=round(raw_score*(0.75+0.25*base['freshness_score']/100),2)
        base['live_opportunity_score']=adjusted
        if adjusted < 55:
            base['scanner_recommendation']='PASS'
        live.append(base)

    live.sort(key=lambda x:(-float(x.get('live_opportunity_score') or 0),x.get('commence_time_utc') or '',x.get('market_id') or ''))
    generated=iso(current)
    OUT.parent.mkdir(parents=True,exist_ok=True); DASH.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({
        'generated_at_utc':generated,
        'horizon_hours':HORIZON_HOURS,
        'stale_after_minutes':STALE_MINUTES,
        'status_counts':status_counts,
        'markets':live,
        'warning':'Live-slate research ranking only; not a guarantee or instruction to wager.'
    },indent=2),encoding='utf-8')
    recs={k:sum(x.get('scanner_recommendation')==k for x in live) for k in ['BET_NOW','WATCH','PASS']}
    tiers={k:sum(x.get('tier')==k for x in live) for k in ['ELITE','STRONG','WATCH','LOW','AVOID']}
    summary={
        'generated_at_utc':generated,
        'status':'READY' if live else 'STANDBY',
        'horizon_hours':HORIZON_HOURS,
        'markets_evaluated':len(latest),
        'live_markets':len(live),
        'events':len({x.get('event_id') for x in live if x.get('event_id')}),
        'status_counts':status_counts,
        'tier_counts':tiers,
        'recommendation_counts':recs,
        'top_opportunities':live[:25],
        'warning':'STANDBY is expected when no fresh markets start within the next 48 hours.'
    }
    DASH.write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return summary

if __name__=='__main__':
    run()
