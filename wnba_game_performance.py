"""Build game-level performance analytics from the frozen prediction ledger."""
from __future__ import annotations
import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER=Path('data/history/wnba_game_predictions.jsonl')
OUTPUTS=[Path('data/dashboard/wnba_game_performance.json'),Path('data/warehouse/wnba_game_performance.json')]

def num(v:Any):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None

def rows():
    out=[]
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding='utf-8').splitlines():
            try:
                r=json.loads(line)
                if isinstance(r,dict):out.append(r)
            except Exception:pass
    return out

def market_summary(data:list[dict],result_key:str,rec_key:str):
    graded=[r for r in data if r.get('graded') and r.get(result_key) not in {None,'PASS','VOID'}]
    w=sum(r.get(result_key)=='WIN' for r in graded);l=sum(r.get(result_key)=='LOSS' for r in graded);p=sum(r.get(result_key)=='PUSH' for r in graded)
    decisions=w+l
    sides=defaultdict(lambda:{'wins':0,'losses':0,'pushes':0})
    for r in graded:
        side=str(r.get(rec_key) or 'UNKNOWN')
        result=str(r.get(result_key))
        if result=='WIN':sides[side]['wins']+=1
        elif result=='LOSS':sides[side]['losses']+=1
        elif result=='PUSH':sides[side]['pushes']+=1
    return {'record':{'wins':w,'losses':l,'pushes':p},'hit_rate':round(w/decisions,4) if decisions else None,'by_side':[{'side':k,**v,'hit_rate':round(v['wins']/(v['wins']+v['losses']),4) if v['wins']+v['losses'] else None} for k,v in sorted(sides.items())]}

def build():
    data=rows();graded=[r for r in data if r.get('graded')]
    margin=[num(r.get('margin_error')) for r in graded];margin=[x for x in margin if x is not None]
    total=[num(r.get('total_error')) for r in graded];total=[x for x in total if x is not None]
    over_games=sum((num(r.get('actual_total')) or -1)>(num(r.get('market_total')) or 1e9) for r in graded if num(r.get('market_total')) is not None)
    under_games=sum((num(r.get('actual_total')) or 1e9)<(num(r.get('market_total')) or -1) for r in graded if num(r.get('market_total')) is not None)
    report={
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'ok',
      'summary':{'archived_games':len(data),'graded_games':len(graded),'pending_games':sum(not r.get('graded') for r in data),'avg_margin_error':round(sum(margin)/len(margin),2) if margin else None,'avg_total_error':round(sum(total)/len(total),2) if total else None,'market_totals_over':over_games,'market_totals_under':under_games},
      'spread':market_summary(data,'spread_result','spread_recommendation'),
      'total':market_summary(data,'total_result','total_recommendation'),
      'recent_games':sorted(graded,key=lambda r:str(r.get('target_date') or ''),reverse=True)[:100],
      'largest_total_misses':sorted(graded,key=lambda r:num(r.get('total_error')) or -1,reverse=True)[:20],
      'largest_margin_misses':sorted(graded,key=lambda r:num(r.get('margin_error')) or -1,reverse=True)[:20],
      'policy':{'source':'frozen pregame game prediction ledger','grading':'final score versus frozen spread and total','pass_rows_retained':True}
    }
    for p in OUTPUTS:
        p.parent.mkdir(parents=True,exist_ok=True);json.dump(report,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    print(json.dumps(report['summary'],indent=2));return report

if __name__=='__main__':build()
