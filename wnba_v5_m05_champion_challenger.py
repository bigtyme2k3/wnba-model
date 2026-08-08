"""V5-M05 Ensemble / Champion-Challenger Validation.

Leakage-safe expanding-window comparison of multiple lightweight probability models.
No production promotion is allowed here; M05 is research-only until the sample and
CLV gates from M04 are satisfied.
"""
from __future__ import annotations

import csv, json, math
from pathlib import Path
from statistics import mean, pstdev

FEATURES=Path('data/dashboard/wnba_v5_historical_features.csv')
M04=Path('data/dashboard/wnba_v5_m04_report.json')
OUT_PRED=Path('data/dashboard/wnba_v5_m05_predictions.csv')
OUT_RANK=Path('data/dashboard/wnba_v5_model_rankings.json')
OUT_CHAMP=Path('data/dashboard/wnba_v5_champion.json')
OUT_WEIGHTS=Path('data/dashboard/wnba_v5_ensemble_weights.json')
OUT_REPORT=Path('data/dashboard/wnba_v5_m05_report.json')

MIN_PRIOR=3
MIN_TRAIN=40
EPS=1e-9
FEATURES_LIST=[
 'market_implied_probability','line_minus_prior_mean','rolling3_actual_mean',
 'rolling5_actual_mean','rolling5_actual_std','rolling5_trend_slope',
 'historical_hit_rate_at_current_line','historical_hit_rate_l5_at_current_line','prior_games'
]

