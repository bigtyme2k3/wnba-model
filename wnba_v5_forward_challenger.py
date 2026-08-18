"""V5 canonical forward champion/challenger evaluation.

Uses one EARLIEST immutable issued prediction per ranking_key from the M12 ledger.
Challenger models are trained only on earlier canonical resolved markets and are
scored chronologically. This module is shadow/research-only and never rewrites
issued predictions or production decisions.
"""
from __future__ import annotations

import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

LEDGER=Path('data/history/wnba_v5_forward_predictions.jsonl')
OUT=Path('data/dashboard/wnba_v5_forward_challenger.json')
MIN_TRAIN=60
L2_LOGISTIC=.15
L2_RIDGE=1.5
LR=.04
EPOCHS=450
EPS=1e-9
FEATURES=[
    'market_implied_probability','line_minus_prior_mean','rolling3_actual_mean',
    'rolling5_actual_mean','rolling5_actual_std','rolling5_trend_slope',
    'historical_hit_rate_at_current_line','historical_hit_rate_l5_at_current_line','prior_games'
]

def f(v,d=None):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except Exception:return d

def clamp(x,lo=.02,hi=.98): return max(lo,min(hi,x))
def sigmoid(z):
    if z>=0:
        e=math.exp(-min(z,40)); return 1/(1+e)
    e=math.exp(max(z,-40)); return e/(1+e)
def logit(p):
    p=clamp(p,.01,.99); return math.log(p/(1-p))
def load_rows():
    rows=[]
    if not LEDGER.exists(): return rows
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try: rows.append(json.loads(line))
            except Exception: pass
    return rows

def canonical_earliest(rows):
    chosen={}
    for r in rows:
        k=str(r.get('ranking_key') or '').strip()
        if not k: continue
        old=chosen.get(k)
        ts=str(r.get('prediction_generated_at_utc') or '')
        if old is None or ts < str(old.get('prediction_generated_at_utc') or ''): chosen[k]=r
    return list(chosen.values())
def xrow(r):
    snap=r.get('feature_snapshot') or {}
    vals=[]
    for k in FEATURES:
        v=f(snap.get(k))
        if v is None: return None
        vals.append(v)
    return vals
def standardize(X):
    p=len(X[0]); mu=[mean(r[j] for r in X) for j in range(p)]; sd=[]
    for j in range(p):
        s=pstdev(r[j] for r in X); sd.append(s if s>1e-8 else 1.0)
    Z=[[(r[j]-mu[j])/sd[j] for j in range(p)] for r in X]
    return Z,mu,sd
def fit_logistic(X,y):
    Z,mu,sd=standardize(X); p=len(X[0]); w=[0.0]*(p+1); w[0]=logit(clamp(sum(y)/len(y),.05,.95))
    for _ in range(EPOCHS):
        g=[0.0]*(p+1)
        for z,t in zip(Z,y):
            pr=sigmoid(w[0]+sum(w[j+1]*z[j] for j in range(p))); err=pr-t; g[0]+=err
            for j in range(p): g[j+1]+=err*z[j]
        g[0]/=len(Z)
        for j in range(p): g[j+1]=g[j+1]/len(Z)+L2_LOGISTIC*w[j+1]
        for j in range(p+1): w[j]-=LR*g[j]
    return {'w':w,'mu':mu,'sd':sd}
def pred_logistic(m,x):
    z=[(x[j]-m['mu'][j])/m['sd'][j] for j in range(len(x))]
    return clamp(sigmoid(m['w'][0]+sum(m['w'][j+1]*z[j] for j in range(len(z)))))
def fit_ridge(X,y):
    Z,mu,sd=standardize(X); p=len(X[0]); w=[mean(y)]+[0.0]*p
    for _ in range(EPOCHS):
        g=[0.0]*(p+1)
        for z,t in zip(Z,y):
            pr=w[0]+sum(w[j+1]*z[j] for j in range(p)); err=pr-t; g[0]+=err
            for j in range(p): g[j+1]+=err*z[j]
        g[0]/=len(Z)
        for j in range(p): g[j+1]=g[j+1]/len(Z)+L2_RIDGE*w[j+1]
        for j in range(p+1): w[j]-=LR*g[j]
    return {'w':w,'mu':mu,'sd':sd}
