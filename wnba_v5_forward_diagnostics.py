"""Diagnose V5 true forward performance without treating repeated refresh snapshots as independent bets.

Reads the immutable M12 ledger and publishes two views:
1) all frozen prediction snapshots (diagnostic only), and
2) one canonical EARLIEST issued prediction per ranking_key (primary forward evidence).

Breakdowns are side/stat/probability/edge/odds/confidence/date. No prediction is
rewritten and no model selection is performed here.
"""
from __future__ import annotations

import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

LEDGER=Path('data/history/wnba_v5_forward_predictions.jsonl')
OUT=Path('data/dashboard/wnba_v5_forward_diagnostics.json')


def f(v,d=None):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except Exception:return d

def unit_profit(odds,win):
    o=f(odds)
    if o is None or o==0:return None
    if not win:return -1.0
    return o/100.0 if o>0 else 100.0/abs(o)
def load():
    rows=[]
    if not LEDGER.exists():return rows
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try: rows.append(json.loads(line))
            except Exception: pass
    return rows

def ts(r): return str(r.get('prediction_generated_at_utc') or '')
def canonical_earliest(rows):
    chosen={}
    for r in rows:
        k=str(r.get('ranking_key') or '').strip()
        if not k: continue
        p=chosen.get(k)
        if p is None or ts(r)<ts(p):chosen[k]=r
    return list(chosen.values())
def prob_band(p):
    p=f(p)
    if p is None:return 'UNKNOWN'
    if p>=.70:return '70%+'
    if p>=.65:return '65-69.9%'
    if p>=.60:return '60-64.9%'
    if p>=.55:return '55-59.9%'
    if p>=.50:return '50-54.9%'
    if p>=.45:return '45-49.9%'
    return '<45%'
def edge_band(e):
    e=f(e)
    if e is None:return 'UNKNOWN'
    if e>=.15:return '15%+'
    if e>=.10:return '10-14.9%'
    if e>=.05:return '5-9.9%'
    if e>=.02:return '2-4.9%'
    if e>=0:return '0-1.9%'
    if e>=-.05:return '-0.1_TO_-5%'
    return '<-5%'
def odds_band(o):
    o=f(o)
    if o is None:return 'UNKNOWN'
    if o>=100:return 'PLUS'
    if o>-150:return '-101_TO_-149'
    if o>-300:return '-150_TO_-299'
    if o>-500:return '-300_TO_-499'
    return '-500_OR_SHORTER'
def conf_band(c):
    c=f(c)
    if c is None:return 'UNKNOWN'
    if c>=.70:return '70%+'
    if c>=.60:return '60-69.9%'
    if c>=.50:return '50-59.9%'
    if c>=.40:return '40-49.9%'
    return '<40%'
def resolved(rows):return [r for r in rows if r.get('target_win') in (0,1)]
def metrics(rows):
    q=resolved(rows); n=len(q)
    if not n:return {'n':0}
    wins=sum(int(r['target_win']) for r in q)
    b=[];mb=[];profits=[];edge_profits=[]
    for r in q:
        y=int(r['target_win']);p=f(r.get('v5_probability'));mp=f(r.get('market_probability'));o=f(r.get('odds'))
        if p is not None:b.append((p-y)**2)
        if mp is not None:mb.append((mp-y)**2)
        if p is not None and p>=.5 and o is not None:
            x=unit_profit(o,y)
            if x is not None:profits.append(x)
        if p is not None and mp is not None and p>mp and o is not None:
            x=unit_profit(o,y)
            if x is not None:edge_profits.append(x)
    return {
      'n':n,'wins':wins,'losses':n-wins,'win_rate':round(wins/n,6),
      'v5_brier':round(mean(b),6) if b else None,'market_brier':round(mean(mb),6) if mb else None,
      'brier_delta_vs_market':round(mean(b)-mean(mb),6) if b and mb else None,
      'model_bets_at_0_5':len(profits),'model_roi_at_0_5':round(sum(profits)/len(profits),6) if profits else None,
      'positive_edge_bets':len(edge_profits),'positive_edge_roi':round(sum(edge_profits)/len(edge_profits),6) if edge_profits else None,
    }
def breakdown(rows,keyfn,min_n=1):
    buckets=defaultdict(list)
    for r in rows:buckets[str(keyfn(r))].append(r)
    out=[]
    for k,v in buckets.items():
        m=metrics(v)
        if m.get('n',0)>=min_n:out.append({'segment':k,**m})
    return sorted(out,key=lambda x:(-x.get('n',0),x['segment']))
def view(rows):
    rr=resolved(rows)
    return {
      'overall':metrics(rows),
      'by_side':breakdown(rr,lambda r:str(r.get('side') or 'UNKNOWN').upper()),
      'by_stat':breakdown(rr,lambda r:str(r.get('stat') or 'UNKNOWN').upper()),
      'by_probability_band':breakdown(rr,lambda r:prob_band(r.get('v5_probability'))),
      'by_edge_band':breakdown(rr,lambda r:edge_band(r.get('probability_edge'))),
      'by_odds_band':breakdown(rr,lambda r:odds_band(r.get('odds'))),
      'by_confidence_band':breakdown(rr,lambda r:conf_band(r.get('confidence_score'))),
      'by_date':breakdown(rr,lambda r:str(r.get('date') or '')[:10]),
    }
def main():
    rows=load(); unique=canonical_earliest(rows)
    multiplicity=defaultdict(int)
    for r in rows:
        k=str(r.get('ranking_key') or '').strip()
        if k:multiplicity[k]+=1
    mult=list(multiplicity.values())
    report={
      'version':'V5','module':'FORWARD_DIAGNOSTICS','generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'ledger_rows':len(rows),'unique_ranking_keys':len(unique),
      'snapshot_multiplicity':{
        'average_snapshots_per_ranking_key':round(sum(mult)/len(mult),4) if mult else None,
        'max_snapshots_per_ranking_key':max(mult) if mult else 0,
        'ranking_keys_with_multiple_snapshots':sum(x>1 for x in mult),
      },
      'primary_evidence_policy':'Use earliest immutable issued prediction per ranking_key so repeated refreshes are not counted as independent bets.',
      'all_snapshots_diagnostic_only':view(rows),
      'canonical_earliest_prediction_per_market':view(unique),
      'candidate_segments_min100':[],
    }
    candidates=[]
    primary=report['canonical_earliest_prediction_per_market']
    for dim in ('by_side','by_stat','by_probability_band','by_edge_band','by_odds_band','by_confidence_band'):
        for s in primary[dim]:
            if s.get('n',0)>=100:
                candidates.append({'dimension':dim,'segment':s['segment'],**{k:v for k,v in s.items() if k!='segment'}})
    report['candidate_segments_min100']=sorted(candidates,key=lambda x:((x.get('brier_delta_vs_market') or 99),-(x.get('positive_edge_roi') or -99),-x.get('n',0)))
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('ledger_rows','unique_ranking_keys','snapshot_multiplicity','primary_evidence_policy')},indent=2))
if __name__=='__main__':main()
