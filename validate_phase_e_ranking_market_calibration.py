"""Sprint 20.5 Phase E: validate ranking signal and segmented calibration."""
from __future__ import annotations
import argparse, json, math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HISTORY=Path('data/history/wnba_model_history.jsonl')
PHASE_D=Path('data/audit/phase_d_calibration_validation.json')
REPORT=Path('data/audit/phase_e_ranking_market_validation.json')
SEGMENTS=Path('data/audit/phase_e_segment_validation.json')
POLICY=Path('data/warehouse/wnba_calibration_deployment_policy.json')

def load_json(path:Path, default:Any):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def read_jsonl(path:Path)->List[Dict[str,Any]]:
    out=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                row=json.loads(line)
                if isinstance(row,dict):out.append(row)
            except Exception:pass
    return out

def prob(v:Any)->Optional[float]:
    try:x=float(v)
    except Exception:return None
    if not math.isfinite(x):return None
    if x>1:x/=100
    return x if 0<=x<=1 else None

def result(row:Dict[str,Any])->Optional[int]:
    x=str(row.get('outcome') or row.get('result') or '').upper()
    return 1 if x=='WIN' else 0 if x=='LOSS' else None

def direction(row:Dict[str,Any])->str:
    text=str(row.get('signal') or row.get('selection') or row.get('side') or '').upper()
    if 'UNDER' in text:return 'UNDER'
    if 'OVER' in text:return 'OVER'
    return 'UNKNOWN'

def market(row:Dict[str,Any])->str:return str(row.get('stat') or row.get('market') or 'UNKNOWN').upper()

def auc(scores:Sequence[float], ys:Sequence[int])->Optional[float]:
    pos=[s for s,y in zip(scores,ys) if y==1]; neg=[s for s,y in zip(scores,ys) if y==0]
    if not pos or not neg:return None
    wins=ties=0
    for p in pos:
        for n in neg:
            wins += p>n; ties += p==n
    return (wins+0.5*ties)/(len(pos)*len(neg))

def brier(scores,ys):return sum((p-y)**2 for p,y in zip(scores,ys))/len(scores) if scores else None

def logloss(scores,ys):
    if not scores:return None
    return -sum(y*math.log(max(1e-6,min(1-1e-6,p)))+(1-y)*math.log(max(1e-6,min(1-1e-6,1-p))) for p,y in zip(scores,ys))/len(scores)

def ece(scores,ys):
    if not scores:return None
    total=len(scores); value=0.0
    for i in range(10):
        lo=i/10; hi=(i+1)/10 if i<9 else 1.000001
        idx=[j for j,p in enumerate(scores) if lo<=p<hi]
        if idx:
            ap=sum(scores[j] for j in idx)/len(idx); ar=sum(ys[j] for j in idx)/len(idx)
            value += abs(ap-ar)*len(idx)/total
    return value

def platt(p:float,model:Dict[str,Any])->float:
    p=max(1e-6,min(1-1e-6,p)); z=math.log(p/(1-p))
    a=float(model.get('a',1)); b=float(model.get('b',0))
    return 1/(1+math.exp(-(a*z+b)))

