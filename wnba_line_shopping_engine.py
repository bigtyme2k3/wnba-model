"""Sprint 20 Phase 1: select the best WNBA line and price across DK, FD, and Fanatics."""
from __future__ import annotations
import argparse, json, math, os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

CONSENSUS=Path('data/warehouse/wnba_sportsbook_consensus.json')
HISTORY=Path('data/history/line_shopping_history.jsonl')
OUTS=[Path('data/warehouse/market_intelligence.json'),Path('data/dashboard/market_intelligence.json')]
ALLOWED={'DraftKings','FanDuel','Fanatics'}

def num(v):
    try:
        n=float(v);return n if math.isfinite(n) else None
    except Exception:return None

def implied(o):
    x=num(o)
    if x is None or x==0:return None
    return abs(x)/(abs(x)+100) if x<0 else 100/(x+100)

def decimal(o):
    p=implied(o);return None if not p else 1/p

def read_json(path,default):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def read_jsonl(path):
    out=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                row=json.loads(line)
                if isinstance(row,dict):out.append(row)
            except Exception:pass
    return out

def write_jsonl(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in rows),encoding='utf-8')

def better_price(a,b):
    if a is None:return b
    if b is None:return a
    return a if float(a)>=float(b) else b

def choose_best(market,side):
    price_key='best_over_price' if side=='OVER' else 'best_under_price'
    book_key='best_over_book' if side=='OVER' else 'best_under_book'
    return market.get(book_key),num(market.get(price_key))

def build(target):
    source=read_json(CONSENSUS,{'markets':[],'summary':{}})
    now=datetime.now(timezone.utc).isoformat();records=[]
    for market in source.get('markets',[]):
        books=[b for b in market.get('books',[]) if b in ALLOWED]
        for side in ('OVER','UNDER'):
            best_book,best_odds=choose_best(market,side)
            if best_book not in ALLOWED:best_book=None
            consensus_prob=num(market.get('consensus_over_probability' if side=='OVER' else 'consensus_under_probability'))
            best_prob=implied(best_odds)
            rec={
                'shopping_key':'|'.join(str(x or '').lower() for x in (target,market.get('player'),market.get('game'),market.get('stat'),side)),
                'date':target,'captured_at_utc':now,'player':market.get('player'),'game':market.get('game'),'market':market.get('stat'),'side':side,
                'book_count':int(market.get('book_count') or len(books)),'books':books,'consensus_line':num(market.get('consensus_line')),
                'line_range':num(market.get('line_range')) or 0.0,'consensus_implied_probability':consensus_prob,
                'best_book':best_book,'best_line':num(market.get('consensus_line')),'best_odds':best_odds,'best_decimal_odds':decimal(best_odds),
                'best_implied_probability':best_prob,'price_advantage':(consensus_prob-best_prob) if consensus_prob is not None and best_prob is not None else None,
                'market_disagreement_score':min(1.0,(num(market.get('line_range')) or 0)/2.0),'status':'multi_book' if len(books)>=2 else 'single_book'
            }
            records.append(rec)
    records.sort(key=lambda r:(r['book_count'],r['market_disagreement_score'],r.get('price_advantage') or -9),reverse=True)
    existing={r.get('shopping_key'):r for r in read_jsonl(HISTORY) if r.get('shopping_key')};inserted=updated=0
    for rec in records:
        prior=existing.get(rec['shopping_key']);material=lambda x:{k:v for k,v in x.items() if k!='captured_at_utc'}
        if prior is None:existing[rec['shopping_key']]=rec;inserted+=1
        elif material(prior)!=material(rec):existing[rec['shopping_key']]=rec;updated+=1
    write_jsonl(HISTORY,sorted(existing.values(),key=lambda r:(str(r.get('date')),str(r.get('shopping_key')))))
    by_book={b:sum(r.get('best_book')==b for r in records) for b in sorted(ALLOWED)}
    report={'generated_at_utc':now,'target_date':target,'source':str(CONSENSUS),'summary':{'markets':len(records),'multi_book_markets':sum(r['status']=='multi_book' for r in records),'three_book_markets':sum(r['book_count']>=3 for r in records),'inserted_history_records':inserted,'updated_history_records':updated,'best_book_counts':by_book},'top_line_differences':sorted(records,key=lambda r:r.get('line_range') or 0,reverse=True)[:50],'top_price_advantages':sorted(records,key=lambda r:r.get('price_advantage') or -9,reverse=True)[:50],'markets':records[:500]}
    for path in OUTS:
        path.parent.mkdir(parents=True,exist_ok=True);json.dump(report,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Line shopping:',build(a.date)['summary'])
if __name__=='__main__':main()
