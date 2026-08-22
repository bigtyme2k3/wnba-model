from __future__ import annotations

import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HISTORY=Path('data/history/wnba_model_history.jsonl')
OUT=Path('data/dashboard/wnba_v5_player_prop_action_audit.json')
MODEL='sprint19_player_props_v5_m02_action_v2'
GRADED={'WIN','LOSS','PUSH','VOID'}


def sf(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None

def read_rows():
    out=[]
    if not HISTORY.exists(): return out
    for line in HISTORY.read_text(encoding='utf-8').splitlines():
        try:
            r=json.loads(line)
            if isinstance(r,dict):out.append(r)
        except Exception:pass
    return out

def action(r):
    a=str(r.get('final_action') or r.get('action') or '').upper()
    if a in {'BET','LEAN','WATCH','PASS'}:return a
    return 'WATCH' if str(r.get('signal') or r.get('recommendation') or '').upper() in {'OVER','UNDER'} else 'PASS'

def summary(rows):
    wins=sum(r.get('outcome')=='WIN' for r in rows); losses=sum(r.get('outcome')=='LOSS' for r in rows)
    pushes=sum(r.get('outcome')=='PUSH' for r in rows); voids=sum(r.get('outcome')=='VOID' for r in rows)
    decisions=wins+losses
    return {'rows':len(rows),'wins':wins,'losses':losses,'pushes':pushes,'voids':voids,'decisions':decisions,'hit_rate':round(wins/decisions,4) if decisions else None}

def price_bucket(r):
    o=sf(r.get('american_odds'))
    if o is None:return 'UNKNOWN'
    if o>=150:return '+150+'
    if o>=100:return '+100-149'
    if o>=-129:return '-100--129'
    if o>=-199:return '-130--199'
    return '-200+'

def confidence_bucket(r):
    x=sf(r.get('confidence'))
    if x is None:return 'UNKNOWN'
    if x>=80:return '80+'
    if x>=70:return '70-79.9'
    if x>=60:return '60-69.9'
    if x>=50:return '50-59.9'
    return '<50'

def edge_bucket(r):
    x=abs(sf(r.get('edge')) or 0.0)
    if x>=4:return '4.0+'
    if x>=3:return '3.0-3.99'
    if x>=2:return '2.0-2.99'
    if x>=1:return '1.0-1.99'
    if x>=0.5:return '0.5-0.99'
    return '<0.5'

def group(rows,key_fn):
    d=defaultdict(list)
    for r in rows:d[str(key_fn(r) or 'UNKNOWN')].append(r)
    return [{'group':k,**summary(v)} for k,v in sorted(d.items())]

def segment(rows, dimensions):
    d=defaultdict(list)
    for r in rows:
        key=tuple(str(fn(r) or 'UNKNOWN') for _,fn in dimensions)
        d[key].append(r)
    out=[]
    for key,v in d.items():
        item={name:value for (name,_),value in zip(dimensions,key)}
        item.update(summary(v));out.append(item)
    return out

def main():
    all_rows=read_rows()
    rows=[r for r in all_rows if str(r.get('model_version') or '')==MODEL and r.get('outcome') in GRADED and str(r.get('signal') or r.get('recommendation') or '').upper() in {'OVER','UNDER'} and str(r.get('result_scope') or '')!='QUARANTINED']
    by_action=group(rows,action)
    amap={x['group']:x for x in by_action}
    bet_hr=(amap.get('BET') or {}).get('hit_rate')
    watch=[r for r in rows if action(r)=='WATCH']
    watch_dims=[('stat',lambda r:r.get('stat')),('side',lambda r:r.get('signal') or r.get('recommendation')),('confidence',confidence_bucket),('edge',edge_bucket),('price',price_bucket)]
    candidates=[]
    for dims in [watch_dims[:1],watch_dims[1:2],watch_dims[2:3],watch_dims[3:4],watch_dims[4:5],watch_dims[:2],watch_dims[2:4],watch_dims[:4]]:
        for s in segment(watch,dims):
            hr=s.get('hit_rate');n=s.get('decisions') or 0
            if n>=25 and hr is not None:
                s['lift_vs_bet']=round(hr-bet_hr,4) if bet_hr is not None else None
                s['candidate_for_shadow_promotion']=bool((bet_hr is None or hr>=bet_hr+0.08) and hr>=0.55)
                s['dimensions']=[name for name,_ in dims]
                candidates.append(s)
    candidates.sort(key=lambda s:(not s['candidate_for_shadow_promotion'],-(s.get('decisions') or 0),-(s.get('hit_rate') or 0)))
    payload={
      'version':'V5','module':'PLAYER_PROP_ACTION_AUDIT','generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'model_version':MODEL,'research_only':True,'production_mutation':False,
      'graded_directional_rows':len(rows),'by_action':by_action,
      'watch_share_pct':round(100*len(watch)/len(rows),1) if rows else None,
      'watch_analysis':{
        'by_stat':group(watch,lambda r:r.get('stat')),
        'by_side':group(watch,lambda r:r.get('signal') or r.get('recommendation')),
        'by_confidence':group(watch,confidence_bucket),
        'by_edge':group(watch,edge_bucket),
        'by_price':group(watch,price_bucket),
        'candidate_segments':candidates[:60],
        'shadow_promotion_candidates':[x for x in candidates if x['candidate_for_shadow_promotion']][:20],
      },
      'diagnosis':{
        'bet_hit_rate':bet_hr,
        'watch_hit_rate':(amap.get('WATCH') or {}).get('hit_rate'),
        'watch_beats_bet':bool(bet_hr is not None and (amap.get('WATCH') or {}).get('hit_rate') is not None and (amap.get('WATCH') or {}).get('hit_rate')>bet_hr),
        'policy_issue_suspected':bool(bet_hr is not None and (amap.get('WATCH') or {}).get('hit_rate') is not None and (amap.get('WATCH') or {}).get('hit_rate')>=bet_hr+0.08),
      },
      'policy':'Research audit only. Do not promote WATCH rows from retrospective hit rate alone; use identified segments as prospective shadow rules and require chronological confirmation.'
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2,allow_nan=False))

if __name__=='__main__':main()
