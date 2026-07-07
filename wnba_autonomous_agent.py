from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone

def load(p,d):
    try:
        if os.path.exists(p): return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d

def build(target):
    final=load('data/warehouse/wnba_decision_engine_final.json',{})
    health=load('data/warehouse/wnba_source_health.json',{})
    risk=load('data/warehouse/wnba_risk_allocation.json',{})
    reasoning=load('data/warehouse/wnba_reasoning_layer.json',{})
    issues=[]
    if health.get('summary',{}).get('degraded_or_missing',0)>2: issues.append('source_health_degraded')
    if final.get('summary',{}).get('rows',0)==0: issues.append('no_final_decisions')
    action='publish_card' if not issues and final.get('summary',{}).get('bets',0)>0 else 'publish_watchlist'
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'agent_action':action,'issues':issues,'summary':{'final':final.get('summary',{}),'risk':risk.get('summary',{}),'reasoning_rows':reasoning.get('summary',{}).get('rows',0)},'top_decisions':final.get('top_decisions',[])[:12]}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_autonomous_agent.json','data/dashboard/wnba_autonomous_agent.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Autonomous agent built:', build(args.date)['agent_action'])
if __name__=='__main__': main()
