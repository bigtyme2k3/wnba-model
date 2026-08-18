"""V5 shadow probability recalibration.

Fits a conservative shrinkage coefficient on canonical EARLIEST forward
predictions only, then applies it to current M11 probabilities in shadow mode.
The calibrated probability is:

    p_cal = market_p + alpha * (raw_v5_p - market_p)

alpha is selected from a fixed grid to minimize Brier score. Side-specific alpha
is allowed only when that side has >=60 resolved canonical markets; otherwise the
global alpha is used. Historical evaluation is reported both in-sample and with a
chronological expanding-date policy. This module never overwrites M11 or M10.
"""
from __future__ import annotations

import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

LEDGER=Path('data/history/wnba_v5_forward_predictions.jsonl')
LIVE=Path('data/dashboard/wnba_v5_live_inference.json')
OUT_REPORT=Path('data/dashboard/wnba_v5_probability_recalibration.json')
OUT_LIVE=Path('data/dashboard/wnba_v5_live_inference_recalibrated_shadow.json')

GRID=[i/100 for i in range(0,101)]
MIN_GLOBAL=100
MIN_SIDE=60
EPS=1e-9


def f(v,d=None):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except Exception:return d

def clamp(p): return max(0.01,min(0.99,p))
def load_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def load_ledger():
    rows=[]
    if not LEDGER.exists():return rows
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        try:rows.append(json.loads(line))
        except Exception:pass
    return rows

def ts(r):return str(r.get('prediction_generated_at_utc') or '')
def canonical_earliest(rows):
    chosen={}
    for r in rows:
        k=str(r.get('ranking_key') or '').strip()
        if not k:continue
        old=chosen.get(k)
        if old is None or ts(r)<ts(old):chosen[k]=r
    return list(chosen.values())
def resolved(rows):
    out=[]
    for r in rows:
        if r.get('target_win') not in (0,1):continue
        p=f(r.get('v5_probability'));m=f(r.get('market_probability'))
        if p is None or m is None:continue
        out.append(r)
    return out

def blend(r,a):
    p=f(r.get('v5_probability'));m=f(r.get('market_probability'))
    return clamp(m+a*(p-m))
def brier(rows,key='raw',alpha=None):
    if not rows:return None
    vals=[]
    for r in rows:
        y=int(r['target_win'])
        if key=='raw':p=f(r.get('v5_probability'))
        elif key=='market':p=f(r.get('market_probability'))
        else:p=blend(r,alpha)
        if p is not None:vals.append((p-y)**2)
    return mean(vals) if vals else None
def logloss(rows,key='raw',alpha=None):
    vals=[]
    for r in rows:
        y=int(r['target_win'])
        if key=='raw':p=f(r.get('v5_probability'))
        elif key=='market':p=f(r.get('market_probability'))
        else:p=blend(r,alpha)
        if p is not None:
            p=clamp(p);vals.append(-(y*math.log(p)+(1-y)*math.log(1-p)))
    return mean(vals) if vals else None
def fit_alpha(rows):
    if not rows:return 0.0
    scored=[(brier(rows,'blend',a),a) for a in GRID]
    scored.sort(key=lambda x:(x[0],x[1]))
    return scored[0][1]
def metrics(rows,a):
    return {
      'n':len(rows),
      'raw_v5_brier':round(brier(rows,'raw'),6) if rows else None,
      'market_brier':round(brier(rows,'market'),6) if rows else None,
      'recalibrated_brier':round(brier(rows,'blend',a),6) if rows else None,
      'raw_v5_log_loss':round(logloss(rows,'raw'),6) if rows else None,
      'market_log_loss':round(logloss(rows,'market'),6) if rows else None,
      'recalibrated_log_loss':round(logloss(rows,'blend',a),6) if rows else None,
    }
