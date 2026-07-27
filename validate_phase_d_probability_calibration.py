"""Sprint 20.5 Phase D: chronological out-of-sample probability calibration validation."""
from __future__ import annotations
import argparse, json, math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HISTORY=Path('data/history/wnba_model_history.jsonl')
REPORT=Path('data/audit/phase_d_calibration_validation.json')
MODEL=Path('data/warehouse/wnba_probability_calibrator.json')
CURVES=Path('data/audit/phase_d_validation_curves.json')
BANDS=((0,.5),(.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,.95),(.95,1.000001))

def read_rows():
    if not HISTORY.exists(): return []
    out=[]
    for line in HISTORY.read_text(encoding='utf-8').splitlines():
        try:
            r=json.loads(line)
            if isinstance(r,dict): out.append(r)
        except Exception: pass
    return out

def prob(v):
    try: x=float(v); x=x/100 if x>1 else x
    except Exception: return None
    return x if math.isfinite(x) and 0<=x<=1 else None

def result(r):
    x=str(r.get('outcome') or r.get('result') or '').upper()
    return 1 if x=='WIN' else 0 if x=='LOSS' else None

def clamp(x): return max(1e-6,min(1-1e-6,x))
def logit(p): p=clamp(p); return math.log(p/(1-p))
def sigmoid(z): return 1/(1+math.exp(-max(-40,min(40,z))))

def metrics(pairs):
    n=len(pairs)
    if not n: return {'samples':0}
    bs=sum((p-y)**2 for p,y in pairs)/n
    ll=-sum(y*math.log(clamp(p))+(1-y)*math.log(clamp(1-p)) for p,y in pairs)/n
    bands=[]; ece=0
    for lo,hi in BANDS:
        m=[(p,y) for p,y in pairs if lo<=p<hi]
        if not m: continue
        ap=sum(p for p,_ in m)/len(m); hr=sum(y for _,y in m)/len(m); gap=hr-ap
        ece += abs(gap)*len(m)/n
        bands.append({'low':lo,'high':min(1,hi),'count':len(m),'average_probability':round(ap,6),'actual_win_rate':round(hr,6),'gap':round(gap,6)})
    return {'samples':n,'brier_score':round(bs,6),'log_loss':round(ll,6),'ece':round(ece,6),'average_probability':round(sum(p for p,_ in pairs)/n,6),'actual_win_rate':round(sum(y for _,y in pairs)/n,6),'bands':bands}

def fit_temperature(train):
    best=(1.0,10**9)
    for i in range(50,801):
        t=i/100
        ll=metrics([(sigmoid(logit(p)/t),y) for p,y in train]).get('log_loss',99)
        if ll<best[1]: best=(t,ll)
    return {'method':'temperature','temperature':best[0]}

def fit_shrink(train):
    best=(1.0,10**9)
    for i in range(0,101):
        s=i/100
        ll=metrics([(0.5+s*(p-0.5),y) for p,y in train]).get('log_loss',99)
        if ll<best[1]: best=(s,ll)
    return {'method':'linear_shrinkage','strength':best[0]}

def fit_platt(train):
    a,b=1.0,0.0; lr=.02
    for _ in range(2500):
        ga=gb=0.0
        for p,y in train:
            q=sigmoid(a*logit(p)+b); ga+=(q-y)*logit(p); gb+=q-y
        n=max(1,len(train)); a-=lr*ga/n; b-=lr*gb/n
    return {'method':'platt','a':round(a,8),'b':round(b,8)}

def fit_isotonic(train):
    blocks=[]
    for p,y in sorted(train):
        blocks.append([p,p,1,float(y)])
        while len(blocks)>1 and blocks[-2][3]/blocks[-2][2] > blocks[-1][3]/blocks[-1][2]:
            z=blocks.pop(); blocks[-1][1]=z[1]; blocks[-1][2]+=z[2]; blocks[-1][3]+=z[3]
    return {'method':'isotonic','blocks':[{'low':a,'high':b,'value':s/n} for a,b,n,s in blocks]}

