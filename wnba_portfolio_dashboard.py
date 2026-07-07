from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone

def load(p,d):
    try:
        if os.path.exists(p): return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d

def build(target):
    allocation=load('data/warehouse/wnba_risk_allocation.json',{})
    port=load('data/warehouse/wnba_portfolio_optimizer_v2.json',{})
    final=load('data/warehouse/wnba_decision_engine_final.json',{})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'allocation':allocation.get('summary',{}),'portfolio':port.get('summary',{}),'final':final.get('summary',{})},'recommended_card':port.get('recommended_card',[]),'exposure_by_team':allocation.get('exposure_by_team',{}),'allocation':allocation.get('allocation',[])}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_portfolio_dashboard.json','data/dashboard/wnba_portfolio_dashboard.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Portfolio dashboard built:', build(args.date)['summary'])
if __name__=='__main__': main()
