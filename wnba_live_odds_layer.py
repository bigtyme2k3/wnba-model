"""Live odds layer using free/manual/cached sources first and Odds API only when upstream workflow enables it."""
from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
import pandas as pd

def load_json(p,d):
    try:
        if os.path.exists(p): return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d

def read_csv(p):
    try:
        if os.path.exists(p): return pd.read_csv(p)
    except Exception: pass
    return pd.DataFrame()

def build(target):
    odds=read_csv(f'data/raw/odds_{target}.csv')
    if odds.empty: odds=read_csv('data/raw/odds_today.csv')
    manual=read_csv('data/manual/wnba_manual_odds.csv')
    status=load_json('data/raw/odds_source_status.json',{})
    rows=[]
    source=status.get('selected_source','unknown')
    if not odds.empty:
        for _,r in odds.iterrows():
            rows.append({'game_date':r.get('game_date',target),'home_team':r.get('home_team'),'away_team':r.get('away_team'),'spread_home':r.get('spread_home'),'total':r.get('total'),'ml_home':r.get('ml_home'),'ml_away':r.get('ml_away'),'num_books':r.get('num_books',1),'best_source':r.get('source',source),'freshness':'current_or_cached'})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'rows':len(rows),'source':source,'manual_rows':0 if manual.empty else len(manual),'status':status.get('status','unknown')},'odds':rows,'policy':'Free/manual/cache first. Paid API is optional only.'}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_live_odds_layer.json','data/dashboard/wnba_live_odds_layer.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Live odds layer built:', build(args.date)['summary'])
if __name__=='__main__': main()
