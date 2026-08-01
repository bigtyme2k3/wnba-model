"""Build V5 Sprint 21 learning intelligence from verified ALT outcomes."""
from __future__ import annotations
import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE=Path('data/history/wnba_alt_streak_history.jsonl')
OUTPUTS=[Path('data/warehouse/wnba_v5_model_intelligence.json'),Path('data/dashboard/wnba_v5_model_intelligence.json')]
FINAL={'WIN','LOSS','PUSH','VOID'}

def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def rows()->list[dict[str,Any]]:
    out=[]
    if ARCHIVE.exists():
        for line in ARCHIVE.open(encoding='utf-8'):
            try:
                r=json.loads(line)
                if isinstance(r,dict) and str(r.get('outcome','')).upper() in FINAL:out.append(r)
            except Exception:pass
    return out

def group(data:list[dict[str,Any]],key:str,min_n:int=10)->list[dict[str,Any]]:
    buckets=defaultdict(list)
    for r in data:buckets[str(r.get(key) or 'Unknown')].append(r)
    result=[]
    for name,items in buckets.items():
        wins=sum(str(r.get('outcome')).upper()=='WIN' for r in items);losses=sum(str(r.get('outcome')).upper()=='LOSS' for r in items)
        decisions=wins+losses;pnl=sum(num(r.get('profit_loss')) or 0 for r in items)
        result.append({'group':name,'sample':len(items),'decisions':decisions,'wins':wins,'losses':losses,'hit_rate':round(wins/decisions,4) if decisions else None,'profit_loss_units':round(pnl,4),'roi':round(pnl/decisions,4) if decisions else None,'reliable':decisions>=min_n})
    return sorted(result,key=lambda x:((x['roi'] is not None),x['roi'] or -999,x['decisions']),reverse=True)

def score_band(r:dict[str,Any])->str:
    s=num(r.get('streak_score'))
    if s is None:return 'Unknown'
    if s>=75:return '75+'
    if s>=70:return '70-74.9'
    if s>=60:return '60-69.9'
    return 'Below 60'

def main()->None:
    data=rows()
    for r in data:r['_score_band']=score_band(r)
    wins=sum(str(r.get('outcome')).upper()=='WIN' for r in data);losses=sum(str(r.get('outcome')).upper()=='LOSS' for r in data)
    decisions=wins+losses;pnl=sum(num(r.get('profit_loss')) or 0 for r in data)
    dimensions={k:group(data,k) for k in ('stat','side','streak_action','streak_grade','_score_band','player','game')}
    reliable=[x|{'dimension':d} for d,items in dimensions.items() for x in items if x['reliable'] and x['decisions']>=20]
    best=sorted(reliable,key=lambda x:x['roi'] if x['roi'] is not None else -999,reverse=True)[:8]
    worst=sorted(reliable,key=lambda x:x['roi'] if x['roi'] is not None else 999)[:8]
    recs=[]
    for x in worst[:4]:
        if (x['roi'] or 0)<0:recs.append(f"Review or restrict {x['dimension']}={x['group']}: ROI {100*x['roi']:.1f}% across {x['decisions']} decisions.")
    for x in best[:4]:
        if (x['roi'] or 0)>0:recs.append(f"Preserve and validate {x['dimension']}={x['group']}: ROI {100*x['roi']:.1f}% across {x['decisions']} decisions.")
    health='HEALTHY' if decisions>=500 and pnl>0 else 'MONITOR' if decisions>=100 else 'COLLECTING'
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'version':'V5','sprint':21,'status':'ok','health':{'status':health,'graded_decisions':decisions},'summary':{'graded':len(data),'wins':wins,'losses':losses,'hit_rate':round(wins/decisions,4) if decisions else None,'profit_loss_units':round(pnl,4),'roi':round(pnl/decisions,4) if decisions else None,'pending_excluded':True},'daily_summary':f"Sprint 21 evaluated {decisions} verified decisions. Overall hit rate is {100*wins/decisions:.1f}% and ROI is {100*pnl/decisions:.1f}%." if decisions else 'No verified decisions available.','recommendations':recs,'learning_notes':[f"Best reliable segment: {best[0]['dimension']}={best[0]['group']}" if best else 'No reliable positive segment yet.',f"Weakest reliable segment: {worst[0]['dimension']}={worst[0]['group']}" if worst else 'No reliable negative segment yet.'],'best_segments':best,'weakest_segments':worst,'diagnostics':dimensions,'policy':{'verified_final_outcomes_only':True,'minimum_reliable_sample':10,'minimum_action_sample':20,'no_causal_claims':True}}
    for p in OUTPUTS:
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))
if __name__=='__main__':main()
