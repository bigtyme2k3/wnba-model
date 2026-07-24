from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DASH=Path('data/dashboard');WARE=Path('data/warehouse')
OUTS=[DASH/'wnba_data_lineage.json',WARE/'wnba_data_lineage.json']

def load(path:Path,default:Any):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def rows(payload:Any,*keys:str):
    if not isinstance(payload,dict):return []
    for key in keys:
        value=payload.get(key)
        if isinstance(value,list):return value
    return []

def key(row:dict[str,Any])->str:
    return '|'.join(str(row.get(k) or '').strip().lower() for k in ('player','market','stat','side','line','sportsbook','book'))

def build()->dict[str,Any]:
    edges=load(DASH/'wnba_daily_edges.json',{})
    ensemble=load(DASH/'wnba_ensemble_intelligence.json',{})
    sims=load(DASH/'wnba_monte_carlo_scenarios.json',{})
    edge_rows=rows(edges,'top_edges')
    ens_rows=rows(ensemble,'ranked_edges')
    sim_rows=rows(sims,'ranked_simulations','all_simulations')
    emap={key(r):r for r in edge_rows if isinstance(r,dict)}
    smap={key(r):r for r in sim_rows if isinstance(r,dict)}
    records=[]
    for rank,row in enumerate(ens_rows,1):
        if not isinstance(row,dict):continue
        k=key(row);edge=emap.get(k,{});sim=smap.get(k,{})
        records.append({
          'rank':rank,'candidate_key':k,'player':row.get('player'),'market':row.get('market'),'side':row.get('side'),'line':row.get('line'),'sportsbook':row.get('sportsbook'),
          'stages':{
            'daily_edge':{'present':bool(edge),'score':edge.get('edge_score'),'confidence':edge.get('confidence')},
            'adaptive_confidence':{'present':row.get('adaptive_probability') is not None,'probability':row.get('adaptive_probability'),'extrapolated':row.get('calibration_extrapolated')},
            'ensemble':{'present':True,'score':row.get('ensemble_score'),'grade':row.get('grade')},
            'simulation':{'present':bool(sim),'probability':sim.get('simulation_probability'),'ev_percent':sim.get('expected_value_percent')},
          },
          'source_files':['data/dashboard/wnba_daily_edges.json','data/dashboard/wnba_adaptive_confidence.json','data/dashboard/wnba_ensemble_intelligence.json','data/dashboard/wnba_monte_carlo_scenarios.json']
        })
    report={'sprint':11,'phase':'data-lineage','generated_at_utc':datetime.now(timezone.utc).isoformat(),'summary':{'daily_edges':len(edge_rows),'ensemble_candidates':len(ens_rows),'simulations':len(sim_rows),'lineage_records':len(records),'simulation_coverage':round(sum(1 for r in records if r['stages']['simulation']['present'])/len(records),4) if records else None},'records':records[:100]}
    for path in OUTS:path.parent.mkdir(parents=True,exist_ok=True);json.dump(report,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    print(json.dumps(report['summary'],indent=2));return report

if __name__=='__main__':build()