def apply(model,p):
    m=model['method']
    if m=='identity': return p
    if m=='temperature': return sigmoid(logit(p)/model['temperature'])
    if m=='linear_shrinkage': return 0.5+model['strength']*(p-0.5)
    if m=='platt': return sigmoid(model['a']*logit(p)+model['b'])
    if m=='isotonic':
        blocks=model['blocks']
        for b in blocks:
            if p<=b['high']: return clamp(b['value'])
        return clamp(blocks[-1]['value'])
    raise ValueError(m)

def build(target, train_share=.70):
    settled=[]
    for r in read_rows():
        p=prob(r.get('simulation_probability')); y=result(r); d=str(r.get('date') or '')
        if p is not None and y is not None and d: settled.append((d,p,y))
    settled.sort(key=lambda x:x[0])
    cut=max(1,min(len(settled)-1,int(len(settled)*train_share))) if len(settled)>1 else 0
    train=[(p,y) for _,p,y in settled[:cut]]; valid=[(p,y) for _,p,y in settled[cut:]]
    candidates=[{'method':'identity'},fit_temperature(train),fit_shrink(train),fit_platt(train),fit_isotonic(train)] if train else [{'method':'identity'}]
    evaluations=[]
    raw=metrics(valid)
    for model in candidates:
        transformed=[(apply(model,p),y) for p,y in valid]
        m=metrics(transformed)
        evaluations.append({'model':model,'validation':m,'brier_improvement':round(raw.get('brier_score',0)-m.get('brier_score',0),6),'log_loss_improvement':round(raw.get('log_loss',0)-m.get('log_loss',0),6),'ece_improvement':round(raw.get('ece',0)-m.get('ece',0),6)})
    ranked=sorted(evaluations,key=lambda x:(x['validation'].get('log_loss',99),x['validation'].get('brier_score',99),x['validation'].get('ece',99)))
    best=ranked[0] if ranked else None
    deploy=bool(best and best['model']['method']!='identity' and len(train)>=500 and len(valid)>=200 and best['log_loss_improvement']>=.01 and best['brier_improvement']>=.005 and best['ece_improvement']>0)
    selected=best['model'] if deploy else {'method':'identity'}
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'settled_records':len(settled),'training_records':len(train),'validation_records':len(valid),'split_date':settled[cut][0] if cut<len(settled) else None,'raw_validation_brier':raw.get('brier_score'),'raw_validation_log_loss':raw.get('log_loss'),'raw_validation_ece':raw.get('ece'),'best_method':best['model']['method'] if best else None,'deployment_gate':'PASS' if deploy else 'HOLD','status':'PASS' if deploy else 'WARN'},'raw_validation':raw,'candidate_evaluations':ranked,'deployment_policy':{'minimum_training_records':500,'minimum_validation_records':200,'minimum_log_loss_improvement':.01,'minimum_brier_improvement':.005,'requires_ece_improvement':True,'uses_chronological_split':True},'selected_calibrator':selected,'notes':['Raw simulation_probability is preserved.','No calibrated probability is used for EV until the deployment gate passes.','Validation records are strictly later than training records.']}
    calibrator={'generated_at_utc':report['generated_at_utc'],'enabled':deploy,'source_field':'simulation_probability','output_field':'calibrated_probability','raw_field':'raw_simulation_probability','model':selected,'validation_summary':report['summary']}
    curves={'generated_at_utc':report['generated_at_utc'],'raw':raw.get('bands',[]),'best':best['validation'].get('bands',[]) if best else []}
    for path,payload in ((REPORT,report),(MODEL,calibrator),(CURVES,curves)):
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,indent=2,allow_nan=False),encoding='utf-8')
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); ap.add_argument('--train-share',type=float,default=.70); a=ap.parse_args()
    r=build(a.date,a.train_share); print('Phase D validation:',r['summary'])
if __name__=='__main__': main()
