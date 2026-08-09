"""V5-M08 context-aware challenger validation.

Tests whether M07 context/similarity features add out-of-sample value beyond the
M05 KNN research champion. Each challenger is fit only on earlier M07 rows and
then scored on the next row. The first MIN_CONTEXT_TRAIN rows fall back to the
unchanged KNN probability, preserving the full 83-row comparison without leakage.
"""
from __future__ import annotations
import csv, json, math
from pathlib import Path
from statistics import mean, pstdev

SRC=Path('data/dashboard/wnba_v5_context_similarity.csv')
M05=Path('data/dashboard/wnba_v5_m05_report.json')
OUT=Path('data/dashboard/wnba_v5_context_challengers.csv')
IMPORTANCE=Path('data/dashboard/wnba_v5_context_feature_importance.json')
COMPARE=Path('data/dashboard/wnba_v5_model_comparison.json')
VALID=Path('data/dashboard/wnba_v5_m08_validation.json')
REPORT=Path('data/dashboard/wnba_v5_m08_report.json')
MIN_CONTEXT_TRAIN=20
EPS=1e-9
L2=0.12
LR=0.08
EPOCHS=350

FEATURE_SETS={
 'PEER_HIT':['similar_peer_hit_rate'],
 'SIMILARITY':['avg_peer_similarity'],
 'REST_FATIGUE':['rest_days','games_last_7d','games_last_14d','fatigue_score'],
 'CONTEXT_SCORE':['context_score'],
 'PEER_PLUS_REST':['similar_peer_hit_rate','avg_peer_similarity','rest_days','games_last_7d','fatigue_score'],
 'ALL_CONTEXT':['similar_peer_hit_rate','avg_peer_similarity','rest_days','games_last_7d','games_last_14d','fatigue_score','rolling5_actual_std','rolling5_trend_slope','historical_hit_rate_l5','context_score'],
}

def f(v,d=None):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except Exception:return d

def clamp(p): return max(0.02,min(0.98,p))
def logit(p):
    p=clamp(p); return math.log(p/(1-p))
def sigmoid(z):
    if z>=0:
        e=math.exp(-min(z,40)); return 1/(1+e)
    e=math.exp(max(z,-40)); return e/(1+e)

