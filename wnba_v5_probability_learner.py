"""V5-M02 Probability Learner.

Small-sample, leakage-safe champion/challenger learner built on the certified V5
historical feature store. Uses chronological expanding-window logistic regression
implemented with the Python standard library. Predictions are produced only for
rows with >=3 prior player/stat games and only after a minimum historical train
window exists.
"""
from __future__ import annotations

import csv, json, math
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

FEATURES=Path('data/dashboard/wnba_v5_historical_features.csv')
OUT_CSV=Path('data/dashboard/wnba_v5_probability_predictions.csv')
OUT_JSON=Path('data/warehouse/wnba_v5_probability_model.json')
STATUS=Path('data/dashboard/wnba_v5_probability_status.json')

MIN_PRIOR_GAMES=3
MIN_TRAIN=40
L2=0.08
LR=0.08
EPOCHS=500
EPS=1e-9

FEATURE_NAMES=[
    'market_implied_probability',
    'line_minus_prior_mean',
    'rolling3_actual_mean',
    'rolling5_actual_mean',
    'rolling5_actual_std',
    'rolling5_trend_slope',
    'historical_hit_rate_at_current_line',
    'historical_hit_rate_l5_at_current_line',
    'prior_games',
]

def f(v:Any):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def clamp(x:float,lo:float=0.02,hi:float=0.98)->float:
    return max(lo,min(hi,x))

def sigmoid(z:float)->float:
    if z>=0:
        ez=math.exp(-min(z,40)); return 1/(1+ez)
    ez=math.exp(max(z,-40)); return ez/(1+ez)

def logit(p:float)->float:
    p=clamp(p,0.01,0.99)
    return math.log(p/(1-p))

def row_features(r:dict[str,str])->list[float]|None:
    vals=[]
    for k in FEATURE_NAMES:
        x=f(r.get(k))
        if x is None:
            return None
        vals.append(x)
    return vals

def fit_logistic(X:list[list[float]],y:list[int]):
    n=len(X); p=len(X[0])
    mu=[mean(row[j] for row in X) for j in range(p)]
    sd=[]
    for j in range(p):
        s=pstdev(row[j] for row in X)
        sd.append(s if s>1e-8 else 1.0)
    Z=[[(row[j]-mu[j])/sd[j] for j in range(p)] for row in X]
    w=[0.0]*(p+1)
    # Initialize intercept from base rate.
    base=clamp(sum(y)/n,0.05,0.95)
    w[0]=logit(base)
    for _ in range(EPOCHS):
        g=[0.0]*(p+1)
        for z,t in zip(Z,y):
            pred=sigmoid(w[0]+sum(w[j+1]*z[j] for j in range(p)))
            err=pred-t
            g[0]+=err
            for j in range(p): g[j+1]+=err*z[j]
        g[0]/=n
        for j in range(p):
            g[j+1]=g[j+1]/n + L2*w[j+1]
        for j in range(p+1): w[j]-=LR*g[j]
    return {'weights':w,'mean':mu,'std':sd}

def predict(model,x:list[float])->float:
    z=[(x[j]-model['mean'][j])/model['std'][j] for j in range(len(x))]
    return clamp(sigmoid(model['weights'][0]+sum(model['weights'][j+1]*z[j] for j in range(len(z)))))

def brier(ps,ys): return sum((p-y)**2 for p,y in zip(ps,ys))/len(ps) if ps else None

def logloss(ps,ys):
    return -sum(y*math.log(clamp(p,EPS,1-EPS))+(1-y)*math.log(clamp(1-p,EPS,1-EPS)) for p,y in zip(ps,ys))/len(ps) if ps else None

def ece(ps,ys,bins=5):
    if not ps:return None
    total=len(ps); out=0.0
    for b in range(bins):
        lo=b/bins; hi=(b+1)/bins
        idx=[i for i,p in enumerate(ps) if (lo<=p<(hi if b<bins-1 else hi+EPS))]
        if not idx: continue
        conf=mean(ps[i] for i in idx); acc=mean(ys[i] for i in idx)
        out+=len(idx)/total*abs(conf-acc)
    return out

