"""Correlation-aware Parlay Optimizer v2.

Same-player pairs use direct joint probabilities emitted by the unified player
simulation. Cross-player parlays are allowed only as conservative estimates and
are clearly labeled because their joint outcomes are not simulated together.
The optimizer avoids duplicate markets, contradictory legs, excessive game
concentration, and low-quality or unpriced selections.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

UNIFIED=Path('data/dashboard/wnba_unified_player_simulation_v2.json')
TOP=Path('data/dashboard/wnba_cross_market_top_plays.json')
OUTS=[Path('data/warehouse/wnba_parlay_optimizer_v2.json'),Path('data/dashboard/wnba_parlay_optimizer_v2.json')]
MAX_LEGS=3
MIN_LEG_PROB=.52
MIN_JOINT_PROB=.18


def load(path:Path,default:Any)->Any:
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def dump(path:Path,payload:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8') as h:json.dump(payload,h,indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def decimal_from_american(o:Any)->float|None:
    x=num(o)
    if x is None or x==0:return None
    return 1+100/-x if x<0 else 1+x/100
def clamp(v:float,a:float,b:float)->float:return max(a,min(b,v))
def leg_key(leg:dict[str,Any])->tuple:
    return (str(leg.get('player') or ''),str(leg.get('game') or ''),str(leg.get('stat')),str(leg.get('side')),num(leg.get('line')))
def contradictory(a:dict[str,Any],b:dict[str,Any])->bool:
    return leg_key(a)[:-1]==leg_key(b)[:-1] and a.get('side')!=b.get('side')
def duplicate(a:dict[str,Any],b:dict[str,Any])->bool:return leg_key(a)==leg_key(b)
def parlay_decimal(legs:list[dict[str,Any]])->float|None:
    result=1.0
    for leg in legs:
        d=decimal_from_american(leg.get('odds'))
        if d is None:return None
        result*=d
    return result
def ev_from_prob(prob:float,decimal:float|None)->float|None:
    return None if decimal is None else prob*(decimal-1)-(1-prob)
def score(prob:float,ev:float|None,quality:float,method:str,correlation_lift:float=0)->float:
    ev_score=50 if ev is None else clamp(50+ev*180,0,100)
    prob_score=clamp((prob-.12)*150,0,100)
    method_bonus=8 if method=='DIRECT_JOINT_SIMULATION' else 0
    corr_bonus=clamp(correlation_lift*250,-12,12)
    return round(clamp(.42*ev_score+.38*prob_score+.20*quality+method_bonus+corr_bonus,0,100),1)
def risk_label(value:float,method:str)->str:
    if method!='DIRECT_JOINT_SIMULATION':return 'High'
    return 'Low' if value>=78 else 'Medium' if value>=62 else 'High'

def build_same_player(unified:dict[str,Any])->list[dict[str,Any]]:
    out=[]
    for player in unified.get('players',[]):
        if not isinstance(player,dict):continue
        market_map={(m.get('stat'),m.get('side'),num(m.get('line'))):m for m in player.get('markets',[]) if isinstance(m,dict)}
        for pair in player.get('same_player_pairs',[]):
            legs=[]
            for spec in pair.get('legs',[]):
                market=market_map.get((spec.get('stat'),spec.get('side'),num(spec.get('line'))))
                if market:
                    legs.append({'player':player.get('player'),'game':f"{player.get('team','')} vs {player.get('opponent','')}",'stat':market.get('stat'),'side':market.get('side'),'line':market.get('line'),'odds':market.get('odds'),'sportsbook':market.get('sportsbook'),'hit_probability':market.get('hit_probability')})
            if len(legs)!=2:continue
            decimal=parlay_decimal(legs);joint=num(pair.get('joint_probability'))
            if joint is None or joint<MIN_JOINT_PROB or decimal is None:continue
            ev=ev_from_prob(joint,decimal);lift=num(pair.get('correlation_lift')) or 0
            quality=num(player.get('confidence')) or 50
            out.append({'parlay_type':'SAME_PLAYER','player':player.get('player'),'game':legs[0]['game'],'legs':legs,'joint_probability':round(joint,4),'independent_probability':round((num(legs[0].get('hit_probability')) or 0)*(num(legs[1].get('hit_probability')) or 0),4),'correlation_lift':round(lift,4),'calculation_method':'DIRECT_JOINT_SIMULATION','decimal_odds_estimate':round(decimal,4),'expected_value_per_unit':round(ev,4) if ev is not None else None,'confidence':round(quality,1),'score':score(joint,ev,quality,'DIRECT_JOINT_SIMULATION',lift),'risk_level':risk_label(score(joint,ev,quality,'DIRECT_JOINT_SIMULATION',lift),'DIRECT_JOINT_SIMULATION'),'action':'BET' if ev is not None and ev>=.06 and joint>=.24 else 'LEAN' if ev is not None and ev>0 else 'PASS'})
    return out

def build_cross_player(top:dict[str,Any])->list[dict[str,Any]]:
    pool=[]
    for row in top.get('portfolio',[]):
        if not isinstance(row,dict) or not row.get('player'):continue
        if row.get('decision') not in {'BET','LEAN'}:continue
        p=num(row.get('hit_probability'));odds=num(row.get('odds'))
        if p is None or p<MIN_LEG_PROB or odds is None:continue
        pool.append({'player':row.get('player'),'game':row.get('game'),'stat':row.get('stat'),'side':row.get('side'),'line':row.get('line'),'odds':odds,'sportsbook':row.get('sportsbook'),'hit_probability':p,'confidence':row.get('confidence'),'data_quality_status':row.get('data_quality_status')})
    out=[]
    for size in (2,3):
        for combo in itertools.combinations(pool,size):
            if len({leg['player'] for leg in combo})<size:continue
            if any(duplicate(a,b) or contradictory(a,b) for i,a in enumerate(combo) for b in combo[i+1:]):continue
            game_counts={g:sum(1 for leg in combo if leg['game']==g) for g in {leg['game'] for leg in combo}}
            if max(game_counts.values())>2:continue
            independent=math.prod(leg['hit_probability'] for leg in combo)
            # Conservative haircut for unmodeled cross-player dependence.
            penalty=.94 if len(game_counts)==size else .88
            joint=independent*penalty
            if joint<MIN_JOINT_PROB:continue
            decimal=parlay_decimal(list(combo));ev=ev_from_prob(joint,decimal)
            quality=sum(num(leg.get('confidence')) or 50 for leg in combo)/size
            out.append({'parlay_type':'CROSS_PLAYER','player':None,'game':'Multiple' if len(game_counts)>1 else combo[0]['game'],'legs':list(combo),'joint_probability':round(joint,4),'independent_probability':round(independent,4),'correlation_lift':round(joint-independent,4),'calculation_method':'CONSERVATIVE_INDEPENDENCE_ESTIMATE','decimal_odds_estimate':round(decimal,4) if decimal is not None else None,'expected_value_per_unit':round(ev,4) if ev is not None else None,'confidence':round(quality,1),'score':score(joint,ev,quality,'CONSERVATIVE_INDEPENDENCE_ESTIMATE',joint-independent),'risk_level':'High','action':'LEAN' if ev is not None and ev>=.03 else 'PASS','warning':'Cross-player joint probability is estimated, not directly simulated.'})
    return out

def dedupe(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    best={}
    for row in rows:
        key=tuple(sorted(leg_key(leg) for leg in row.get('legs',[])))
        current=best.get(key)
        if current is None or row['score']>current['score']:best[key]=row
    return list(best.values())
def build(target:str)->dict[str,Any]:
    unified=load(UNIFIED,{});top=load(TOP,{})
    rows=dedupe(build_same_player(unified)+build_cross_player(top))
    rows.sort(key=lambda r:(r['score'],num(r.get('expected_value_per_unit')) or -999,r['joint_probability']),reverse=True)
    for i,row in enumerate(rows,1):row['rank']=i;row['recommended_units']=.25 if row['action']=='BET' else .1 if row['action']=='LEAN' else 0
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'candidates':len(rows),'same_player':sum(r['parlay_type']=='SAME_PLAYER' for r in rows),'cross_player':sum(r['parlay_type']=='CROSS_PLAYER' for r in rows),'bets':sum(r['action']=='BET' for r in rows),'leans':sum(r['action']=='LEAN' for r in rows)},'parlays':rows[:30],'methodology':{'same_player':'direct joint probability from unified player simulations','cross_player':'conservative independence estimate with explicit haircut','pricing':'estimated by multiplying decimal odds because sportsbook SGP repricing may differ','constraints':{'max_legs':MAX_LEGS,'minimum_leg_probability':MIN_LEG_PROB,'minimum_joint_probability':MIN_JOINT_PROB},'stake_policy':'0.25 units for BET, 0.10 units for LEAN, zero for PASS','warning':'Sportsbooks may reject combinations or reprice correlated legs.'}}
    for p in OUTS:dump(p,payload)
    print('Parlay Optimizer v2:',payload['summary']);return payload

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));args=ap.parse_args();build(args.date)
if __name__=='__main__':main()