def pred_ridge(m,x):
    z=[(x[j]-m['mu'][j])/m['sd'][j] for j in range(len(x))]
    return clamp(m['w'][0]+sum(m['w'][j+1]*z[j] for j in range(len(z))))
def brier(ps,ys): return mean((p-y)**2 for p,y in zip(ps,ys)) if ps else None
def logloss(ps,ys): return -mean(y*math.log(clamp(p,EPS,1-EPS))+(1-y)*math.log(clamp(1-p,EPS,1-EPS)) for p,y in zip(ps,ys)) if ps else None
def unit_profit(odds,win):
    o=f(odds)
    if o is None or o==0:return None
    if not win:return -1.0
    return o/100 if o>0 else 100/abs(o)
def summarize(name,rows):
    if not rows:return {'model':name,'n':0}
    ps=[r[name] for r in rows]; ys=[r['y'] for r in rows]
    profits=[]
    for r in rows:
        if r[name]>=.5:
            u=unit_profit(r.get('odds'),r['y'])
            if u is not None:profits.append(u)
    return {'model':name,'n':len(rows),'brier':round(brier(ps,ys),6),'log_loss':round(logloss(ps,ys),6),
            'accuracy':round(mean(int((p>=.5)==bool(y)) for p,y in zip(ps,ys)),6),
            'bets_at_0_5':len(profits),'roi_at_0_5':round(sum(profits)/len(profits),6) if profits else None}
def main():
    canonical=canonical_earliest(load_rows())
    eligible=[]
    for r in canonical:
        y=r.get('target_win'); x=xrow(r)
        if y in (0,1) and x is not None:
            eligible.append((r,x,int(y)))
    eligible.sort(key=lambda t:(str(t[0].get('date') or ''),str(t[0].get('prediction_generated_at_utc') or ''),str(t[0].get('ranking_key') or '')))
    scored=[]
    for i,(r,x,y) in enumerate(eligible):
        if i<MIN_TRAIN: continue
        train=eligible[:i]; X=[a[1] for a in train]; Y=[a[2] for a in train]
        lg=fit_logistic(X,Y); rg=fit_ridge(X,Y)
        market=clamp(f(r.get('market_probability'),f(r.get('market_implied_probability'),.5)))
        raw=clamp(f(r.get('v5_probability'),f(r.get('knn_probability'),.5)))
        lp=pred_logistic(lg,x); rp=pred_ridge(rg,x)
        # Conservative challenger ensemble: market + logistic + ridge only; raw KNN excluded.
        ens=clamp((market+lp+rp)/3)
        scored.append({'date':str(r.get('date') or '')[:10],'ranking_key':r.get('ranking_key'),'side':str(r.get('side') or '').upper(),
                       'stat':str(r.get('stat') or r.get('market') or '').upper(),'odds':r.get('odds'),'y':y,
                       'MARKET':market,'RAW_KNN':raw,'LOGISTIC_FORWARD':lp,'RIDGE_FORWARD':rp,'CHALLENGER_ENSEMBLE':ens})
    models=['MARKET','RAW_KNN','LOGISTIC_FORWARD','RIDGE_FORWARD','CHALLENGER_ENSEMBLE']
    rankings=[summarize(n,scored) for n in models]; rankings.sort(key=lambda z:(z.get('brier',999),z.get('log_loss',999)))
    by_side={}
    for side in ('OVER','UNDER'):
        q=[r for r in scored if r['side']==side]
        by_side[side]=sorted([summarize(n,q) for n in models],key=lambda z:(z.get('brier',999),z.get('log_loss',999)))
    report={'version':'V5','module':'FORWARD_CHAMPION_CHALLENGER','stage':'CANONICAL_CHRONOLOGICAL_SHADOW',
            'generated_at_utc':datetime.now(timezone.utc).isoformat(),'canonical_resolved_eligible_rows':len(eligible),
            'minimum_prior_canonical_rows':MIN_TRAIN,'chronologically_scored_rows':len(scored),'features':FEATURES,
            'rankings':rankings,'forward_research_champion':rankings[0]['model'] if rankings else None,'by_side':by_side,
            'production_ready':False,'research_only':True,
            'policy':'Only earliest immutable prediction per ranking_key is eligible. Challenger fits use prior canonical resolved markets only. No production promotion from this module.',
            'promotion_note':'Require materially larger canonical sample and repeated chronological superiority before altering M10/M11.'}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))
if __name__=='__main__':main()
