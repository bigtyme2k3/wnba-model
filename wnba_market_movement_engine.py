"""Sprint 20 Phase 3: analyze WNBA market movement, steam, and model alignment."""
from __future__ import annotations
import argparse,json,math,statistics
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

SNAPS=Path('data/history/wnba_line_snapshots.jsonl')
RANKINGS=Path('data/warehouse/wnba_opportunity_rankings.json')
HISTORY=Path('data/history/market_movement_history.jsonl')
OUTS=[Path('data/warehouse/market_movement.json'),Path('data/dashboard/market_movement.json')]


def num(v):
    try:
        n=float(v);return n if math.isfinite(n) else None
    except Exception:return None

def norm(v):return ' '.join(str(v or '').strip().lower().replace('’',"'").split())

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

def key(row):
    return '|'.join(norm(x) for x in (row.get('date'),row.get('player'),row.get('game'),row.get('stat') or row.get('market'),row.get('signal') or row.get('side')))

def price(row):
    side=str(row.get('signal') or row.get('side') or '').upper()
    return num(row.get('over_price')) if side in {'OVER','YES'} else num(row.get('under_price')) if side in {'UNDER','NO'} else num(row.get('price') or row.get('odds'))

def directional_move(start,end,side):
    a=num(start);b=num(end)
    if a is None or b is None:return None
    return b-a if str(side).upper() in {'OVER','YES'} else a-b

def minutes_between(a,b):
    try:return max(0.0,(datetime.fromisoformat(str(b).replace('Z','+00:00'))-datetime.fromisoformat(str(a).replace('Z','+00:00'))).total_seconds()/60)
    except Exception:return None

def ranking_index():
    payload=read_json(RANKINGS,{'all_ranked':[]})
    return {key({'date':r.get('date'),'player':r.get('player'),'game':r.get('game'),'market':r.get('market'),'side':r.get('side')}):r for r in payload.get('all_ranked',[])}

def classify_model(move,ranking):
    if not ranking:return 'NO_MODEL_MATCH'
    side=str(ranking.get('side') or '').upper();m=num(move) or 0
    if abs(m)<0.25:return 'MARKET_STABLE'
    agrees=m>0
    rank=int(ranking.get('rank') or 999)
    if agrees and rank<=20:return 'MODEL_AHEAD_OF_MOVE'
    if agrees:return 'MODEL_AGREES_WITH_MARKET'
    return 'MODEL_DISAGREES_WITH_MARKET'

