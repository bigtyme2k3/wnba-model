from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone

def load(p,d):
    try:
        if os.path.exists(p): return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d

def num(v,d=0.0):
    try: return float(v)
    except Exception: return d

def build(target,capital=500.0):
    card=load('data/warehouse/wnba_portfolio_optimizer_v2.json',{}).get('recommended_card',[])
    exposure={}
    rows=[]
    total=0.0
    for r in card:
        amount=min(num(r.get('recommended_stake'),0), capital*0.03)
        total+=amount
        team=str(r.get('team') or 'UNK')
        exposure[team]=round(exposure.get(team,0)+amount,2)
        rows.append({**r,'capped_amount':round(amount,2),'unit_multiple':round(amount/20,2),'exposure_bucket':team})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'capital':capital,'summary':{'card_size':len(rows),'total_exposure':round(total,2),'exposure_pct':round(total/max(1,capital),4),'teams':len(exposure)},'exposure_by_team':exposure,'allocation':rows,'rules':{'max_single_position_pct':0.03,'max_card_pct':0.18,'unit_size':20}}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_risk_allocation.json','data/dashboard/wnba_risk_allocation.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); ap.add_argument('--capital',type=float,default=500); args=ap.parse_args(); print('Risk allocation built:', build(args.date,args.capital)['summary'])
if __name__=='__main__': main()
