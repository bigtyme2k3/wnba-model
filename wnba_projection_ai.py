"""Player Projection AI: builds adjusted player prop projections from recent form, matchup, market and simulation signals."""
from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
import pandas as pd

def load(p,d):
    try:
        if os.path.exists(p): return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d
def sf(v,d=0.0):
    try: return float(v)
    except Exception: return d
def key(r): return (str(r.get('player')),str(r.get('game')),str(r.get('stat')))
def read_points(target):
    for p in [f'data/raw/player_points_{target}.csv','data/raw/player_points_today.csv']:
        try:
            if os.path.exists(p): return pd.read_csv(p)
        except Exception: pass
    return pd.DataFrame()
def build(target):
    pts=read_points(target)
    sim={key(r):r for r in load('data/warehouse/wnba_monte_carlo_engine.json',{}).get('all_simulations',[])}
    match={key(r):r for r in load('data/warehouse/wnba_matchup_intelligence.json',{}).get('matchups',[])}
    rows=[]
    if not pts.empty:
        for _,rr in pts.iterrows():
            r=rr.to_dict(); s=sim.get(key(r),{}); m=match.get(key(r),{})
            base=sf(r.get('pred')); median=sf(s.get('p50'),base); matchup=sf(m.get('matchup_score'),60)
            adj=(matchup-60)*0.02
            final=round(base*0.55+median*0.40+adj,2)
            rows.append({**{k:r.get(k) for k in ['player','team','game','stat','line','signal','conf']},'base_projection':base,'sim_median':median,'matchup_score':matchup,'ai_projection':final,'ai_edge':round(final-sf(r.get('line')),2),'projection_source':'player_points+monte_carlo+matchup'})
    rows.sort(key=lambda x:abs(sf(x.get('ai_edge'))), reverse=True)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'summary':{'rows':len(rows),'strong_edges':sum(1 for r in rows if abs(sf(r.get('ai_edge')))>=2)},'projections':rows}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_projection_ai.json','data/dashboard/wnba_projection_ai.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Projection AI built:', build(args.date)['summary'])
if __name__=='__main__': main()