def main():
    rows=list(csv.DictReader(FEATURES.open(encoding='utf-8-sig',newline='')))
    eligible=[]
    for r in rows:
        pg=int(float(r.get('prior_games') or 0))
        x=row_features(r)
        y=f(r.get('target_win'))
        if pg>=MIN_PRIOR_GAMES and x is not None and y in (0.0,1.0):
            eligible.append((r,x,int(y)))
    eligible.sort(key=lambda t:(t[0].get('game_date',''),t[0].get('game_id',''),int(t[0].get('archive_index') or 0)))

    preds=[]
    market_ps=[]; model_ps=[]; ys=[]
    # Expanding-window, refit before each evaluation row. Slow but tiny dataset and maximally auditable.
    for i,(r,x,y) in enumerate(eligible):
        if i<MIN_TRAIN: continue
        train=eligible[:i]
        X=[a[1] for a in train]; Y=[a[2] for a in train]
        model=fit_logistic(X,Y)
        mp=clamp(f(r.get('market_implied_probability')) or 0.5)
        pp=predict(model,x)
        edge=pp-mp
        out={
            'archive_index':r.get('archive_index'),'game_date':r.get('game_date'),'game_id':r.get('game_id'),
            'player':r.get('player'),'stat':r.get('stat'),'side':r.get('side'),'alt_line':r.get('alt_line'),
            'american_odds':r.get('american_odds'),'prior_games':r.get('prior_games'),'target_win':y,
            'market_probability':round(mp,6),'v5_probability':round(pp,6),'probability_edge':round(edge,6),
            'train_rows':i,'walk_forward':True,
        }
        preds.append(out); market_ps.append(mp); model_ps.append(pp); ys.append(y)

    if not preds:
        raise SystemExit('V5_M02_INSUFFICIENT_WALK_FORWARD_ROWS')

    # Final model fit for future scoring artifact, but never used in walk-forward metrics above.
    X=[a[1] for a in eligible]; Y=[a[2] for a in eligible]
    final_model=fit_logistic(X,Y)
    market_b=brier(market_ps,ys); model_b=brier(model_ps,ys)
    report={
        'version':'V5','module':'V5-M02','stage':'PROBABILITY_LEARNER',
        'status':'READY' if len(preds)>=50 else 'LIMITED_SAMPLE',
        'feature_rows_total':len(rows),'training_eligible_rows':len(eligible),
        'walk_forward_predictions':len(preds),'minimum_train_rows':MIN_TRAIN,
        'feature_names':FEATURE_NAMES,
        'metrics':{
            'v5_brier':round(model_b,6),'market_brier':round(market_b,6),
            'brier_improvement_vs_market':round(market_b-model_b,6),
            'v5_log_loss':round(logloss(model_ps,ys),6),'market_log_loss':round(logloss(market_ps,ys),6),
            'v5_ece_5bin':round(ece(model_ps,ys),6),'market_ece_5bin':round(ece(market_ps,ys),6),
            'walk_forward_hit_rate_at_0_5':round(sum((p>=.5)==bool(y) for p,y in zip(model_ps,ys))/len(ys),6),
        },
        'champion_decision':'V5' if model_b < market_b else 'MARKET_BASELINE',
        'promotion_rule':'Do not replace production V4 decisions yet; proceed to V5-M03 calibration/validation.',
        'next_module':'V5-M03 Calibration + Probability Bands',
    }

    OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(preds[0].keys())); w.writeheader(); w.writerows(preds)
    artifact={
        'schema':'v5-probability-model-v1','training_rows':len(eligible),'features':FEATURE_NAMES,
        'model':final_model,'hyperparameters':{'l2':L2,'learning_rate':LR,'epochs':EPOCHS},
        'metrics':report['metrics'],'note':'Final coefficients are for forward scoring only; historical metrics are expanding-window walk-forward.'
    }
    OUT_JSON.parent.mkdir(parents=True,exist_ok=True); OUT_JSON.write_text(json.dumps(artifact,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    STATUS.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
