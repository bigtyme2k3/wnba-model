"""Live market coverage scanner with separate visibility and action horizons.

Fresh markets up to 96 hours before tip are preserved for validation. Only markets
inside 48 hours are actionable. Historical and stale records remain diagnostic only.
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
VISIBILITY_HOURS=96
ACTION_HOURS=48
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
    return round(max(0.0,min(100.0,100.0-(age_minutes/STALE_MINUTES)*100.0)),2)

def classify(commence: datetime | None, updated: datetime | None, current: datetime) -> str:
    if commence is None or commence <= current:
        return 'HISTORICAL'
    if commence > current + timedelta(hours=VISIBILITY_HOURS):
        return 'UPCOMING'
    age=(current-updated).total_seconds()/60 if updated else None
    if age is None or age > STALE_MINUTES:
        return 'STALE'
    if commence <= current + timedelta(hours=ACTION_HOURS):
        return 'ACTIONABLE'
    return 'EARLY_MARKET'

def run() -> dict[str, Any]:
    current=now_dt()
    predictions=load(PRED,'predictions') or load(PRED,'forecasts')
    ranked={x.get('market_id'):x for x in load(OPPS,'opportunities') if x.get('market_id')}

    latest: dict[str,dict[str,Any]]={}
    for p in predictions:
        mid=p.get('market_id')
        if not mid:
            continue
        prior=latest.get(mid)
        if prior is None or (latest_time(p) or datetime.min.replace(tzinfo=timezone.utc)) > (latest_time(prior) or datetime.min.replace(tzinfo=timezone.utc)):
            latest[mid]=p

    status_counts={k:0 for k in ['ACTIONABLE','EARLY_MARKET','UPCOMING','STALE','HISTORICAL']}
    visible=[]
    for mid,p in latest.items():
        commence=parse(p.get('commence_time_utc'))
        updated=latest_time(p)
        status=classify(commence,updated,current)
        status_counts[status]+=1
        if status not in {'ACTIONABLE','EARLY_MARKET'}:
            continue
        base=dict(ranked.get(mid,{}) or p)
        age=round(max(0.0,(current-updated).total_seconds()/60),2) if updated else None
        base.update({
            'market_id':mid,
            'market_status':status,
            'actionable':status=='ACTIONABLE',
            'validation_capture':True,
            'last_update_utc':iso(updated) if updated else None,
            'minutes_since_update':age,
            'freshness_score':freshness(age),
            'hours_to_tip':round((commence-current).total_seconds()/3600,3) if commence else None,
        })
        raw_score=float(base.get('opportunity_score') or 0)
        adjusted=round(raw_score*(0.75+0.25*base['freshness_score']/100),2)
        base['live_opportunity_score']=adjusted
        if status=='EARLY_MARKET':
            base['scanner_recommendation']='WATCH'
            base['action_note']='Early market captured for validation; not yet inside the 48-hour action window.'
        elif adjusted < 55:
            base['scanner_recommendation']='PASS'
        visible.append(base)

    visible.sort(key=lambda x:(0 if x.get('actionable') else 1,-float(x.get('live_opportunity_score') or 0),x.get('commence_time_utc') or '',x.get('market_id') or ''))
    actionable=[x for x in visible if x.get('actionable')]
    early=[x for x in visible if not x.get('actionable')]
    generated=iso(current)
    OUT.parent.mkdir(parents=True,exist_ok=True);DASH.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({
        'generated_at_utc':generated,
        'visibility_horizon_hours':VISIBILITY_HOURS,
        'action_horizon_hours':ACTION_HOURS,
        'stale_after_minutes':STALE_MINUTES,
        'status_counts':status_counts,
        'markets':visible,
        'warning':'Early markets are captured for research validation; only ACTIONABLE markets are eligible for immediate opportunity decisions.'
    },indent=2),encoding='utf-8')
    recs={k:sum(x.get('scanner_recommendation')==k for x in actionable) for k in ['BET_NOW','WATCH','PASS']}
    tiers={k:sum(x.get('tier')==k for x in actionable) for k in ['ELITE','STRONG','WATCH','LOW','AVOID']}
    summary={
        'generated_at_utc':generated,
        'status':'READY' if visible else 'STANDBY',
        'visibility_horizon_hours':VISIBILITY_HOURS,
        'action_horizon_hours':ACTION_HOURS,
        'markets_evaluated':len(latest),
        'markets_available':len(visible),
        'live_markets':len(actionable),
        'early_markets':len(early),
        'events':len({x.get('event_id') for x in visible if x.get('event_id')}),
        'actionable_events':len({x.get('event_id') for x in actionable if x.get('event_id')}),
        'status_counts':status_counts,
        'tier_counts':tiers,
        'recommendation_counts':recs,
        'top_opportunities':actionable[:25],
        'early_market_captures':early[:25],
        'warning':'Markets up to 96 hours are visible and captured; only those within 48 hours are actionable.'
    }
    DASH.write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return summary

if __name__=='__main__':
    run()
