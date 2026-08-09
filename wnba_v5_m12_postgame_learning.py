"""V5-M12 post-game learning + forward validation.

Persists every M11 live V5 score in an append-safe ledger, grades it only when a
certified actual later appears in the V5 historical feature store, and computes
true forward-only model metrics. Predictions are never recomputed after outcome.

Outputs:
  data/history/wnba_v5_forward_predictions.jsonl
  data/dashboard/wnba_v5_forward_validation.csv
  data/dashboard/wnba_v5_forward_metrics.json
  data/dashboard/wnba_v5_learning_state.json
  data/dashboard/wnba_v5_m12_report.json
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

INFERENCE = Path('data/dashboard/wnba_v5_live_inference.json')
FEATURES = Path('data/dashboard/wnba_v5_historical_features.csv')
LEDGER = Path('data/history/wnba_v5_forward_predictions.jsonl')
OUT_CSV = Path('data/dashboard/wnba_v5_forward_validation.csv')
METRICS = Path('data/dashboard/wnba_v5_forward_metrics.json')
STATE = Path('data/dashboard/wnba_v5_learning_state.json')
REPORT = Path('data/dashboard/wnba_v5_m12_report.json')
EPS = 1e-12


def f(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def norm(v):
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def clamp(p):
    return max(EPS, min(1.0-EPS, float(p)))


def implied(o):
    o = f(o)
    if o is None or o == 0:
        return None
    return abs(o)/(abs(o)+100.0) if o < 0 else 100.0/(o+100.0)


def unit_profit(odds, win):
    o = f(odds)
    if o is None or o == 0:
        return None
    if not win:
        return -1.0
    return o/100.0 if o > 0 else 100.0/abs(o)


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def read_ledger():
    if not LEDGER.exists():
        return []
    rows=[]
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try: rows.append(json.loads(line))
            except Exception: pass
    return rows


def prediction_id(r):
    # ranking_key identifies a market observation. Probability + source timestamp
    # freeze the actual issued prediction and prevent duplicate workflow runs.
    return '|'.join([
        str(r.get('ranking_key') or ''),
        str(r.get('prediction_generated_at_utc') or ''),
        str(r.get('v5_probability') or '')
    ])


def build_actual_index():
    if not FEATURES.exists():
        return {}
    rows=list(csv.DictReader(FEATURES.open(encoding='utf-8-sig',newline='')))
    buckets=defaultdict(list)
    for r in rows:
        date=str(r.get('game_date') or '')[:10]
        player=norm(r.get('player'))
        stat=str(r.get('stat') or '').upper()
        actual=f(r.get('target_actual'))
        if date and player and stat and actual is not None:
            buckets[(date,player,stat)].append(actual)
    idx={}
    for k,vals in buckets.items():
        # ALT variants for the same player/stat/game should share the same actual.
        uniq=sorted({round(x,8) for x in vals})
        if len(uniq)==1:
            idx[k]=uniq[0]
    return idx


def outcome(actual, line, side):
    if actual is None or line is None:
        return None
    s=str(side or '').upper()
    if actual == line:
        return 'PUSH'
    if s=='OVER':
        return 'WIN' if actual > line else 'LOSS'
    if s=='UNDER':
        return 'WIN' if actual < line else 'LOSS'
    return None


def brier(rows,key):
    vals=[]
    for r in rows:
        p=f(r.get(key)); y=r.get('target_win')
        if p is not None and y in (0,1): vals.append((p-y)**2)
    return mean(vals) if vals else None


def logloss(rows,key):
    vals=[]
    for r in rows:
        p=f(r.get(key)); y=r.get('target_win')
        if p is not None and y in (0,1):
            p=clamp(p); vals.append(-(y*math.log(p)+(1-y)*math.log(1-p)))
    return mean(vals) if vals else None


def accuracy(rows,key):
    vals=[]
    for r in rows:
        p=f(r.get(key)); y=r.get('target_win')
        if p is not None and y in (0,1): vals.append(int((p>=.5)==bool(y)))
    return mean(vals) if vals else None


def ece(rows,key,bins=5):
    pairs=[]
    for r in rows:
        p=f(r.get(key)); y=r.get('target_win')
        if p is not None and y in (0,1): pairs.append((p,y))
    if not pairs:return None
    total=len(pairs); out=0.0
    for b in range(bins):
        lo=b/bins; hi=(b+1)/bins
        q=[(p,y) for p,y in pairs if lo<=p<(hi if b<bins-1 else hi+EPS)]
        if q: out += len(q)/total * abs(mean(p for p,_ in q)-mean(y for _,y in q))
    return out


def r6(v):
    return None if v is None else round(v,6)


def main():
    now=datetime.now(timezone.utc).isoformat()
    payload=read_json(INFERENCE,{})
    inf_report=payload.get('report',{}) if isinstance(payload,dict) else {}
    current=payload.get('scored',[]) if isinstance(payload,dict) else []

    ledger=read_ledger()
    seen={prediction_id(r) for r in ledger}
    added=0
    generated=inf_report.get('generated_at_utc')
    for s in current:
        row={
            'ranking_key':s.get('ranking_key'),
            'prediction_generated_at_utc':generated,
            'date':str(s.get('date') or '')[:10],
            'player':s.get('player'),'game':s.get('game'),'stat':str(s.get('market') or '').upper(),
            'side':str(s.get('side') or '').upper(),'line':f(s.get('line')),'odds':f(s.get('odds')),
            'book':s.get('best_book'),'model':s.get('model') or 'KNN',
            'v5_probability':f(s.get('v5_probability')),'knn_probability':f(s.get('knn_probability')),
            'market_probability':f(s.get('market_implied_probability')),
            'probability_edge':f(s.get('probability_edge')),
            'confidence_score':f(s.get('confidence_score')),
            'uncertainty_score':f(s.get('uncertainty_score')),
            'neighbor_count':s.get('neighbor_count'),'neighbor_hit_rate':f(s.get('neighbor_hit_rate')),
            'average_neighbor_distance':f(s.get('average_neighbor_distance')),
            'actual':None,'outcome':'PENDING','target_win':None,'graded_at_utc':None,
            'research_only':True,
        }
        pid=prediction_id(row); row['prediction_id']=pid
        if pid not in seen:
            ledger.append(row);seen.add(pid);added+=1

    actuals=build_actual_index(); newly_graded=0
    for r in ledger:
        if r.get('outcome') not in (None,'','PENDING'):
            continue
        key=(str(r.get('date') or '')[:10],norm(r.get('player')),str(r.get('stat') or '').upper())
        actual=actuals.get(key)
        out=outcome(actual,f(r.get('line')),r.get('side'))
        if out:
            r['actual']=actual;r['outcome']=out;r['graded_at_utc']=now
            r['target_win']=1 if out=='WIN' else (0 if out=='LOSS' else None)
            newly_graded+=1

    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    with LEDGER.open('w',encoding='utf-8') as h:
        for r in sorted(ledger,key=lambda x:(x.get('date',''),x.get('ranking_key',''),x.get('prediction_generated_at_utc',''))):
            h.write(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n')

    resolved=[r for r in ledger if r.get('outcome') in {'WIN','LOSS','PUSH'}]
    binary=[r for r in resolved if r.get('target_win') in (0,1)]
    pending=[r for r in ledger if r.get('outcome')=='PENDING']

    # Forward betting evidence at the same 0.5 research threshold used in M05.
    bets=[]
    for r in binary:
        p=f(r.get('v5_probability')); o=f(r.get('odds'))
        if p is not None and p>=.5 and o is not None:
            profit=unit_profit(o,int(r['target_win']))
            if profit is not None:bets.append(profit)

    posedge=[]
    for r in binary:
        p=f(r.get('v5_probability')); mp=f(r.get('market_probability'));o=f(r.get('odds'))
        if p is not None and mp is not None and p>mp and o is not None:
            profit=unit_profit(o,int(r['target_win']))
            if profit is not None:posedge.append(profit)

    metrics={
        'forward_predictions':len(ledger),'resolved_predictions':len(resolved),'binary_graded_predictions':len(binary),
        'pushes':sum(r.get('outcome')=='PUSH' for r in resolved),'pending_predictions':len(pending),
        'v5_brier':r6(brier(binary,'v5_probability')),'market_brier':r6(brier(binary,'market_probability')),
        'v5_log_loss':r6(logloss(binary,'v5_probability')),'market_log_loss':r6(logloss(binary,'market_probability')),
        'v5_ece_5bin':r6(ece(binary,'v5_probability')),'market_ece_5bin':r6(ece(binary,'market_probability')),
        'v5_accuracy':r6(accuracy(binary,'v5_probability')),'market_accuracy':r6(accuracy(binary,'market_probability')),
        'model_bets_at_0_5':len(bets),'model_profit_units_at_0_5':round(sum(bets),4) if bets else 0.0,
        'model_roi_at_0_5':r6(sum(bets)/len(bets)) if bets else None,
        'positive_edge_bets':len(posedge),'positive_edge_profit_units':round(sum(posedge),4) if posedge else 0.0,
        'positive_edge_roi':r6(sum(posedge)/len(posedge)) if posedge else None,
    }

    # Production gate remains deliberately conservative and cannot be bypassed by M12.
    minimum_rows=300; minimum_clv=60.0; explicit_clv_coverage=0.0
    promotion_ready=(len(binary)>=minimum_rows and explicit_clv_coverage>=minimum_clv and
                     metrics['v5_brier'] is not None and metrics['market_brier'] is not None and
                     metrics['v5_brier']<metrics['market_brier'])
    status='READY_FORWARD_LEARNING' if ledger else 'WAITING_FOR_M11_PREDICTIONS'
    if ledger and not binary: status='WAITING_FOR_CERTIFIED_OUTCOMES'

    state={
        'version':'V5','module':'V5-M12','status':status,'generated_at_utc':now,
        'research_champion':'KNN','new_predictions_appended':added,'newly_graded':newly_graded,
        'metrics':metrics,
        'promotion_gate':{
            'production_ready':promotion_ready,'minimum_forward_rows':minimum_rows,
            'current_forward_rows':len(binary),'minimum_explicit_clv_coverage_pct':minimum_clv,
            'explicit_clv_coverage_pct':explicit_clv_coverage,
            'reason':'V4 remains production champion until >=300 graded forward predictions, >=60% explicit CLV coverage, and V5 beats market forward Brier.'
        },
        'learning_policy':'Append predictions before outcomes; grade only from later certified actuals; never rewrite issued probabilities.',
        'next_module':'V5-M13 Production Readiness + Shadow Monitoring'
    }
    report=dict(state)
    report['pending_examples']=[{'date':r.get('date'),'player':r.get('player'),'stat':r.get('stat'),'side':r.get('side')} for r in pending[:10]]

    OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
    fields=['prediction_id','ranking_key','prediction_generated_at_utc','date','player','game','stat','side','line','odds','book','model','v5_probability','market_probability','probability_edge','confidence_score','uncertainty_score','actual','outcome','target_win','graded_at_utc']
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows([{k:r.get(k) for k in fields} for r in ledger])
    METRICS.write_text(json.dumps(metrics,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    STATE.write_text(json.dumps(state,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
