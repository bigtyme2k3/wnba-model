"""WNBA V4 Mission Control and publication reliability gate.

Validates slate date, freshness, row counts, alternate-line availability, model
outputs, QA, explainability, CLV capture, and dashboard publication. Critical
failures block publishing; optional-source failures publish a clearly labeled
degraded report and request bounded retries.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

OUTS=[Path('data/warehouse/wnba_mission_control.json'),Path('data/dashboard/wnba_mission_control.json')]

CHECKS=[
 {'id':'games','name':'Games','path':'data/dashboard/wnba_master.json','keys':['games'],'minimum':1,'critical':True},
 {'id':'player_props','name':'Player Props','path':'data/dashboard/wnba_master.json','keys':['props'],'minimum':1,'critical':True},
 {'id':'alt_props','name':'ALT Player Props','path':'data/dashboard/wnba_alt_streaks.json','keys':['summary.alternate_rows'],'minimum':1,'critical':False,'retry':True},
 {'id':'minutes','name':'Minutes Projection','path':'data/dashboard/wnba_minutes_projection_v2.json','keys':['projections'],'minimum':1,'critical':True},
 {'id':'unified','name':'Unified Simulation','path':'data/dashboard/wnba_unified_player_simulation_v2.json','keys':['players'],'minimum':1,'critical':True},
 {'id':'top_plays','name':'Top Plays','path':'data/dashboard/wnba_cross_market_top_plays.json','keys':['top_plays'],'minimum':1,'critical':False},
 {'id':'explainability','name':'Explainability','path':'data/dashboard/wnba_model_explainability.json','keys':['explanations'],'minimum':1,'critical':False},
 {'id':'clv_snapshot','name':'CLV Snapshot','path':'data/history/wnba_market_observations.jsonl','keys':[],'minimum':1,'critical':False},
 {'id':'qa','name':'V4 QA','path':'data/dashboard/wnba_v4_status.json','keys':['modules'],'minimum':1,'critical':True},
 {'id':'dashboard','name':'Dashboard Publish','path':'docs/index.html','keys':[],'minimum':1,'critical':True},
]

def load(path:Path,default:Any)->Any:
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def dump(path:Path,payload:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8') as handle:json.dump(payload,handle,indent=2,allow_nan=False)

def nested(payload:Any,key:str)->Any:
    value=payload
    for part in key.split('.'):
        if not isinstance(value,dict):return None
        value=value.get(part)
    return value

def count_value(value:Any)->int:
    if isinstance(value,list):return len(value)
    if isinstance(value,dict):return len(value)
    if isinstance(value,bool):return int(value)
    try:return int(value or 0)
    except Exception:return 0

def file_rows(path:Path,keys:list[str])->int:
    if not path.exists():return 0
    if path.suffix=='.json':
        payload=load(path,{})
        counts=[count_value(nested(payload,key)) for key in keys]
        return max(counts or [1 if payload else 0])
    if path.suffix=='.jsonl':return sum(1 for line in path.read_text(encoding='utf-8').splitlines() if line.strip())
    return 1 if path.stat().st_size>0 else 0

def generated_at(path:Path)->str|None:
    if path.suffix!='.json':return datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat() if path.exists() else None
    payload=load(path,{})
    return payload.get('generated_at_utc') or payload.get('updated_at_utc')

def target_date(path:Path)->str|None:
    payload=load(path,{}) if path.suffix=='.json' else {}
    return payload.get('target_date') or payload.get('slate_date')

def minutes_old(timestamp:str|None)->float|None:
    if not timestamp:return None
    try:
        dt=datetime.fromisoformat(str(timestamp).replace('Z','+00:00'))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return max(0,(datetime.now(timezone.utc)-dt).total_seconds()/60)
    except Exception:return None

def evaluate(check:dict[str,Any],target:str,retry_count:int)->dict[str,Any]:
    path=Path(check['path']);exists=path.exists();rows=file_rows(path,check.get('keys',[]));stamp=generated_at(path);age=minutes_old(stamp);file_target=target_date(path)
    issues=[];warnings=[]
    if not exists:issues.append('Output file missing')
    elif rows<check['minimum']:issues.append(f"Expected at least {check['minimum']} row; found {rows}")
    if file_target and file_target!=target:issues.append(f'Stale slate date {file_target}; expected {target}')
    if age is not None and age>1440:warnings.append(f'Output is {age/60:.1f} hours old')
    if check['id']=='alt_props' and exists:
        payload=load(path,{});summary=payload.get('summary',{})
        source_props=count_value(summary.get('source_props'));standard=count_value(summary.get('standard_rows'));alternate=count_value(summary.get('alternate_rows'))
        if source_props>0 and alternate==0:
            issues.append(f'Prop source loaded {source_props} markets but produced 0 alternate lines')
            warnings.append(f'Standard streak rows remain available: {standard}')
    if check['id']=='qa' and exists:
        payload=load(path,{});blockers=count_value((payload.get('summary') or {}).get('release_blockers'))
        overall=(payload.get('qa') or {}).get('overall_status')
        if blockers>0 or overall=='red':issues.append(f'QA reports {blockers} release blockers and status {overall}')
    status='RED' if issues and check['critical'] else 'YELLOW' if issues or warnings else 'GREEN'
    action='BLOCK_PUBLISH' if status=='RED' else 'RETRY_SOURCE' if issues and check.get('retry') and retry_count<2 else 'PUBLISH_DEGRADED' if issues else 'NONE'
    return {'id':check['id'],'component':check['name'],'status':status,'critical':check['critical'],'path':check['path'],'rows':rows,'target_date':file_target,'generated_at_utc':stamp,'age_minutes':round(age,1) if age is not None else None,'retry_count':retry_count if check.get('retry') else 0,'action':action,'issues':issues,'warnings':warnings}

def build(target:str,retry_count:int=0)->dict[str,Any]:
    checks=[evaluate(check,target,retry_count) for check in CHECKS]
    critical=[c for c in checks if c['status']=='RED'];degraded=[c for c in checks if c['status']=='YELLOW'];retry=[c for c in checks if c['action']=='RETRY_SOURCE']
    publication='BLOCKED' if critical else 'DEGRADED' if degraded else 'READY'
    alt=next(c for c in checks if c['id']=='alt_props')
    message='All required pipelines are healthy.' if publication=='READY' else 'Critical data failed; affected recommendations are withheld.' if publication=='BLOCKED' else 'Report published with clear warnings; unavailable optional sections are withheld.'
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','publication_status':publication,'publication_message':message,'summary':{'components':len(checks),'green':sum(c['status']=='GREEN' for c in checks),'yellow':sum(c['status']=='YELLOW' for c in checks),'red':sum(c['status']=='RED' for c in checks),'retry_required':len(retry),'release_blockers':len(critical),'warnings':sum(len(c['warnings']) for c in checks)},'alt_props':{'available':alt['status']=='GREEN','status':alt['status'],'retry_count':alt['retry_count'],'action':alt['action'],'message':'Alternate player props loaded.' if alt['status']=='GREEN' else 'Alternate player props are unavailable. Standard props remain visible; ALT recommendations are withheld.'},'checks':checks,'retry_plan':[{'component':c['component'],'attempt':retry_count+1,'maximum_attempts':2,'command_chain':['python wnba_alt_streaks.py --date '+target,'python wnba_alt_streaks_correctness.py','python wnba_alt_streaks_warehouse_upgrade.py --date '+target,'python wnba_alt_streaks_opponent_context.py','python wnba_alt_streaks_position_context.py','python wnba_alt_streaks_pace_minutes_context.py','python wnba_alt_streak_confidence.py --date '+target]} for c in retry],'policy':{'critical_failures_block_publication':True,'optional_failures_publish_degraded':True,'maximum_automatic_retries':2,'silent_empty_sections_allowed':False,'affected_recommendations_withheld':True}}
    for path in OUTS:dump(path,payload)
    print('Mission Control:',payload['publication_status'],payload['summary'])
    return payload

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--date',default=str(date.today()));parser.add_argument('--retry-count',type=int,default=0);args=parser.parse_args();build(args.date,args.retry_count)
if __name__=='__main__':main()
