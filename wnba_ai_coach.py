"""AI Coach report: plain-English recommendations from final decision, portfolio, market, and simulation data."""
from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone

def load(p,d):
    try:
        if os.path.exists(p): return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d
def build(target):
    dec=load('data/warehouse/wnba_decision_engine_final.json',{})
    port=load('data/warehouse/wnba_portfolio_optimizer_v2.json',{})
    rows=[]
    for r in dec.get('top_decisions',[])[:30]:
        action=r.get('final_action') or r.get('recommendation')
        player=r.get('player'); stat=r.get('stat'); sig=r.get('signal')
        why=[f"Final score {r.get('final_score', r.get('consensus_score'))}",f"Monte Carlo probability {r.get('simulation_probability')}",f"Market move {r.get('market_move')}",f"Engine agreement {r.get('engine_agreement')}"]
        rows.append({'player':player,'game':r.get('game'),'play':f"{player} {stat} {sig}",'action':action,'score':r.get('final_score',r.get('consensus_score')),'coach_note':'; '.join(why),'risk_note':'Confirm book line and player status before placing any wager.'})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'notes':len(rows),'portfolio_card_size':port.get('summary',{}).get('card_size',0)},'coach_cards':rows}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_ai_coach.json','data/dashboard/wnba_ai_coach.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('AI coach built:', build(args.date)['summary'])
if __name__=='__main__': main()
