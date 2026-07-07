"""Final Autonomous Decision Engine: combines consensus, simulation, market, source health, and portfolio into one decision layer."""
from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone

def load(p,d):
    try:
        if os.path.exists(p): return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d
def k(r): return (str(r.get('player')),str(r.get('game')),str(r.get('stat')))
def sf(v,d=0):
    try: return float(v)
    except Exception: return d
def build(target):
    cons=load('data/warehouse/wnba_consensus_engine.json',{}).get('all_consensus',[])
    sims=load('data/warehouse/wnba_monte_carlo_engine.json',{}).get('all_simulations',[])
    market=load('data/warehouse/wnba_market_engine.json',{}).get('movements',[])
    port=load('data/warehouse/wnba_portfolio_optimizer_v2.json',{})
    sm={k(r):r for r in sims}; mm={k(r):r for r in market}
    decisions=[]
    for r in cons:
        s=sm.get(k(r),{}); m=mm.get(k(r),{})
        base=sf(r.get('consensus_score'))
        prob=sf(s.get('signal_probability'),0.5)*100
        move=sf(m.get('move'),0)
        signal=str(r.get('signal','')).upper()
        market_bonus=0
        if signal=='OVER' and move>0: market_bonus=3
        if signal=='UNDER' and move<0: market_bonus=3
        if abs(move)>=2: market_bonus+=2
        final=round(base*0.55+prob*0.35+market_bonus+sf(r.get('ev_pct'))*0.10,1)
        action='BET' if final>=78 else 'LEAN' if final>=68 else 'WATCH' if final>=58 else 'PASS'
        decisions.append({**r,'simulation_probability':round(prob/100,4),'market_move':move,'final_score':final,'final_action':action,'decision_reason':f"Consensus {base}, simulation {round(prob,1)}%, market move {move}."})
    decisions.sort(key=lambda x:x.get('final_score',0), reverse=True)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'rows':len(decisions),'bets':sum(1 for r in decisions if r.get('final_action')=='BET'),'leans':sum(1 for r in decisions if r.get('final_action')=='LEAN')},'top_decisions':decisions[:50],'portfolio_card':port.get('recommended_card',[])}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_decision_engine_final.json','data/dashboard/wnba_decision_engine_final.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Final decision engine built:', build(args.date)['summary'])
if __name__=='__main__': main()
