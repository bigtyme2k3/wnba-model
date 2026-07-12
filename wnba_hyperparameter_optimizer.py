"""M23 deterministic champion/challenger hyperparameter search."""
from __future__ import annotations
import argparse,itertools,json,math,os
from datetime import date,datetime,timezone
HIST='data/history/wnba_model_history.jsonl'; PREV='data/warehouse/wnba_hyperparameter_optimizer.json'
def read_jsonl(path):
    out=[]
    if os.path.exists(path):
        for line in open(path,encoding='utf-8'):
            try:out.append(json.loads(line))
            except Exception:pass
    return out
def load(path,d):
    try:return json.load(open(path,encoding='utf-8')) if os.path.exists(path) else d
    except Exception:return d
def num(v,d=0):
    try:
        n=float(v);return n if math.isfinite(n) else d
    except Exception:return d
def score_row(r,w):
    edge=max(0,min(1,num(r.get('edge_pct'))/15));ev=max(0,min(1,num(r.get('ev_pct'))/15));prob=max(0,min(1,(num(r.get('simulation_probability'),.5)-.5)/.25));market=max(0,min(1,.5+num(r.get('market_move'))/10))
    return w[0]*edge+w[1]*ev+w[2]*prob+w[3]*market
def evaluate(rows,w):
    if not rows:return 0
    chosen=sorted(rows,key=lambda r:score_row(r,w),reverse=True)[:max(5,len(rows)//3)];return sum(r.get('outcome')=='WIN' for r in chosen)/max(1,sum(r.get('outcome') in {'WIN','LOSS'} for r in chosen))
def build(target):
    rows=[r for r in read_jsonl(HIST) if r.get('outcome') in {'WIN','LOSS'}]; champion=load(PREV,{}).get('production_weights',[.35,.25,.25,.15]);champion_score=evaluate(rows,champion);best=(champion_score,champion)
    grid=[.15,.25,.35,.45]
    for a,b,c in itertools.product(grid,repeat=3):
        d=1-a-b-c
        if d<.1 or d>.5:continue
        w=[a,b,c,round(d,2)];s=evaluate(rows,w)
        if s>best[0]:best=(s,w)
    minimum=60;improvement=best[0]-champion_score;promote=len(rows)>=minimum and improvement>=.02
    production=best[1] if promote else champion
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'samples':len(rows),'champion_score':round(champion_score,4),'challenger_score':round(best[0],4),'improvement':round(improvement,4),'promoted':promote},'feature_order':['edge','ev','simulation','market'],'champion_weights':champion,'challenger_weights':best[1],'production_weights':production,'policy':{'minimum_samples':minimum,'minimum_improvement':.02,'rollback_safe':True}}
    os.makedirs('data/warehouse',exist_ok=True);os.makedirs('data/dashboard',exist_ok=True)
    for p in ('data/warehouse/wnba_hyperparameter_optimizer.json','data/dashboard/wnba_hyperparameter_optimizer.json'):json.dump(report,open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
    return report
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Optimizer:',build(a.date)['summary'])
if __name__=='__main__':main()