def expanding_date_eval(rows):
    dates=sorted({str(r.get('date') or '')[:10] for r in rows if r.get('date')})
    scored=[];detail=[]
    for d in dates:
        train=[r for r in rows if str(r.get('date') or '')[:10] < d]
        test=[r for r in rows if str(r.get('date') or '')[:10] == d]
        if len(train)<MIN_GLOBAL or not test:
            detail.append({'date':d,'train_n':len(train),'test_n':len(test),'status':'INSUFFICIENT_PRIOR_CANONICAL_ROWS'})
            continue
        a=fit_alpha(train)
        for r in test:scored.append((r,a))
        detail.append({'date':d,'train_n':len(train),'test_n':len(test),'alpha':a,'status':'SCORED'})
    if not scored:return {'n':0,'dates':detail}
    raw=[];market=[];cal=[]
    for r,a in scored:
        y=int(r['target_win']);p=f(r.get('v5_probability'));m=f(r.get('market_probability'));c=blend(r,a)
        raw.append((p-y)**2);market.append((m-y)**2);cal.append((c-y)**2)
    return {'n':len(scored),'raw_v5_brier':round(mean(raw),6),'market_brier':round(mean(market),6),'recalibrated_brier':round(mean(cal),6),'dates':detail}
def main():
    now=datetime.now(timezone.utc).isoformat()
    canonical=resolved(canonical_earliest(load_ledger()))
    if len(canonical)<MIN_GLOBAL:
        report={'version':'V5','module':'PROBABILITY_RECALIBRATION','status':'WAITING_FOR_100_CANONICAL_FORWARD_ROWS','generated_at_utc':now,'canonical_resolved_rows':len(canonical),'research_only':True,'production_ready':False}
        OUT_REPORT.parent.mkdir(parents=True,exist_ok=True);OUT_REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2));return
    global_alpha=fit_alpha(canonical)
    side_rows=defaultdict(list)
    for r in canonical:side_rows[str(r.get('side') or '').upper()].append(r)
    side_alpha={}
    side_metrics={}
    for side,rows in side_rows.items():
        a=fit_alpha(rows) if len(rows)>=MIN_SIDE else global_alpha
        side_alpha[side]=a
        side_metrics[side]={'alpha':a,'used_side_specific_fit':len(rows)>=MIN_SIDE,**metrics(rows,a)}
    report={
      'version':'V5','module':'PROBABILITY_RECALIBRATION','stage':'SHADOW_MARKET_SHRINKAGE','status':'READY_SHADOW',
      'generated_at_utc':now,'canonical_resolved_rows':len(canonical),'global_alpha':global_alpha,
      'interpretation':'alpha=0 means use market probability; alpha=1 means keep raw V5 probability.',
      'global_in_sample':metrics(canonical,global_alpha),'by_side':side_metrics,
      'chronological_expanding_date_evaluation':expanding_date_eval(canonical),
      'research_only':True,'production_ready':False,
      'promotion_policy':'Do not feed recalibrated probabilities into M10 until >=300 canonical resolved markets and chronological forward Brier is no worse than market.',
    }
    live=load_json(LIVE,{})
    shadow=[]
    for r in live.get('scored',[]) if isinstance(live,dict) else []:
        p=f(r.get('v5_probability'));m=f(r.get('market_implied_probability'))
        if p is None or m is None:continue
        side=str(r.get('side') or '').upper();a=side_alpha.get(side,global_alpha)
        c=clamp(m+a*(p-m))
        x=dict(r);x['raw_v5_probability']=p;x['recalibrated_v5_probability']=round(c,6);x['recalibration_alpha']=a;x['recalibrated_probability_edge']=round(c-m,6);x['recalibration_mode']='SHADOW_ONLY';shadow.append(x)
    payload={'report':report,'scored':shadow,'source_m11_report':live.get('report') if isinstance(live,dict) else None}
    OUT_REPORT.parent.mkdir(parents=True,exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    OUT_LIVE.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'canonical_resolved_rows':len(canonical),'global_alpha':global_alpha,'shadow_live_rows':len(shadow),'global_in_sample':report['global_in_sample'],'chronological':report['chronological_expanding_date_evaluation']},indent=2))
if __name__=='__main__':main()
