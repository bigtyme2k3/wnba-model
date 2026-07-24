from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DASH=Path('data/dashboard');WARE=Path('data/warehouse')
OUTS=[DASH/'wnba_final_qa.json',WARE/'wnba_final_qa.json']

def load(path:Path,default:Any):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def list_rows(payload:Any,*keys:str):
    if isinstance(payload,list):return payload
    if not isinstance(payload,dict):return []
    for key in keys:
        value=payload.get(key)
        if isinstance(value,list):return value
    return []

def duplicate_count(rows:list[dict[str,Any]],fields:tuple[str,...])->int:
    seen=set();dupes=0
    for row in rows:
        if not isinstance(row,dict):continue
        key=tuple(str(row.get(f) or '').strip().lower() for f in fields)
        if key in seen:dupes+=1
        else:seen.add(key)
    return dupes

def build()->dict[str,Any]:
    readiness=load(DASH/'wnba_pipeline_readiness.json',{})
    edges=load(DASH/'wnba_daily_edges.json',{})
    ensemble=load(DASH/'wnba_ensemble_intelligence.json',{})
    sims=load(DASH/'wnba_monte_carlo_scenarios.json',{})
    lineage=load(DASH/'wnba_data_lineage.json',{})
    streaks=load(DASH/'wnba_alt_streaks.json',{})
    edge_rows=list_rows(edges,'top_edges')
    ens_rows=list_rows(ensemble,'ranked_edges')
    sim_rows=list_rows(sims,'ranked_simulations','all_simulations')
    streak_rows=list_rows(streaks,'rows','streaks')
    checks={
      'readiness_report_present':bool(readiness),
      'dashboard_exists':Path('docs/index.html').exists(),
      'adaptive_report_present':(DASH/'wnba_adaptive_confidence.json').exists(),
      'ensemble_output_present':(DASH/'wnba_ensemble_intelligence.json').exists(),
      'simulation_output_present':(DASH/'wnba_monte_carlo_scenarios.json').exists(),
      'no_duplicate_edges':duplicate_count(edge_rows,('player','market','side','line','sportsbook'))==0,
      'no_duplicate_ensemble':duplicate_count(ens_rows,('player','market','side','line','sportsbook'))==0,
      'no_duplicate_simulations':duplicate_count(sim_rows,('player','market','side','line','sportsbook'))==0,
      'ensemble_not_ahead_of_edges':len(ens_rows)<=len(edge_rows) if edge_rows else len(ens_rows)==0,
      'simulations_not_ahead_of_ensemble':len(sim_rows)<=len(ens_rows) if ens_rows else len(sim_rows)==0,
      'lineage_matches_ensemble':int((lineage.get('summary') or {}).get('lineage_records') or 0)==len(ens_rows),
    }
    live=readiness.get('status')=='READY'
    if live:
        checks['live_edges_available']=len(edge_rows)>0
        checks['live_ensemble_available']=len(ens_rows)>0
        checks['live_simulations_available']=len(sim_rows)>0
    failed=[k for k,v in checks.items() if not v]
    status='PASS' if not failed else 'ATTENTION' if readiness.get('status')!='READY' and all(not k.startswith('live_') for k in failed) else 'FAIL'
    report={'sprint':11,'phase':'final-qa','generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':status,'readiness_status':readiness.get('status'),'checks':checks,'failed_checks':failed,'counts':{'daily_edges':len(edge_rows),'ensemble':len(ens_rows),'simulations':len(sim_rows),'alt_streaks':len(streak_rows)},'green_light':status=='PASS' and readiness.get('status')=='READY'}
    for path in OUTS:path.parent.mkdir(parents=True,exist_ok=True);json.dump(report,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    print(json.dumps(report,indent=2));return report

if __name__=='__main__':build()
