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
    for r in final:
        score=float(r.get('final_score') or 0)
        sim=float(r.get('simulation_probability') or 0)*100
        votes=[score>=68, sim>=55, r.get('final_action') in {'BET','LEAN'}]
        rows.append({'player':r.get('player'),'game':r.get('game'),'stat':r.get('stat'),'signal':r.get('signal'),'votes_for':sum(1 for v in votes if v),'votes_total':len(votes),'score':round((score+sim)/2,1)})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'rows':len(rows),'strong':sum(1 for r in rows if r.get('votes_for')>=2)},'votes':rows}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_vote_layer_v2.json','data/dashboard/wnba_vote_layer_v2.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Vote layer v2 built:', build(args.date)['summary'])
if __name__=='__main__': main()