def f(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None

def clamp(x,lo=.02,hi=.98): return max(lo,min(hi,x))
def sigmoid(z):
    if z>=0:
        e=math.exp(-min(z,40)); return 1/(1+e)
    e=math.exp(max(z,-40)); return e/(1+e)
def logit(p):
    p=clamp(p,.01,.99); return math.log(p/(1-p))
def rowx(r):
    vals=[]
    for k in FEATURES_LIST:
        x=f(r.get(k))
        if x is None:return None
        vals.append(x)
    return vals

def standardize(X):
    p=len(X[0]); mu=[mean(r[j] for r in X) for j in range(p)]; sd=[]
    for j in range(p):
        s=pstdev(r[j] for r in X); sd.append(s if s>1e-8 else 1.0)
    Z=[[(r[j]-mu[j])/sd[j] for j in range(p)] for r in X]
    return Z,mu,sd

def fit_logistic(X,y,l2=.08,lr=.08,epochs=350):
    Z,mu,sd=standardize(X); p=len(X[0]); w=[0.0]*(p+1); w[0]=logit(clamp(sum(y)/len(y),.05,.95))
    for _ in range(epochs):
        g=[0.0]*(p+1)
        for z,t in zip(Z,y):
            pred=sigmoid(w[0]+sum(w[j+1]*z[j] for j in range(p))); err=pred-t; g[0]+=err
            for j in range(p):g[j+1]+=err*z[j]
        g[0]/=len(Z)
        for j in range(p):g[j+1]=g[j+1]/len(Z)+l2*w[j+1]
        for j in range(p+1):w[j]-=lr*g[j]
    return {'w':w,'mu':mu,'sd':sd}
def pred_logistic(m,x):
    z=[(x[j]-m['mu'][j])/m['sd'][j] for j in range(len(x))]
    return clamp(sigmoid(m['w'][0]+sum(m['w'][j+1]*z[j] for j in range(len(z)))))

def fit_ridge(X,y,l2=1.0):
    Z,mu,sd=standardize(X); p=len(X[0]); w=[mean(y)]+[0.0]*p; lr=.03
    for _ in range(500):
        g=[0.0]*(p+1)
        for z,t in zip(Z,y):
            pr=w[0]+sum(w[j+1]*z[j] for j in range(p)); err=pr-t; g[0]+=err
            for j in range(p):g[j+1]+=err*z[j]
        g[0]/=len(Z)
        for j in range(p):g[j+1]=g[j+1]/len(Z)+l2*w[j+1]
        for j in range(p+1):w[j]-=lr*g[j]
    return {'w':w,'mu':mu,'sd':sd}
def pred_ridge(m,x):
    z=[(x[j]-m['mu'][j])/m['sd'][j] for j in range(len(x))]
    return clamp(m['w'][0]+sum(m['w'][j+1]*z[j] for j in range(len(z))))

def pred_empirical(r):
    vals=[f(r.get('historical_hit_rate_at_current_line')),f(r.get('historical_hit_rate_l5_at_current_line')),f(r.get('market_implied_probability'))]
    vals=[x for x in vals if x is not None]
    return clamp(mean(vals) if vals else .5)

def pred_knn(train,x,k=15):
    X=[a[1] for a in train]; Z,mu,sd=standardize(X)
    zx=[(x[j]-mu[j])/sd[j] for j in range(len(x))]
    ds=[]
    for z,a in zip(Z,train):
        d=sum((z[j]-zx[j])**2 for j in range(len(zx))); ds.append((d,a[2]))
    ds.sort(key=lambda t:t[0]); q=ds[:min(k,len(ds))]
    return clamp(sum(y/(math.sqrt(d)+.25) for d,y in q)/sum(1/(math.sqrt(d)+.25) for d,_ in q))

def brier(ps,ys):return mean((p-y)**2 for p,y in zip(ps,ys))
def logloss(ps,ys):return -mean(y*math.log(clamp(p,EPS,1-EPS))+(1-y)*math.log(clamp(1-p,EPS,1-EPS)) for p,y in zip(ps,ys))
def acc(ps,ys):return mean(int((p>=.5)==bool(y)) for p,y in zip(ps,ys))
def ece(ps,ys,bins=5):
    total=len(ps); out=0.0
    for b in range(bins):
        lo=b/bins; hi=(b+1)/bins
        idx=[i for i,p in enumerate(ps) if lo<=p<(hi if b<bins-1 else hi+EPS)]
        if idx:out+=len(idx)/total*abs(mean(ps[i] for i in idx)-mean(ys[i] for i in idx))
    return out

def unit_profit(odds,win):
    o=f(odds)
    if not win:return -1.0
    if o is None or o==0:return 0.0
    return o/100 if o>0 else 100/abs(o)

def main():
    rows=list(csv.DictReader(FEATURES.open(encoding='utf-8-sig',newline='')))
    eligible=[]
    for r in rows:
        x=rowx(r); y=f(r.get('target_win')); pg=int(float(r.get('prior_games') or 0))
        if x is not None and y in (0.0,1.0) and pg>=MIN_PRIOR:eligible.append((r,x,int(y)))
    eligible.sort(key=lambda t:(t[0].get('game_date',''),t[0].get('game_id',''),int(t[0].get('archive_index') or 0)))
    names=['MARKET','LOGISTIC_V5','RIDGE_LINEAR','EMPIRICAL','KNN','ENSEMBLE']
    hist={n:[] for n in names}; ys=[]; out=[]
    for i,(r,x,y) in enumerate(eligible):
        if i<MIN_TRAIN:continue
        train=eligible[:i]; X=[a[1] for a in train]; Y=[a[2] for a in train]
        lg=fit_logistic(X,Y); rg=fit_ridge(X,Y)
        preds={
          'MARKET':clamp(f(r.get('market_implied_probability')) or .5),
          'LOGISTIC_V5':pred_logistic(lg,x),
          'RIDGE_LINEAR':pred_ridge(rg,x),
          'EMPIRICAL':pred_empirical(r),
          'KNN':pred_knn(train,x),
        }
        # Dynamic ensemble weights use only PRIOR out-of-sample performance.
        prior_scores={}
        for n in ['LOGISTIC_V5','RIDGE_LINEAR','EMPIRICAL','KNN','MARKET']:
            if len(hist[n])>=10:
                prior_scores[n]=1/max(mean((p-t)**2 for p,t in hist[n]),1e-6)
            else:prior_scores[n]=1.0
        den=sum(prior_scores.values()); preds['ENSEMBLE']=clamp(sum(preds[n]*prior_scores[n] for n in prior_scores)/den)
        ys.append(y)
        for n in names:hist[n].append((preds[n],y))
        out.append({
          'archive_index':r.get('archive_index'),'game_date':r.get('game_date'),'game_id':r.get('game_id'),'player':r.get('player'),
          'stat':r.get('stat'),'side':r.get('side'),'alt_line':r.get('alt_line'),'american_odds':r.get('american_odds'),'target_win':y,
          **{n.lower()+'_probability':round(preds[n],6) for n in names},'train_rows':i
        })
    if not out:raise SystemExit('V5_M05_INSUFFICIENT_ROWS')
    rankings=[]
    for n in names:
        ps=[p for p,_ in hist[n]]; yy=[y for _,y in hist[n]]
        profits=sum(unit_profit(o.get('american_odds'),int(o['target_win'])) for o in out if (float(o[n.lower()+'_probability'])>=.5))
        bets=sum(1 for o in out if float(o[n.lower()+'_probability'])>=.5)
        rankings.append({'model':n,'n':len(ps),'brier':round(brier(ps,yy),6),'log_loss':round(logloss(ps,yy),6),'ece_5bin':round(ece(ps,yy),6),'accuracy':round(acc(ps,yy),6),'bets_at_0_5':bets,'profit_units_at_0_5':round(profits,4),'roi_at_0_5':round(profits/bets,6) if bets else None})
    rankings.sort(key=lambda r:(r['brier'],r['log_loss']))
    research_champion=rankings[0]['model']
    # Stable final ensemble weights from all OOS Brier values, excluding ensemble itself.
    bases=[r for r in rankings if r['model']!='ENSEMBLE']; inv={r['model']:1/max(r['brier'],1e-6) for r in bases}; den=sum(inv.values()); weights={k:round(v/den,6) for k,v in inv.items()}
    m04=json.loads(M04.read_text()) if M04.exists() else {}
    production=False
    report={
      'version':'V5','module':'V5-M05','stage':'ENSEMBLE_CHAMPION_CHALLENGER','status':'READY',
      'evaluation_rows':len(out),'minimum_train_rows':MIN_TRAIN,'models_evaluated':names,
      'research_champion':research_champion,'rankings':rankings,'ensemble_weights':weights,
      'promotion_gate':{
        'production_promotion':production,
        'reason':'Research-only: require >=300 forward observations and >=60% CLV coverage before replacing V4.',
        'evaluation_rows':len(out),'minimum_required_rows':300,
        'clv_coverage_pct':(m04.get('clv') or {}).get('coverage_pct',0.0),'minimum_clv_coverage_pct':60.0
      },
      'next_module':'V5-M06 Market Movement Intelligence'
    }
    OUT_PRED.parent.mkdir(parents=True,exist_ok=True)
    with OUT_PRED.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(out[0].keys()));w.writeheader();w.writerows(out)
    OUT_RANK.write_text(json.dumps({'version':'V5','module':'V5-M05','rankings':rankings},indent=2)+'\n')
    OUT_CHAMP.write_text(json.dumps({'research_champion':research_champion,'production_champion':'V4','production_promotion':False},indent=2)+'\n')
    OUT_WEIGHTS.write_text(json.dumps({'weights':weights,'method':'inverse walk-forward Brier; ensemble prediction itself uses only prior OOS Brier'},indent=2)+'\n')
    OUT_REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
