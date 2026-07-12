"""M18 safe self-learning with minimum samples and bounded weight changes."""
from __future__ import annotations
import argparse,json,math,os
from datetime import date,datetime,timezone
from typing import Any

HISTORY_PATH='data/history/wnba_model_history.jsonl'; PREV='data/warehouse/wnba_self_learning.json'
ENGINES=['Projection EV','Projection Edge','Player Intelligence','Matchup Intelligence','Injury Engine','Market Engine','DeepSeek Engine']

def read_jsonl(path):
    out=[]
    if os.path.exists(path):
        for line in open(path,encoding='utf-8'):
            try:out.append(json.loads(line))
            except Exception:pass
    return out

def load(path,default):
    try:return json.load(open(path,encoding='utf-8')) if os.path.exists(path) else default
    except Exception:return default

def normalize(weights):
    safe={k:max(0.05,min(0.30,float(weights.get(k,0)))) for k in ENGINES}; total=sum(safe.values()) or 1
    return {k:round(v/total,4) for k,v in safe.items()}

def build(target):
    hist=read_jsonl(HISTORY_PATH); finalized=[r for r in hist if r.get('outcome') in {'WIN','LOSS','PUSH'} and r.get('actual') is not None]
    previous=load(PREV,{}).get('engine_weights') or {e:1/len(ENGINES) for e in ENGINES}; candidate=dict(previous)
    minimum=40; applied=False; reason='minimum sample not reached'
    if len(finalized)>=minimum:
        decisions=[r for r in finalized if r.get('outcome') in {'WIN','LOSS'}]; wr=sum(r.get('outcome')=='WIN' for r in decisions)/max(1,len(decisions)); clv=[float(r.get('line_clv')) for r in finalized if isinstance(r.get('line_clv'),(int,float)) and math.isfinite(float(r.get('line_clv')))] ; avg_clv=sum(clv)/len(clv) if clv else 0
        shifts={e:0.0 for e in ENGINES}
        if wr>=0.55: shifts['Projection EV']+=0.015; shifts['Projection Edge']+=0.01
        else: shifts['Player Intelligence']+=0.01; shifts['Matchup Intelligence']+=0.01
        if avg_clv>0: shifts['Market Engine']+=0.015
        elif avg_clv<0: shifts['Market Engine']-=0.01
        for k,v in shifts.items(): candidate[k]=candidate.get(k,1/len(ENGINES))+max(-0.02,min(0.02,v))
        candidate=normalize(candidate)
        previous_score=float(load(PREV,{}).get('validation_score',0) or 0); validation=round(0.7*wr+0.3*max(0,min(1,0.5+avg_clv/10)),4)
        if previous_score and validation<previous_score-0.02:
            candidate=normalize(previous); reason='candidate rejected because validation worsened'
        else:
            applied=True; reason='bounded update accepted'
    else:
        validation=float(load(PREV,{}).get('validation_score',0) or 0); candidate=normalize(previous)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','history_records':len(hist),'graded_records':len(finalized),'minimum_sample':minimum,'update_applied':applied,'update_reason':reason,'validation_score':validation,'engine_weights':candidate,'safety':{'max_single_update':0.02,'weight_floor':0.05,'weight_ceiling':0.30,'rollback_on_validation_drop':True}}
    os.makedirs('data/warehouse',exist_ok=True);os.makedirs('data/dashboard',exist_ok=True)
    for p in ('data/warehouse/wnba_self_learning.json','data/dashboard/wnba_self_learning.json'):json.dump(report,open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Self learning:',build(a.date))
if __name__=='__main__':main()
