"""Controlled, reviewable recalibration proposals for Projection Engine v2.

This module never edits production weights. It creates bounded proposals from
projection history, performs a chronological holdout backtest, and marks each
proposal LOCKED, TESTING, APPROVED, or REJECTED. Approval means eligible for
manual review only.
"""
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

HISTORY=Path('data/history/wnba_projection_history.jsonl')
OUTS=[Path('data/warehouse/wnba_controlled_recalibration.json'),Path('data/dashboard/wnba_controlled_recalibration.json')]
PROPOSALS=Path('data/history/wnba_recalibration_proposals.jsonl')
MIN_WEIGHT=100
MIN_VARIANCE=200
MAX_MEAN_SHIFT=.05
MAX_SCALE_SHIFT=.05

def read_jsonl(p:Path)->list[dict[str,Any]]:
    out=[]
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            try:
                r=json.loads(line)
                if isinstance(r,dict):out.append(r)
            except Exception:pass
    return out
def write_jsonl(p:Path,rows:list[dict[str,Any]])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in rows),encoding='utf-8')
def dump(p:Path,x:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True);json.dump(x,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def mae(rows:list[dict[str,Any]],shift:float=0)->float|None:
    vals=[]
    for r in rows:
        mean=num(r.get('mean'));actual=num(r.get('actual'))
        if mean is not None and actual is not None:vals.append(abs(mean*(1+shift)-actual))
    return sum(vals)/len(vals) if vals else None
def coverage(rows:list[dict[str,Any]],scale:float=1)->float|None:
    vals=[]
    for r in rows:
        mean=num(r.get('mean'));p10=num(r.get('p10'));p90=num(r.get('p90'));actual=num(r.get('actual'))
        if None in (mean,p10,p90,actual):continue
        lo=mean-(mean-p10)*scale;hi=mean+(p90-mean)*scale;vals.append(lo<=actual<=hi)
    return sum(vals)/len(vals) if vals else None
def split(rows:list[dict[str,Any]])->tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    rows=sorted(rows,key=lambda r:(str(r.get('date') or ''),str(r.get('captured_at_utc') or '')))
    cut=max(1,int(len(rows)*.75));return rows[:cut],rows[cut:]
def proposal_for(stat:str,rows:list[dict[str,Any]])->dict[str,Any]:
    n=len(rows);train,holdout=split(rows);base_mae=mae(holdout);base_cov=coverage(holdout)
    bias=sum((num(r.get('mean')) or 0)-(num(r.get('actual')) or 0) for r in train)/len(train) if train else 0
    avg_mean=sum(num(r.get('mean')) or 0 for r in train)/len(train) if train else 0
    shift=0 if avg_mean==0 else max(-MAX_MEAN_SHIFT,min(MAX_MEAN_SHIFT,-bias/avg_mean))
    proposed_mae=mae(holdout,shift)
    scale=1.0
    if n>=MIN_VARIANCE:
        train_cov=coverage(train)
        if train_cov is not None:
            scale=max(1-MAX_SCALE_SHIFT,min(1+MAX_SCALE_SHIFT,1+(0.80-train_cov)*.25))
    proposed_cov=coverage(holdout,scale)
    mae_improve=None if base_mae is None or proposed_mae is None else base_mae-proposed_mae
    coverage_change=None if base_cov is None or proposed_cov is None else proposed_cov-base_cov
    if n<MIN_WEIGHT:status='LOCKED';reason=f'Requires {MIN_WEIGHT} graded projections; has {n}.'
    elif len(holdout)<20:status='TESTING';reason='Holdout sample below 20.'
    elif mae_improve is None or mae_improve<=0:status='REJECTED';reason='No holdout MAE improvement.'
    elif coverage_change is not None and coverage_change<-.03:status='REJECTED';reason='MAE improved but interval coverage worsened materially.'
    else:status='APPROVED';reason='Passed bounded chronological holdout test; manual review required.'
    return {'proposal_id':f'{stat}|{n}|{round(shift,4)}|{round(scale,4)}','stat':stat,'sample_size':n,'train_size':len(train),'holdout_size':len(holdout),'status':status,'reason':reason,'current':{'mean_multiplier':1.0,'variance_multiplier':1.0},'proposed':{'mean_multiplier':round(1+shift,4),'variance_multiplier':round(scale,4)},'bounds':{'max_mean_change_pct':MAX_MEAN_SHIFT,'max_variance_change_pct':MAX_SCALE_SHIFT},'backtest':{'baseline_mae':round(base_mae,4) if base_mae is not None else None,'proposed_mae':round(proposed_mae,4) if proposed_mae is not None else None,'mae_improvement':round(mae_improve,4) if mae_improve is not None else None,'baseline_coverage':round(base_cov,4) if base_cov is not None else None,'proposed_coverage':round(proposed_cov,4) if proposed_cov is not None else None,'coverage_change':round(coverage_change,4) if coverage_change is not None else None},'production_applied':False}
def build(target:str)->dict[str,Any]:
    rows=[r for r in read_jsonl(HISTORY) if r.get('actual') is not None];groups=defaultdict(list)
    for r in rows:groups[str(r.get('stat') or 'UNKNOWN')].append(r)
    proposals=[proposal_for(stat,items) for stat,items in sorted(groups.items())]
    audit=read_jsonl(PROPOSALS);seen={r.get('proposal_id') for r in audit}
    now=datetime.now(timezone.utc).isoformat()
    for p in proposals:
        if p['proposal_id'] not in seen:audit.append({**p,'created_at_utc':now});seen.add(p['proposal_id'])
    write_jsonl(PROPOSALS,audit)
    payload={'generated_at_utc':now,'target_date':target,'status':'ok','summary':{'stats':len(proposals),'locked':sum(p['status']=='LOCKED' for p in proposals),'testing':sum(p['status']=='TESTING' for p in proposals),'approved':sum(p['status']=='APPROVED' for p in proposals),'rejected':sum(p['status']=='REJECTED' for p in proposals)},'proposals':proposals,'policy':{'production_weights_modified':False,'approval_requires_manual_review':True,'chronological_holdout':True,'minimum_weight_sample':MIN_WEIGHT,'minimum_variance_sample':MIN_VARIANCE,'maximum_single_update_pct':5,'rollback_audit_path':str(PROPOSALS)}}
    for p in OUTS:dump(p,payload)
    print('Controlled Recalibration:',payload['summary']);return payload
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();build(a.date)
if __name__=='__main__':main()
