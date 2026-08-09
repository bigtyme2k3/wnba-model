"""WNBA V5 Operations Sprint 3 M01 - Current Slate Freshness Guard.

Validates that the ranked opportunity board belongs to the current Eastern Time
WNBA slate before M11 may score it. This module never invents a current slate;
it classifies the repository board as FRESH, EMPTY_CURRENT_SLATE, or STALE_BLOCKED
and publishes machine-readable guard outputs.
"""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RANKINGS = Path('data/warehouse/wnba_opportunity_rankings.json')
OUT = Path('data/dashboard')
OUT_GUARD = OUT/'wnba_v5_s3_m01_freshness.json'
OUT_SLATE = OUT/'wnba_v5_current_slate.json'
OUT_STALE = OUT/'wnba_v5_stale_game_report.json'
OUT_VALID = OUT/'wnba_v5_slate_validation.json'
OUT_HEALTH = OUT/'wnba_v5_schedule_health.json'
ET = ZoneInfo('America/New_York')


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except Exception:
        return {}


def rows_of(p):
    if not isinstance(p, dict): return []
    for key in ('all_ranked','top_opportunities','opportunities','rows'):
        rows=p.get(key)
        if isinstance(rows,list) and rows: return rows
    return []


def clean_date(v):
    s=str(v or '').strip()
    return s[:10] if len(s)>=10 else ''


def game_key(r):
    gid=str(r.get('game_id') or '').strip()
    if gid: return gid
    game=' '.join(str(r.get('game') or '').strip().lower().split())
    date=clean_date(r.get('date'))
    return f'{date}|{game}' if game else ''


def main():
    now_utc=datetime.now(timezone.utc)
    now_et=now_utc.astimezone(ET)
    today=now_et.date().isoformat()
    p=load_json(RANKINGS)
    rows=rows_of(p)
    payload_date=clean_date(p.get('target_date'))
    row_dates=[clean_date(r.get('date')) for r in rows if clean_date(r.get('date'))]
    dates=sorted(set(row_dates + ([payload_date] if payload_date else [])))
    current=[r for r in rows if clean_date(r.get('date') or payload_date)==today]
    stale=[r for r in rows if clean_date(r.get('date') or payload_date) and clean_date(r.get('date') or payload_date)!=today]
    undated=[r for r in rows if not clean_date(r.get('date') or payload_date)]

    keys=[game_key(r) for r in current if game_key(r)]
    counts=Counter(keys)
    # Repeated prop rows for one game are expected; duplicate_game_ids means conflicting
    # canonical rows cannot be inferred here, so we only audit missing/blank identities.
    blank_game_rows=sum(1 for r in current if not game_key(r))
    missing_tipoff=sum(1 for r in current if not (r.get('commence_time') or r.get('start_time') or r.get('tipoff')))

    if not RANKINGS.exists():
        status='BLOCKED_NO_RANKINGS'
    elif not rows:
        status='EMPTY_CURRENT_SLATE' if payload_date in ('',today) else 'STALE_BLOCKED'
    elif stale or undated or not current:
        status='STALE_BLOCKED'
    else:
        status='FRESH'

    allow=status in {'FRESH','EMPTY_CURRENT_SLATE'}
    reason={
      'FRESH':'Ranked board is dated for the current Eastern Time slate.',
      'EMPTY_CURRENT_SLATE':'No ranked opportunities are present for the current slate; safe standby.',
      'STALE_BLOCKED':'Ranked board contains no exclusively current-date slate and must not be scored.',
      'BLOCKED_NO_RANKINGS':'Opportunity rankings file is missing.'
    }[status]

    guard={
      'version':'V5','sprint':'OPERATIONS_SPRINT_3','module':'S3-M01',
      'stage':'CURRENT_SLATE_FRESHNESS_GUARD','status':status,'allow_live_inference':allow,
      'generated_at_utc':now_utc.isoformat(),'current_date_et':today,'ranking_target_date':payload_date or None,
      'board_dates':dates,'ranked_rows':len(rows),'current_rows':len(current),'stale_rows':len(stale),'undated_rows':len(undated),
      'blank_game_identity_rows':blank_game_rows,'missing_tipoff_rows':missing_tipoff,
      'reason':reason,'policy':'M11 may score only when allow_live_inference=true. Historical or stale boards remain research artifacts only.'
    }
    slate={'generated_at_utc':now_utc.isoformat(),'current_date_et':today,'status':status,
           'source':'data/warehouse/wnba_opportunity_rankings.json','rows':current if allow else []}
    stale_report={'generated_at_utc':now_utc.isoformat(),'current_date_et':today,'status':status,
                  'stale_count':len(stale),'undated_count':len(undated),
                  'examples':[{'date':clean_date(r.get('date') or payload_date),'game':r.get('game'),'player':r.get('player')} for r in (stale+undated)[:25]]}
    validation={'generated_at_utc':now_utc.isoformat(),'status':'PASS' if allow else 'BLOCK',
                'checks':{'rankings_file_exists':RANKINGS.exists(),'all_rows_current_or_empty':not stale and not undated,
                          'current_rows_present_or_empty_board':bool(current) or not rows,'game_identity_present':blank_game_rows==0},
                'allow_live_inference':allow}
    health={'generated_at_utc':now_utc.isoformat(),'module':'S3-M01','status':'HEALTHY' if allow else 'BLOCKED_STALE_SLATE',
            'current_date_et':today,'board_date':payload_date or (dates[0] if len(dates)==1 else None),
            'ranked_rows':len(rows),'current_rows':len(current),'stale_rows':len(stale),'next_action':'RUN_M11' if allow else 'REFRESH_CURRENT_OPPORTUNITY_BOARD'}
    OUT.mkdir(parents=True,exist_ok=True)
    for path,obj in ((OUT_GUARD,guard),(OUT_SLATE,slate),(OUT_STALE,stale_report),(OUT_VALID,validation),(OUT_HEALTH,health)):
        path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(guard,indent=2))

if __name__=='__main__': main()