def fit(rows,features):
    # Baseline logit(KNN) is always included; missing context is median-imputed.
    med=[]
    for k in features:
        vals=[f(r.get(k)) for r in rows if f(r.get(k)) is not None]
        med.append(sorted(vals)[len(vals)//2] if vals else 0.0)
    X=[]; y=[]
    for r in rows:
        x=[logit(f(r.get('knn_probability'),0.5))]+[(f(r.get(k),med[j])) for j,k in enumerate(features)]
        X.append(x); y.append(int(float(r.get('target_win') or 0)))
    p=len(X[0]); mu=[mean(x[j] for x in X) for j in range(p)]; sd=[]
    for j in range(p):
        s=pstdev(x[j] for x in X); sd.append(s if s>1e-8 else 1.0)
    Z=[[(x[j]-mu[j])/sd[j] for j in range(p)] for x in X]
    w=[0.0]*(p+1); base=clamp(sum(y)/len(y)); w[0]=logit(base)
    for _ in range(EPOCHS):
        g=[0.0]*(p+1)
        for z,t in zip(Z,y):
            pr=sigmoid(w[0]+sum(w[j+1]*z[j] for j in range(p))); e=pr-t; g[0]+=e
            for j in range(p):g[j+1]+=e*z[j]
        g[0]/=len(Z)
        for j in range(p):g[j+1]=g[j+1]/len(Z)+L2*w[j+1]
        for j in range(p+1):w[j]-=LR*g[j]
    return {'w':w,'mu':mu,'sd':sd,'med':med,'features':features}

def pred(m,r):
    x=[logit(f(r.get('knn_probability'),0.5))]+[(f(r.get(k),m['med'][j])) for j,k in enumerate(m['features'])]
    z=[(x[j]-m['mu'][j])/m['sd'][j] for j in range(len(x))]
    return clamp(sigmoid(m['w'][0]+sum(m['w'][j+1]*z[j] for j in range(len(z)))))

def brier(ps,ys): return sum((p-y)**2 for p,y in zip(ps,ys))/len(ps)
def logloss(ps,ys): return -sum(y*math.log(max(EPS,p))+(1-y)*math.log(max(EPS,1-p)) for p,y in zip(ps,ys))/len(ps)
def ece(ps,ys,bins=5):
    out=0.0
    for b in range(bins):
        lo=b/bins; hi=(b+1)/bins; idx=[i for i,p in enumerate(ps) if lo<=p<(hi if b<bins-1 else hi+EPS)]
        if idx: out+=len(idx)/len(ps)*abs(mean(ps[i] for i in idx)-mean(ys[i] for i in idx))
    return out

def units(rows,ps):
    total=0.0; bets=0; wins=0
    for r,p in zip(rows,ps):
        if p<0.5: continue
        o=f(r.get('american_odds'))
        # M07 source has no odds; ROI is unavailable here unless odds are later joined.
        if o is None: continue
        bets+=1; y=int(float(r.get('target_win') or 0)); wins+=y
        total += (100/abs(o) if o<0 else o/100) if y else -1
    return {'bets':bets,'wins':wins,'profit_units':round(total,4) if bets else None,'roi':round(total/bets,6) if bets else None}

def metrics(rows,ps):
    ys=[int(float(r.get('target_win') or 0)) for r in rows]
    return {'n':len(rows),'brier':round(brier(ps,ys),6),'log_loss':round(logloss(ps,ys),6),'ece_5bin':round(ece(ps,ys),6),'accuracy':round(sum((p>=.5)==bool(y) for p,y in zip(ps,ys))/len(ys),6),**units(rows,ps)}

def main():
    rows=list(csv.DictReader(SRC.open(encoding='utf-8-sig',newline='')))
    rows.sort(key=lambda r:(r.get('game_date',''),r.get('game_id',''),int(float(r.get('archive_index') or 0))))
    if not rows: raise SystemExit('M08_INPUT_MISSING')
    baseline=[clamp(f(r.get('knn_probability'),0.5)) for r in rows]
    predictions={'KNN_BASELINE':baseline}
    final_models={}
    for name,features in FEATURE_SETS.items():
        ps=[]
        for i,r in enumerate(rows):
            if i<MIN_CONTEXT_TRAIN: ps.append(baseline[i]); continue
            m=fit(rows[:i],features); ps.append(pred(m,r))
        predictions[name]=ps; final_models[name]=fit(rows,features)
    rankings=[]
    base_m=metrics(rows,baseline)
    for name,ps in predictions.items():
        m=metrics(rows,ps); m['model']=name; m['brier_lift_vs_knn']=round(base_m['brier']-m['brier'],6); m['logloss_lift_vs_knn']=round(base_m['log_loss']-m['log_loss'],6)
        m['passes_core_gate']=bool(name!='KNN_BASELINE' and m['brier']<base_m['brier'] and m['log_loss']<base_m['log_loss'] and m['ece_5bin']<=base_m['ece_5bin'])
        rankings.append(m)
    rankings.sort(key=lambda x:(x['brier'],x['log_loss']))
    champion=rankings[0]['model']
    promoted=champion!='KNN_BASELINE' and rankings[0]['passes_core_gate']
    fields=['archive_index','game_date','game_id','player','stat','side','target_win']+list(predictions.keys())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for i,r in enumerate(rows):w.writerow({**{k:r.get(k) for k in fields[:7]},**{k:round(v[i],6) for k,v in predictions.items()}})
    # Context coefficient magnitudes from the full-sample diagnostic fit; never used as OOS evidence.
    imp={}
    for name,m in final_models.items():
        imp[name]=[{ 'feature':'KNN_LOGIT' if j==0 else m['features'][j-1], 'abs_standardized_weight':round(abs(m['w'][j+1]),6)} for j in range(len(m['features'])+1)]
        imp[name].sort(key=lambda x:x['abs_standardized_weight'],reverse=True)
    m05=json.loads(M05.read_text(encoding='utf-8')) if M05.exists() else {}
    report={'version':'V5','module':'V5-M08','stage':'CONTEXT_AWARE_CHALLENGER_VALIDATION','status':'READY','evaluation_rows':len(rows),'minimum_context_train_rows':MIN_CONTEXT_TRAIN,'baseline':'KNN_BASELINE','baseline_metrics':base_m,'rankings':rankings,'research_champion':champion,'context_challenger_promoted':promoted,'promotion_note':'Research-only. A context challenger must improve Brier + log loss without worsening ECE; V4 production remains unchanged.','m05_research_champion':m05.get('research_champion'),'next_module':'V5-M09 Portfolio + Decision Optimization'}
    VALID.write_text(json.dumps({'predictions_compared':list(predictions),'rankings':rankings},indent=2)+'\n',encoding='utf-8')
    IMPORTANCE.write_text(json.dumps({'diagnostic_only':True,'feature_weights':imp},indent=2)+'\n',encoding='utf-8')
    COMPARE.write_text(json.dumps({'baseline':base_m,'rankings':rankings,'champion':champion},indent=2)+'\n',encoding='utf-8')
    REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