def build(target):
    now=datetime.now(timezone.utc).isoformat();snaps=[r for r in read_jsonl(SNAPS) if str(r.get('date'))==target];rankings=ranking_index();groups=defaultdict(list)
    for r in snaps:groups[key(r)].append(r)
    records=[]
    for market_key,rows in groups.items():
        rows=sorted(rows,key=lambda r:str(r.get('captured_at_utc') or ''))
        if not rows:continue
        opening=next((r for r in rows if norm(r.get('stage')) in {'open','opening'}),rows[0]);closing=next((r for r in reversed(rows) if norm(r.get('stage')) in {'close','closing'}),rows[-1])
        side=str(opening.get('signal') or opening.get('side') or '').upper();line_moves=[];price_moves=[]
        for a,b in zip(rows,rows[1:]):
            lm=directional_move(a.get('line'),b.get('line'),side);pm=None
            pa,pb=price(a),price(b)
            if pa is not None and pb is not None:pm=pb-pa
            if lm not in (None,0):line_moves.append(lm)
            if pm not in (None,0):price_moves.append(pm)
        total=directional_move(opening.get('line'),closing.get('line'),side) or 0.0
        span=minutes_between(opening.get('captured_at_utc'),closing.get('captured_at_utc'))
        books=sorted({str(r.get('book') or '') for r in rows if r.get('book')})
        largest=max([abs(x) for x in line_moves],default=0.0);velocity=abs(total)/(span/60) if span and span>0 else 0.0
        steam=len(books)>=2 and abs(total)>=1.0 and (span is None or span<=180)
        ranking=rankings.get(market_key);model_class=classify_model(total,ranking)
        reverse=bool(ranking and abs(total)>=0.5 and model_class=='MODEL_DISAGREES_WITH_MARKET')
        volatility=min(100.0,abs(total)*25+len(line_moves)*8+largest*12+min(20,velocity*5))
        steam_score=min(100.0,(len(books)/3)*35+min(40,abs(total)*20)+(25 if steam else 0))
        stability=max(0.0,100-volatility)
        movement_score=min(100.0,abs(total)*30+len(line_moves)*10+min(20,velocity*4))
        market_confidence=max(0.0,min(100.0,0.35*steam_score+0.25*movement_score+0.25*stability+(15 if model_class in {'MODEL_AHEAD_OF_MOVE','MODEL_AGREES_WITH_MARKET'} else 0)))
        records.append({'movement_key':market_key,'date':target,'generated_at_utc':now,'player':opening.get('player'),'game':opening.get('game'),'market':opening.get('stat') or opening.get('market'),'side':side,'opening_line':num(opening.get('line')),'current_line':num(rows[-1].get('line')),'closing_line':num(closing.get('line')),'opening_price':price(opening),'current_price':price(rows[-1]),'closing_price':price(closing),'total_directional_line_move':round(total,3),'movement_count':len(line_moves)+len(price_moves),'line_move_count':len(line_moves),'price_move_count':len(price_moves),'largest_line_jump':round(largest,3),'elapsed_minutes':None if span is None else round(span,2),'movement_velocity_per_hour':round(velocity,3),'books':books,'book_count':len(books),'steam_detected':steam,'reverse_line_movement':reverse,'model_market_classification':model_class,'market_confidence_score':round(market_confidence,2),'steam_score':round(steam_score,2),'movement_score':round(movement_score,2),'stability_score':round(stability,2),'volatility_score':round(volatility,2),'timeline':[{'captured_at_utc':r.get('captured_at_utc'),'stage':r.get('stage'),'book':r.get('book'),'line':num(r.get('line')),'price':price(r)} for r in rows]})
    records.sort(key=lambda r:(r['steam_detected'],r['market_confidence_score'],abs(r['total_directional_line_move'])),reverse=True)
    existing={r.get('movement_key'):r for r in read_jsonl(HISTORY) if r.get('movement_key')};inserted=updated=0
    material=lambda x:{k:v for k,v in x.items() if k!='generated_at_utc'}
    for row in records:
        prior=existing.get(row['movement_key'])
        if prior is None:existing[row['movement_key']]=row;inserted+=1
        elif material(prior)!=material(row):existing[row['movement_key']]=row;updated+=1
    write_jsonl(HISTORY,sorted(existing.values(),key=lambda r:(str(r.get('date')),str(r.get('movement_key')))))
    report={'generated_at_utc':now,'target_date':target,'summary':{'tracked_markets':len(records),'steam_alerts':sum(r['steam_detected'] for r in records),'reverse_line_movements':sum(r['reverse_line_movement'] for r in records),'multi_book_markets':sum(r['book_count']>=2 for r in records),'inserted_history_records':inserted,'updated_history_records':updated},'top_steam_alerts':[r for r in records if r['steam_detected']][:50],'reverse_line_movements':[r for r in records if r['reverse_line_movement']][:50],'largest_moves':sorted(records,key=lambda r:abs(r['total_directional_line_move']),reverse=True)[:50],'markets':records[:500],'methodology':{'positive_directional_move':'movement toward the selected side','steam':'two or more books plus at least 1.0 line movement within three hours','reverse_line_movement':'market moves against matched model selection by at least 0.5'}}
    for p in OUTS:p.parent.mkdir(parents=True,exist_ok=True);json.dump(report,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Market movement:',build(a.date)['summary'])
if __name__=='__main__':main()
