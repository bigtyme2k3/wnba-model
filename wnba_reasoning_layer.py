from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone

def load(p,d):
    try:
        if os.path.exists(p): return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d

def build(target):
    final=load('data/warehouse/wnba_decision_engine_final.json',{}).get('top_decisions',[])
    rows=[]
    for r in final[:50]:
        notes=[f"Action: {r.get('final_action')}",f"Score: {r.get('final_score')}",f"Line: {r.get('line')}",f"Simulation: {r.get('simulation_probability')}",f"Market: {r.get('market_move')}"]
        rows.append({'player':r.get('player'),'game':r.get('game'),'stat':r.get('stat'),'action':r.get('final_action'),'notes':notes,'guardrail':'Check latest data quality and player status.'})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'rows':len(rows)},'reasoning':rows}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_reasoning_layer.json','data/dashboard/wnba_reasoning_layer.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Reasoning layer built:', build(args.date)['summary'])
if __name__=='__main__': main()
