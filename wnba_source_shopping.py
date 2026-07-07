from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
import pandas as pd

def read_csv(p):
    try:
        if os.path.exists(p): return pd.read_csv(p)
    except Exception: pass
    return pd.DataFrame()
def build(target):
    df=read_csv(f'data/raw/player_points_{target}.csv')
    if df.empty: df=read_csv('data/raw/player_points_today.csv')
    rows=[]
    if not df.empty:
        for _,r in df.iterrows():
            signal=str(r.get('signal','')).upper()
            price=r.get('over_price') if signal=='OVER' else r.get('under_price')
            rows.append({'player':r.get('player'),'game':r.get('game'),'stat':r.get('stat'),'signal':signal,'line':r.get('line'),'best_price':price,'best_source':r.get('book',r.get('source','current feed')),'shopping_note':'Confirm available line before action.'})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'rows':len(rows)},'best_lines':rows}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_source_shopping.json','data/dashboard/wnba_source_shopping.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Source shopping built:', build(args.date)['summary'])
if __name__=='__main__': main()
