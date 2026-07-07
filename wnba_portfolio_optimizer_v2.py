"""Portfolio Optimizer v2: ranks a card using consensus, Monte Carlo probability, and simple exposure limits."""
from __future__ import annotations
import argparse,json,os,math
from datetime import date,datetime,timezone

def load(p,d):
    try:
        if os.path.exists(p):
            return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d
def key(r): return (str(r.get('player')),str(r.get('game')),str(r.get('stat')))
def kelly(prob, odds=-110):
    b=100/abs(odds) if odds<0 else odds/100
    q=1-prob
    return max(0,min(0.05,(b*prob-q)/b))*0.5
def build(target,bankroll=500.0):
    cons=load('data/warehouse/wnba_consensus_engine.json',{}).get('all_consensus',[])
    sims=load('data/warehouse/wnba_monte_carlo_engine.json',{}).get('all_simulations',[])
    sim_map={key(r):r for r in sims}
    candidates=[]; team_count={}; game_count={}
    for r in cons:
        if r.get('recommendation') not in {'BET','LEAN'}: continue
        sm=sim_map.get(key(r),{})
        prob=float(sm.get('signal_probability') or 0.5)
        score=(float(r.get('consensus_score') or 0)*0.55)+(prob*100*0.35)+(float(r.get('ev_pct') or 0)*0.10)
        stake=round(bankroll*kelly(prob),2)
        if stake<=0: stake=10 if r.get('recommendation')=='BET' else 5
        candidates.append({**r,'simulation_probability':round(prob,4),'portfolio_score':round(score,1),'recommended_stake':stake,'risk_band':sm.get('risk_band','MED')})
    candidates.sort(key=lambda x:x.get('portfolio_score',0),reverse=True)
    card=[]
    for r in candidates:
        team=r.get('team') or 'UNK'; game=r.get('game') or 'UNK'
        if team_count.get(team,0)>=3: continue
        if game_count.get(game,0)>=4: continue
        if sum(x.get('recommended_stake',0) for x in card)+r.get('recommended_stake',0)>bankroll*0.18: continue
        card.append(r); team_count[team]=team_count.get(team,0)+1; game_count[game]=game_count.get(game,0)+1
        if len(card)>=10: break
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'bankroll':bankroll,'summary':{'candidates':len(candidates),'card_size':len(card),'total_stake':round(sum(r.get('recommended_stake',0) for r in card),2)},'recommended_card':card,'candidates':candidates[:75]}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_portfolio_optimizer_v2.json','data/dashboard/wnba_portfolio_optimizer_v2.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); ap.add_argument('--bankroll',type=float,default=500.0); args=ap.parse_args(); print('Portfolio v2 built:', build(args.date,args.bankroll)['summary'])
if __name__=='__main__': main()
