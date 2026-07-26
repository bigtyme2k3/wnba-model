"""Sprint 17 Commit 3.1: normalize sportsbook reaction timing.

Daily historical snapshots can create artificial 24-hour lags. This module only treats
FanDuel/DraftKings moves as synchronized when both books move in the same direction,
with reasonably similar magnitude, inside a six-hour reaction window.
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

COMPS=Path('data/market/sportsbook_movements.json')
MOVES=Path('data/market/line_movements.json')
CLV=Path('data/market/clv_results.json')
OUT=Path('data/forecast/sportsbook_leader_normalized.json')
DASH=Path('data/dashboard/wnba_sportsbook_leader_normalized_summary.json')
BOOKS=('draftkings','fanduel')
MAX_REACTION_MINUTES=360.0


def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def load(path,key):
    if not path.exists(): return []
    raw=json.loads(path.read_text(encoding='utf-8')).get(key,[])
    return raw if isinstance(raw,list) else []
def avg(values): return round(mean(values),6) if values else None
def med(values): return round(median(values),6) if values else None

def sign(value: Any) -> int:
    try: v=float(value)
    except (TypeError,ValueError): return 0
    return 1 if v>1e-9 else -1 if v<-1e-9 else 0

def magnitude_match(a: dict[str,Any], b: dict[str,Any]) -> bool:
    ap=a.get('point_movement'); bp=b.get('point_movement')
    if ap is not None and bp is not None and (abs(float(ap))>0 or abs(float(bp))>0):
        x,y=abs(float(ap)),abs(float(bp))
        return abs(x-y) <= max(1.0, 0.75*max(x,y))
    ap=a.get('price_movement'); bp=b.get('price_movement')
    if ap is None or bp is None: return False
    x,y=abs(float(ap)),abs(float(bp))
    return abs(x-y) <= max(25.0, 0.75*max(x,y))

def move_direction(row: dict[str,Any]) -> int:
    p=row.get('point_movement')
    if p is not None and abs(float(p))>1e-9: return sign(p)
    return sign(row.get('price_movement'))

def efficiency(lead_rate: float, synced_rate: float, clv_rate: float, median_lag: float|None) -> float:
    leadership=35*lead_rate
    synchronization=25*synced_rate
    clv=30*clv_rate
    speed=10 if median_lag is None else max(0,10-min(10,median_lag/36))
    return round(min(100,leadership+synchronization+clv+speed),2)

def run():
    comps=load(COMPS,'comparisons')
    moves=load(MOVES,'movements')
    move_map={(x.get('event_id'),x.get('market'),x.get('outcome_key'),x.get('bookmaker')):x for x in moves}
    records=[]
    book_stats=defaultdict(lambda:{'eligible':0,'synced':0,'leads':0,'lags':[],'isolated':0,'unresolved':0})
    market_stats=defaultdict(lambda:defaultdict(lambda:{'eligible':0,'synced':0,'leads':0,'lags':[]}))
    for c in comps:
        key=(c.get('event_id'),c.get('market'),c.get('outcome_key'))
        dk=move_map.get((*key,'draftkings'),{})
        fd=move_map.get((*key,'fanduel'),{})
        dk_moved=int(dk.get('movement_count') or 0)>0
        fd_moved=int(fd.get('movement_count') or 0)>0
        leader=c.get('first_book_to_move') if c.get('first_book_to_move') in BOOKS else None
        lag=c.get('movement_lag_minutes')
        lag=float(lag) if lag is not None else None
        same_direction=dk_moved and fd_moved and move_direction(dk)!=0 and move_direction(dk)==move_direction(fd)
        similar_magnitude=dk_moved and fd_moved and magnitude_match(dk,fd)
        if dk_moved and fd_moved and lag is not None and lag<=MAX_REACTION_MINUTES and same_direction and similar_magnitude:
            status='SYNCED'
        elif dk_moved ^ fd_moved:
            status='ISOLATED'
            leader='draftkings' if dk_moved else 'fanduel'
        else:
            status='UNRESOLVED'
        for b in BOOKS:
            book_stats[b]['eligible']+=1; market_stats[str(c.get('market'))][b]['eligible']+=1
            if status=='SYNCED':
                book_stats[b]['synced']+=1; market_stats[str(c.get('market'))][b]['synced']+=1
            elif status=='ISOLATED' and b==leader: book_stats[b]['isolated']+=1
            elif status=='UNRESOLVED': book_stats[b]['unresolved']+=1
        if status=='SYNCED' and leader in BOOKS and lag is not None:
            book_stats[leader]['leads']+=1; book_stats[leader]['lags'].append(lag)
            market_stats[str(c.get('market'))][leader]['leads']+=1; market_stats[str(c.get('market'))][leader]['lags'].append(lag)
        records.append({'event_id':key[0],'market':key[1],'outcome_key':key[2],'status':status,'leader':leader,'reaction_lag_minutes':lag if status=='SYNCED' else None,'same_direction':same_direction,'similar_magnitude':similar_magnitude,'draftkings_moved':dk_moved,'fanduel_moved':fd_moved})
    clv=[x for x in load(CLV,'records') if not x.get('is_closing_observation')]
    clv_stats=defaultdict(lambda:{'n':0,'positive':0})
    for x in clv:
        b=x.get('bookmaker')
        if b in BOOKS:
            clv_stats[b]['n']+=1; clv_stats[b]['positive']+=int(x.get('clv_class')=='POSITIVE')
    books=[]
    synced_total=sum(1 for x in records if x['status']=='SYNCED')
    for b in BOOKS:
        s=book_stats[b]; cr=clv_stats[b]
        lead_rate=s['leads']/synced_total if synced_total else 0
        synced_rate=s['synced']/s['eligible'] if s['eligible'] else 0
        clv_rate=cr['positive']/cr['n'] if cr['n'] else 0
        books.append({'bookmaker':b,'comparison_pairs':s['eligible'],'synced_pairs':s['synced'],'isolated_moves':s['isolated'],'unresolved_pairs':s['unresolved'],'synced_leads':s['leads'],'synced_lead_rate':round(lead_rate,6),'synchronization_rate':round(synced_rate,6),'average_synced_lag_minutes':avg(s['lags']),'median_synced_lag_minutes':med(s['lags']),'positive_clv_rate':round(clv_rate,6),'normalized_efficiency_score':efficiency(lead_rate,synced_rate,clv_rate,med(s['lags']))})
    books.sort(key=lambda x:-x['normalized_efficiency_score'])
    markets=[]
    for market, bm in sorted(market_stats.items()):
        rows=[]
        total=max((bm[b]['synced'] for b in BOOKS),default=0)
        for b in BOOKS:
            s=bm[b]; rows.append({'bookmaker':b,'comparison_pairs':s['eligible'],'synced_pairs':s['synced'],'synced_leads':s['leads'],'synced_lead_rate':round(s['leads']/total,6) if total else 0,'average_synced_lag_minutes':avg(s['lags']),'median_synced_lag_minutes':med(s['lags'])})
        leader=max(rows,key=lambda x:(x['synced_lead_rate'],x['synced_leads']))['bookmaker'] if total else None
        markets.append({'market':market,'synced_pairs':total,'market_leader':leader,'books':rows})
    generated=now(); OUT.parent.mkdir(parents=True,exist_ok=True); DASH.parent.mkdir(parents=True,exist_ok=True)
    payload={'generated_at_utc':generated,'reaction_window_minutes':MAX_REACTION_MINUTES,'definition':'Same-direction, similar-magnitude cross-book moves within six hours.','records':records,'sportsbooks':books,'markets':markets}
    OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    counts={k:sum(1 for x in records if x['status']==k) for k in ('SYNCED','ISOLATED','UNRESOLVED')}
    summary={'generated_at_utc':generated,'status':'READY' if records else 'STANDBY','comparison_pairs':len(records),'classification_counts':counts,'sportsbooks_ranked':len(books),'markets_ranked':len(markets),'overall_leader':books[0]['bookmaker'] if books else None,'sportsbooks':books,'market_leaders':markets,'warning':'Only synchronized moves inside the six-hour reaction window are used for lag and leadership timing.'}
    DASH.write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2)); return summary

if __name__=='__main__': run()