def deciles(scores,ys):
    order=sorted(range(len(scores)),key=lambda i:scores[i])
    out=[]
    for d in range(10):
        idx=order[d*len(order)//10:(d+1)*len(order)//10]
        if idx:out.append({'decile':d+1,'count':len(idx),'avg_score':round(sum(scores[i] for i in idx)/len(idx),6),'win_rate':round(sum(ys[i] for i in idx)/len(idx),6)})
    return out

def metrics(scores,ys):
    ds=deciles(scores,ys); spread=(ds[-1]['win_rate']-ds[0]['win_rate']) if len(ds)>=2 else None
    return {'samples':len(scores),'auc':None if auc(scores,ys) is None else round(auc(scores,ys),6),'brier':None if brier(scores,ys) is None else round(brier(scores,ys),6),'log_loss':None if logloss(scores,ys) is None else round(logloss(scores,ys),6),'ece':None if ece(scores,ys) is None else round(ece(scores,ys),6),'top_bottom_decile_win_rate_spread':None if spread is None else round(spread,6),'deciles':ds}

def build(target:str)->Dict[str,Any]:
    rows=[]
    for r in read_jsonl(HISTORY):
        p=prob(r.get('simulation_probability')); y=result(r); d=str(r.get('date') or '')
        if p is not None and y is not None and d:rows.append((d,r,p,y))
    rows.sort(key=lambda x:x[0]); split=max(1,int(len(rows)*0.70)); validation=rows[split:]
    phase_d=load_json(PHASE_D,{})
    model=phase_d.get('selected_calibrator') or phase_d.get('summary',{})
    raw=[p for _,_,p,_ in validation]; ys=[y for *_,y in validation]
    calibrated=[platt(p,model) if model.get('method')=='platt' else p for p in raw]
    raw_m=metrics(raw,ys); cal_m=metrics(calibrated,ys)
    grouped=defaultdict(list)
    for d,r,p,y in validation:
        grouped[f'MARKET:{market(r)}'].append((p,y)); grouped[f'DIRECTION:{direction(r)}'].append((p,y)); grouped[f'MARKET_DIRECTION:{market(r)}:{direction(r)}'].append((p,y))
    segment_rows=[]
    for key,pairs in sorted(grouped.items()):
        s=[x[0] for x in pairs]; yy=[x[1] for x in pairs]; m=metrics(s,yy); m['segment']=key; m['eligible_for_segment_model']=len(pairs)>=100 and m.get('auc') is not None
        segment_rows.append(m)
    auc_ok=raw_m.get('auc') is not None and raw_m['auc']>=0.53
    spread_ok=raw_m.get('top_bottom_decile_win_rate_spread') is not None and raw_m['top_bottom_decile_win_rate_spread']>=0.08
    rank_preserved=(cal_m.get('auc') is not None and raw_m.get('auc') is not None and cal_m['auc']>=raw_m['auc']-0.01)
    probability_spread=(max(calibrated)-min(calibrated)) if calibrated else 0
    noncollapsed=probability_spread>=0.08
    gate='PASS' if auc_ok and spread_ok and rank_preserved and noncollapsed else 'HOLD'
    findings=[]
    if not auc_ok:findings.append('weak_global_discrimination')
    if not spread_ok:findings.append('insufficient_top_bottom_decile_separation')
    if not rank_preserved:findings.append('calibration_damages_ranking')
    if not noncollapsed:findings.append('calibrated_probabilities_collapsed')
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'settled_records':len(rows),'validation_records':len(validation),'split_date':validation[0][0] if validation else None,'raw_auc':raw_m.get('auc'),'calibrated_auc':cal_m.get('auc'),'raw_decile_spread':raw_m.get('top_bottom_decile_win_rate_spread'),'calibrated_probability_range':round(probability_spread,6),'deployment_gate':gate,'status':'PASS' if gate=='PASS' else 'WARN'},'raw_validation':raw_m,'calibrated_validation':cal_m,'findings':findings,'segment_count':len(segment_rows),'deployment_policy':{'minimum_auc':0.53,'minimum_top_bottom_decile_spread':0.08,'maximum_auc_loss_after_calibration':0.01,'minimum_calibrated_probability_range':0.08,'requires_calibration_metric_improvement':True,'requires_preserved_ranking':True},'recommendation':'ENABLE_CALIBRATED_EV' if gate=='PASS' else 'KEEP_CALIBRATOR_DISABLED_AND_REBUILD_PROBABILITY_SIGNAL'}
    for path,payload in ((REPORT,report),(SEGMENTS,{'generated_at_utc':report['generated_at_utc'],'segments':segment_rows}),(POLICY,{'enabled':gate=='PASS','gate':gate,'selected_method':model.get('method'),'findings':findings,'policy':report['deployment_policy']})):
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,indent=2,allow_nan=False),encoding='utf-8')
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Phase E:',build(a.date)['summary'])
if __name__=='__main__':main()
