"""Sprint 17 Commit 3: sportsbook leader and efficiency intelligence.

Compares FanDuel and DraftKings using observed first-move timing, lag, disagreement,
CLV timing quality, and closing-line forecast error. Outputs are descriptive research
metrics and do not imply a guaranteed betting advantage.
"""
from __future__ import annotations
import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

BOOK_MOVES=Path('data/market/sportsbook_movements.json')
CLV=Path('data/market/clv_results.json')
PRED_PERF=Path('data/forecast/closing_line_predictor_performance.json')
OUT=Path('data/forecast/sportsbook_leader_intelligence.json')
DASH=Path('data/dashboard/wnba_sportsbook_leader_summary.json')
BOOKS=('draftkings','fanduel')

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def load(path,key):
    if not path.exists(): return []
    raw=json.loads(path.read_text(encoding='utf-8')).get(key,[])
    return raw if isinstance(raw,list) else []
def safe_mean(v): return round(mean(v),6) if v else None
def safe_median(v): return round(median(v),6) if v else None
def score(lead_rate,clv_rate,lag,mae):
    lead=40*lead_rate
    clv=35*clv_rate
    speed=max(0,15-min(15,(lag or 0)/4))
    accuracy=max(0,10-min(10,(mae or 0)*5))
    return round(min(100,lead+clv+speed+accuracy),2)

def run():
    comps=load(BOOK_MOVES,'comparisons')
    clv=[x for x in load(CLV,'records') if not x.get('is_closing_observation')]
    perf=load(PRED_PERF,'records')
    lead_counts=defaultdict(int); pair_counts=defaultdict(int); lags=defaultdict(list); disagreements=defaultdict(list)
    by_market=defaultdict(lambda:defaultdict(lambda:{'pairs':0,'leads':0,'lags':[],'point_gaps':[]}))
    for c in comps:
        market=str(c.get('market') or 'UNKNOWN')
        leader=c.get('first_book_to_move')
        for b in BOOKS:
            by_market[market][b]['pairs']+=1
            pair_counts[b]+=1
        if leader in BOOKS:
            lead_counts[leader]+=1; by_market[market][leader]['leads']+=1
        lag=c.get('movement_lag_minutes')
        if lag is not None and leader in BOOKS:
            lags[leader].append(float(lag)); by_market[market][leader]['lags'].append(float(lag))
        gap=c.get('current_point_disagreement')
        if gap is not None:
            disagreements[market].append(abs(float(gap)))
            for b in BOOKS: by_market[market][b]['point_gaps'].append(abs(float(gap)))
    clv_stats=defaultdict(lambda:{'n':0,'positive':0,'values':[]})
    for r in clv:
        b=r.get('bookmaker')
        if b not in BOOKS: continue
        s=clv_stats[b]; s['n']+=1; s['positive']+=int(r.get('clv_class')=='POSITIVE')
        v=r.get('implied_probability_clv')
        if v is not None: s['values'].append(float(v))
    mae=defaultdict(list)
    for r in perf:
        b=r.get('bookmaker')
        e=r.get('absolute_point_error')
        if b in BOOKS and e is not None: mae[b].append(float(e))
    books=[]
    for b in BOOKS:
        pairs=pair_counts[b]; leads=lead_counts[b]; cr=clv_stats[b]
        lead_rate=leads/pairs if pairs else 0
        clv_rate=cr['positive']/cr['n'] if cr['n'] else 0
        avg_lag=safe_mean(lags[b]); point_mae=safe_mean(mae[b])
        books.append({'bookmaker':b,'comparison_pairs':pairs,'first_moves':leads,'first_move_rate':round(lead_rate,6),'average_follow_lag_minutes':avg_lag,'median_follow_lag_minutes':safe_median(lags[b]),'clv_observations':cr['n'],'positive_clv_rate':round(clv_rate,6),'average_implied_probability_clv':safe_mean(cr['values']),'forecast_point_mae':point_mae,'efficiency_score':score(lead_rate,clv_rate,avg_lag,point_mae)})
    market_rows=[]
    for market,bookmap in by_market.items():
        row={'market':market,'average_book_point_disagreement':safe_mean(disagreements[market]),'books':[]}
        for b in BOOKS:
            s=bookmap[b]; rate=s['leads']/s['pairs'] if s['pairs'] else 0
            row['books'].append({'bookmaker':b,'pairs':s['pairs'],'first_moves':s['leads'],'first_move_rate':round(rate,6),'average_lag_minutes_when_leading':safe_mean(s['lags'])})
        row['market_leader']=max(row['books'],key=lambda x:(x['first_move_rate'],x['first_moves']))['bookmaker'] if row['books'] else None
        market_rows.append(row)
    market_rows.sort(key=lambda x:x['market'])
    books.sort(key=lambda x:-x['efficiency_score'])
    generated=now(); OUT.parent.mkdir(parents=True,exist_ok=True); DASH.parent.mkdir(parents=True,exist_ok=True)
    payload={'generated_at_utc':generated,'definition':'Observed sportsbook leadership and timing efficiency; descriptive research only.','sportsbooks':books,'markets':market_rows}
    OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    summary={'generated_at_utc':generated,'status':'READY' if comps else 'STANDBY','comparison_pairs':len(comps),'sportsbooks_ranked':len(books),'markets_ranked':len(market_rows),'overall_leader':books[0]['bookmaker'] if books else None,'sportsbooks':books,'market_leaders':market_rows,'warning':'Leadership and efficiency scores describe historical behavior and are not guaranteed betting edges.'}
    DASH.write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2)); return summary
if __name__=='__main__': run()
