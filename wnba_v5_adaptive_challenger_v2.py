"""V5 Adaptive Challenger v2.

Research-only chronological evaluator for prospectively frozen context in the M12
forward ledger. It never reconstructs historical context and never changes M10/M11.
Feature groups are added cumulatively so each group must demonstrate incremental
forward value beyond the market anchor.
"""
from __future__ import annotations
import json,math
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean,pstdev

LEDGER=Path('data/history/wnba_v5_forward_predictions.jsonl')
OUT=Path('data/dashboard/wnba_v5_adaptive_challenger_v2.json')
MIN_TRAIN=60
EPS=1e-9
EPOCHS=350
LR=.035
L2=.20

GROUPS={
 'MARKET':['market_probability'],
 'FORM_SIGNAL':['market_probability','probability_edge','confidence_score','uncertainty_score','neighbor_hit_rate','average_neighbor_distance'],
 'MINUTES_ROLE':['market_probability','probability_edge','confidence_score','uncertainty_score','neighbor_hit_rate','average_neighbor_distance','ctx_minutes_l5','ctx_minutes_l10','ctx_minutes_prior_mean','ctx_starter_rate_l5','ctx_starter_rate_l10','ctx_rotation_games_prior'],
 'LINEUP_INJURY':['market_probability','probability_edge','confidence_score','uncertainty_score','neighbor_hit_rate','average_neighbor_distance','ctx_minutes_l5','ctx_minutes_l10','ctx_minutes_prior_mean','ctx_starter_rate_l5','ctx_starter_rate_l10','ctx_rotation_games_prior','ctx_lineup_confidence','ctx_rotation_multiplier'],
 'MATCHUP':['market_probability','probability_edge','confidence_score','uncertainty_score','neighbor_hit_rate','average_neighbor_distance','ctx_minutes_l5','ctx_minutes_l10','ctx_minutes_prior_mean','ctx_starter_rate_l5','ctx_starter_rate_l10','ctx_rotation_games_prior','ctx_lineup_confidence','ctx_rotation_multiplier','ctx_matchup_defense_index','ctx_matchup_multiplier','ctx_matchup_last5_allowed','ctx_matchup_last10_allowed'],
}

def f(v,d=None):
 try:
  x=float(v);return x if math.isfinite(x) else d
 except Exception:return d
def clamp(x,lo=.02,hi=.98):return max(lo,min(hi,x))
def sigmoid(z):
 if z>=0:
  e=math.exp(-min(z,40));return 1/(1+e)
 e=math.exp(max(z,-40));return e/(1+e)
def logit(p):
 p=clamp(p,.01,.99);return math.log(p/(1-p))
def load():
 if not LEDGER.exists():return []
 out=[]
 for line in LEDGER.read_text(encoding='utf-8').splitlines():
  if line.strip():
   try:out.append(json.loads(line))
   except Exception:pass
 return out
def earliest(rows):
 chosen={}
 for r in rows:
  k=str(r.get('ranking_key') or '').strip()
  if not k:continue
  old=chosen.get(k);ts=str(r.get('prediction_generated_at_utc') or '')
  if old is None or ts<str(old.get('prediction_generated_at_utc') or ''):chosen[k]=r
 return list(chosen.values())
def xrow(r,features):
 vals=[]
 for k in features:
  v=f(r.get(k))
  if v is None:return None
  vals.append(v)
 return vals
def standardize(X):
 p=len(X[0]);mu=[mean(r[j] for r in X) for j in range(p)];sd=[]
 for j in range(p):
  s=pstdev(r[j] for r in X);sd.append(s if s>1e-8 else 1.0)
 Z=[[(r[j]-mu[j])/sd[j] for j in range(p)] for r in X]
 return Z,mu,sd
def fit_logistic(X,y):
 Z,mu,sd=standardize(X);p=len(X[0]);w=[0.0]*(p+1);w[0]=logit(clamp(sum(y)/len(y),.05,.95))
 for _ in range(EPOCHS):
  g=[0.0]*(p+1)
  for z,t in zip(Z,y):
   pr=sigmoid(w[0]+sum(w[j+1]*z[j] for j in range(p)));err=pr-t;g[0]+=err
   for j in range(p):g[j+1]+=err*z[j]
  g[0]/=len(Z)
  for j in range(p):g[j+1]=g[j+1]/len(Z)+L2*w[j+1]
  for j in range(p+1):w[j]-=LR*g[j]
 return {'w':w,'mu':mu,'sd':sd}
