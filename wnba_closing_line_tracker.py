"""M16 closing-line-value tracker for props and game markets."""
from __future__ import annotations
import argparse, json, math, os
from datetime import date, datetime, timezone
from typing import Any
import pandas as pd

SNAPS="data/history/wnba_line_snapshots.jsonl"; HIST="data/history/wnba_model_history.jsonl"

def sf(v,d=None):
    try:
        n=float(v); return n if math.isfinite(n) else d
    except Exception: return d

def clean(v: Any) -> Any:
    if isinstance(v,dict): return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)): return [clean(x) for x in v]
    if isinstance(v,float): return v if math.isfinite(v) else None
    if v is None or isinstance(v,(str,int,bool)): return v
    try:
        if pd.isna(v): return None
    except Exception: pass
    try:
        if hasattr(v,'item'): return clean(v.item())
    except Exception: pass
    return str(v)

def read_jsonl(path):
    out=[]
    if os.path.exists(path):
        for line in open(path,encoding='utf-8'):
            try: out.append(json.loads(line))
            except Exception: pass
    return out

def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',encoding='utf-8') as f:
        for row in rows: f.write(json.dumps(clean(row),separators=(',',':'),allow_nan=False)+'\n')

def load_points(target):
    for p in (f'data/raw/player_points_{target}.csv','data/raw/player_points_today.csv'):
        if os.path.exists(p):
            try: return pd.read_csv(p)
            except Exception: pass
    return pd.DataFrame()

def market_key(row):
    return '|'.join(str(clean(row.get(k)) or '').strip().lower() for k in ('player','game','stat','signal'))

def append_snapshot(target,stage):
    df=load_points(target); now=datetime.now(timezone.utc).isoformat(); existing=read_jsonl(SNAPS); seen={x.get('snapshot_key') for x in existing}; added=[]
    if not df.empty:
        for _,source in df.iterrows():
            r=clean(source.to_dict()); base={"date":target,"stage":stage,"captured_at_utc":now,"player":r.get('player'),"game":r.get('game'),"stat":r.get('stat'),"signal":r.get('signal'),"line":r.get('line'),"over_price":r.get('over_price'),"under_price":r.get('under_price'),"book":r.get('book') or r.get('source')}
            base['market_key']=market_key(base); base['snapshot_key']=f"{target}|{stage}|{base['market_key']}|{base.get('book') or ''}"
            if base['snapshot_key'] not in seen: added.append(base); seen.add(base['snapshot_key'])
    if added:
        os.makedirs(os.path.dirname(SNAPS),exist_ok=True)
        with open(SNAPS,'a',encoding='utf-8') as f:
            for row in added: f.write(json.dumps(clean(row),separators=(',',':'),allow_nan=False)+'\n')
    return added

def price_for(row):
    return sf(row.get('over_price') if str(row.get('signal','')).upper() in {'OVER','YES'} else row.get('under_price'))

def implied(odds):
    odds=sf(odds)
    if odds is None or odds==0:return None
    return abs(odds)/(abs(odds)+100) if odds<0 else 100/(odds+100)

def line_clv(open_line,close_line,signal):
    if open_line is None or close_line is None:return None
    return close_line-open_line if str(signal).upper() in {'OVER','YES'} else open_line-close_line

def build(target,stage):
    added=append_snapshot(target,stage); snaps=[s for s in read_jsonl(SNAPS) if s.get('date')==target]; hist=read_jsonl(HIST)
    by_key={}
    for s in snaps: by_key.setdefault(s.get('market_key') or market_key(s),[]).append(s)
    records=[]; changed=0
    for r in hist:
        if r.get('date')!=target: continue
        key=market_key(r); options=by_key.get(key,[])
        if not options: continue
        opens=[x for x in options if x.get('stage') in {'open','bet','snapshot'}] or options[:1]; closes=[x for x in options if x.get('stage') in {'close','closing'}]
        if not closes: continue
        o=opens[0]; c=closes[-1]; ol=sf(r.get('line'),sf(o.get('line'))); cl=sf(c.get('line')); op=price_for({**o,'signal':r.get('signal')}); cp=price_for({**c,'signal':r.get('signal')})
        lclv=line_clv(ol,cl,r.get('signal')); pclv=(implied(op)-implied(cp)) if implied(op) is not None and implied(cp) is not None else None
        r.update({'closing_line':cl,'closing_price':cp,'line_clv':round(lclv,3) if lclv is not None else None,'price_clv':round(pclv,5) if pclv is not None else None,'clv_grade':'POSITIVE' if (lclv or 0)>0 or (pclv or 0)>0 else 'NEGATIVE' if (lclv or 0)<0 or (pclv or 0)<0 else 'NEUTRAL'})
        records.append({k:r.get(k) for k in ('player','game','stat','signal','line','closing_line','line_clv','price_clv','clv_grade')}); changed+=1
    if changed: write_jsonl(HIST,hist)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'stage':stage,'status':'ok','summary':{'snapshots_added':len(added),'total_snapshots':len(snaps),'graded_clv':len(records),'positive':sum(x['clv_grade']=='POSITIVE' for x in records),'negative':sum(x['clv_grade']=='NEGATIVE' for x in records),'neutral':sum(x['clv_grade']=='NEUTRAL' for x in records)},'records':records}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ('data/warehouse/wnba_clv_summary.json','data/dashboard/wnba_clv_summary.json'): json.dump(clean(report),open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); ap.add_argument('--stage',default='snapshot'); a=ap.parse_args(); print('CLV tracker:',build(a.date,a.stage)['summary'])
if __name__=='__main__': main()
