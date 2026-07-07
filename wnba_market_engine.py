"""Market movement engine from saved line snapshots."""
from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
from collections import defaultdict
SNAPS='data/history/wnba_line_snapshots.jsonl'
def sf(v,d=0.0):
    try:
        if v is None or v=='' or str(v).lower()=='nan': return d
        return float(v)
    except Exception: return d
def read_rows(target):
    rows=[]
    if os.path.exists(SNAPS):
        for line in open(SNAPS,encoding='utf-8'):
            try:
                r=json.loads(line)
                if r.get('date')==target: rows.append(r)
            except Exception: pass
    return rows
def build(target):
    g=defaultdict(list)
    for r in read_rows(target): g[(r.get('player'),r.get('game'),r.get('stat'))].append(r)
    moves=[]
    for k,vals in g.items():
        vals=sorted(vals,key=lambda x:x.get('captured_at_utc',''))
        first,last=vals[0],vals[-1]
        move=sf(last.get('line'))-sf(first.get('line'))
        label='UP' if move>=1 else 'DOWN' if move<=-1 else 'STABLE'
        moves.append({'player':k[0],'game':k[1],'stat':k[2],'open_line':first.get('line'),'current_line':last.get('line'),'move':round(move,2),'snapshots':len(vals),'movement_label':label,'first_seen':first.get('captured_at_utc'),'last_seen':last.get('captured_at_utc')})
    moves.sort(key=lambda r:abs(sf(r.get('move'))), reverse=True)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'markets':len(moves),'up':sum(1 for r in moves if r.get('movement_label')=='UP'),'down':sum(1 for r in moves if r.get('movement_label')=='DOWN')},'movements':moves}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_market_engine.json','data/dashboard/wnba_market_engine.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Market engine built:', build(args.date)['summary'])
if __name__=='__main__': main()