def pred(m,x):
 z=[(x[j]-m['mu'][j])/m['sd'][j] for j in range(len(x))]
 return clamp(sigmoid(m['w'][0]+sum(m['w'][j+1]*z[j] for j in range(len(z)))))
def brier(ps,ys):return mean((p-y)**2 for p,y in zip(ps,ys)) if ps else None
def logloss(ps,ys):return -mean(y*math.log(clamp(p,EPS,1-EPS))+(1-y)*math.log(clamp(1-p,EPS,1-EPS)) for p,y in zip(ps,ys)) if ps else None
def unit_profit(odds,win):
 o=f(odds)
 if o is None or o==0:return None
 if not win:return -1.0
 return o/100 if o>0 else 100/abs(o)
def summarize(rows,key):
 if not rows:return {'n':0}
 ps=[r[key] for r in rows];ys=[r['y'] for r in rows];profits=[]
 for r in rows:
  if r[key]>=.5:
   u=unit_profit(r.get('odds'),r['y'])
   if u is not None:profits.append(u)
 return {'n':len(rows),'brier':round(brier(ps,ys),6),'log_loss':round(logloss(ps,ys),6),'accuracy':round(mean(int((p>=.5)==bool(y)) for p,y in zip(ps,ys)),6),'bets_at_0_5':len(profits),'roi_at_0_5':round(sum(profits)/len(profits),6) if profits else None}

def evaluate_group(resolved,name,features):
 eligible=[]
 for r in resolved:
  x=xrow(r,features)
  if x is not None:eligible.append((r,x,int(r['target_win'])))
 eligible.sort(key=lambda t:(str(t[0].get('date') or ''),str(t[0].get('prediction_generated_at_utc') or ''),str(t[0].get('ranking_key') or '')))
 scored=[]
 for i,(r,x,y) in enumerate(eligible):
  if i<MIN_TRAIN:continue
  X=[a[1] for a in eligible[:i]];Y=[a[2] for a in eligible[:i]]
  m=fit_logistic(X,Y);p=pred(m,x);market=clamp(f(r.get('market_probability'),.5))
  scored.append({'y':y,'odds':r.get('odds'),'MODEL':p,'MARKET':market,'side':str(r.get('side') or '').upper(),'stat':str(r.get('stat') or '').upper()})
 return {'group':name,'features':features,'eligible_rows':len(eligible),'chronologically_scored_rows':len(scored),'model':summarize(scored,'MODEL'),'market_same_rows':summarize(scored,'MARKET')}

def main():
 rows=earliest(load());resolved=[r for r in rows if r.get('target_win') in (0,1)]
 context_fields=sorted({k for r in rows for k in r.keys() if k.startswith('ctx_')})
 context_rows=sum(any(r.get(k) is not None for k in context_fields) for r in rows) if context_fields else 0
 results=[evaluate_group(resolved,name,features) for name,features in GROUPS.items()]
 for i,r in enumerate(results):
  mb=r['model'].get('brier');base=r['market_same_rows'].get('brier')
  r['beats_market_brier']=bool(mb is not None and base is not None and mb<base)
  if i:
   prev=results[i-1]['model'].get('brier');r['beats_previous_group_brier']=bool(mb is not None and prev is not None and mb<prev)
  else:r['beats_previous_group_brier']=None
 status='WAITING_FOR_CONTEXT_ROWS' if context_rows<MIN_TRAIN else 'READY_CONTEXTUAL_SHADOW'
 report={'version':'V5','module':'ADAPTIVE_CHALLENGER_V2','stage':'PROSPECTIVE_CONTEXT_ABLATION','status':status,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'research_only':True,'production_ready':False,'canonical_resolved_rows':len(resolved),'rows_with_any_frozen_context':context_rows,'minimum_context_train_rows':MIN_TRAIN,'context_fields_seen':context_fields,'results':results,'policy':'Only earliest immutable issued prediction per ranking_key is used. Context must already exist in the M12 ledger before outcome; no historical reconstruction/backfill is permitted.','promotion_policy':'No production use. Require repeated chronological superiority over MARKET and the previous surviving feature group on materially larger prospective context samples.'}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8');print(json.dumps(report,indent=2,allow_nan=False))
if __name__=='__main__':main()
