from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DASH=Path('data/dashboard'); WARE=Path('data/warehouse')
OUTS=[DASH/'wnba_pipeline_readiness.json',WARE/'wnba_pipeline_readiness.json']

def load(path:Path,default:Any):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def count_rows(payload:Any,*keys:str)->int:
    if isinstance(payload,list):return len(payload)
    if not isinstance(payload,dict):return 0
    for key in keys:
        value=payload.get(key)
        if isinstance(value,list):return len(value)
        if isinstance(value,dict):
            for child in ('rows','records','markets','props','games','top_edges','ranked_edges','all_simulations'):
                if isinstance(value.get(child),list):return len(value[child])
    for key in ('rows','records','markets','props','games','top_edges','ranked_edges','all_simulations'):
        if isinstance(payload.get(key),list):return len(payload[key])
    return 0

def build(target_date:str|None=None)->dict[str,Any]:
    master=load(DASH/'wnba_master.json',{})
    sportsbook=load(DASH/'wnba_sportsbook_consensus.json',{})
    edges=load(DASH/'wnba_daily_edges.json',{})
    adaptive=load(DASH/'wnba_adaptive_confidence.json',{})
    logs=load(WARE/'wnba_player_game_logs.json',{})
    games=[g for g in master.get('games',[]) if isinstance(g,dict)] if isinstance(master,dict) else []
    today=[g for g in games if g.get('bucket')=='today']
    props=master.get('props',[]) if isinstance(master,dict) and isinstance(master.get('props'),list) else []
    markets=count_rows(sportsbook,'all_consensus','markets')
    player_logs=count_rows(logs,'records')
    calibration_records=int((adaptive.get('summary') or {}).get('calibration_records') or 0) if isinstance(adaptive,dict) else 0
    checks={
      'regular_season_slate':len(today)>0,
      'current_props':len(props)>0,
      'sportsbook_markets':markets>0,
      'player_history':player_logs>=100,
      'adaptive_calibration':calibration_records>=300,
      'dashboard_writable':Path('docs/index.html').exists(),
    }
    blockers=[name for name,ok in checks.items() if not ok]
    live_inputs=checks['regular_season_slate'] and checks['current_props'] and checks['sportsbook_markets']
    core_health=checks['player_history'] and checks['adaptive_calibration'] and checks['dashboard_writable']
    status='READY' if live_inputs and core_health else 'WAIT' if core_health else 'BLOCKED'
    report={
      'sprint':11,'phase':'restart-readiness','generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'target_date':target_date or edges.get('target_date') or master.get('target_date'),'status':status,
      'counts':{'today_games':len(today),'props':len(props),'sportsbook_markets':markets,'player_logs':player_logs,'calibration_records':calibration_records},
      'checks':checks,'blockers':blockers,
      'reason':'Pipeline ready for live model execution.' if status=='READY' else 'Awaiting live regular-season market data.' if status=='WAIT' else 'Core data or dashboard dependency is unavailable.',
      'preserve_last_valid_reports':status!='READY'
    }
    for path in OUTS:path.parent.mkdir(parents=True,exist_ok=True);json.dump(report,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    print(json.dumps(report,indent=2));return report

if __name__=='__main__':build()
