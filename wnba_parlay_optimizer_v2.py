"""Correlation-aware Parlay Optimizer v2.

Same-player pairs use unified player simulations. Same-game cross-player pairs
use direct probabilities from Full-Game Simulation v2. Only combinations across
different games retain a conservative independence estimate.
"""
from __future__ import annotations
import argparse,itertools,json,math
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

UNIFIED=Path('data/dashboard/wnba_unified_player_simulation_v2.json')
FULL_GAME=Path('data/dashboard/wnba_full_game_simulation_v2.json')
TOP=Path('data/dashboard/wnba_cross_market_top_plays.json')
OUTS=[Path('data/warehouse/wnba_parlay_optimizer_v2.json'),Path('data/dashboard/wnba_parlay_optimizer_v2.json')]
MIN_LEG_PROB=.52;MIN_JOINT_PROB=.18

def load(p:Path,d:Any)->Any:
    try:return json.load(p.open(encoding='utf-8')) if p.exists() else d
    except Exception:return d
def dump(p:Path,x:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True);json.dump(x,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def dec(o:Any)->float|None:
    x=num(o)
    if x is None or x==0:return None
    return 1+100/-x if x<0 else 1+x/100
def parlay_dec(legs:list[dict[str,Any]])->float|None:
    out=1.0
    for leg in legs:
        d=dec(leg.get('odds'))
        if d is None:return None
        out*=d
    return out
def ev(prob:float,d:float|None)->float|None:return None if d is None else prob*(d-1)-(1-prob)
def key(leg:dict[str,Any])->tuple:return (str(leg.get('player') or ''),str(leg.get('stat')),str(leg.get('side')),num(leg.get('line')))
def score(prob:float,value:float|None,confidence:float,direct:bool)->float:
    e=50 if value is None else max(0,min(100,50+value*180));p=max(0,min(100,(prob-.12)*150));return round(max(0,min(100,.45*e+.35*p+.20*confidence+(8 if direct else 0))),1)
def finalize(kind:str,game:str,legs:list[dict[str,Any]],joint:float,method:str,confidence:float,correlation:float=0,warning:str|None=None)->dict[str,Any]|None:
    d=parlay_dec(legs)
    if d is None or joint<MIN_JOINT_PROB:return None
    value=ev(joint,d);direct=method in {'DIRECT_JOINT_SIMULATION','DIRECT_FULL_GAME_SIMULATION'};s=score(joint,value,confidence,direct)
    action='BET' if direct and value is not None and value>=.06 and joint>=.24 else 'LEAN' if value is not None and value>0 else 'PASS'
    return {'parlay_type':kind,'game':game,'legs':legs,'joint_probability':round(joint,4),'correlation':round(correlation,4),'calculation_method':method,'decimal_odds_estimate':round(d,4),'expected_value_per_unit':round(value,4) if value is not None else None,'confidence':round(confidence,1),'score':s,'risk_level':'Low' if direct and s>=78 else 'Medium' if direct and s>=62 else 'High','action':action,'warning':warning}
def same_player(unified:dict[str,Any])->list[dict[str,Any]]:
    out=[]
    for p in unified.get('players',[]):
        mmap={(m.get('stat'),m.get('side'),num(m.get('line'))):m for m in p.get('markets',[])}
        for pair in p.get('same_player_pairs',[]):
            legs=[]
            for spec in pair.get('legs',[]):
                m=mmap.get((spec.get('stat'),spec.get('side'),num(spec.get('line'))))
                if m:legs.append({'player':p.get('player'),'stat':m.get('stat'),'side':m.get('side'),'line':m.get('line'),'odds':m.get('odds'),'sportsbook':m.get('sportsbook')})
            if len(legs)==2:
                row=finalize('SAME_PLAYER',f"{p.get('team','')} vs {p.get('opponent','')}",legs,num(pair.get('joint_probability')) or 0,'DIRECT_JOINT_SIMULATION',num(p.get('confidence')) or 50,num(pair.get('correlation_lift')) or 0)
                if row:out.append(row)
    return out
def direct_full_game(full:dict[str,Any],top:dict[str,Any])->list[dict[str,Any]]:
    market_map={key(r):r for r in top.get('top_plays',[]) if r.get('player')}
    out=[]
    for g in full.get('games',[]):
        for pair in g.get('direct_cross_player_pairs',[]):
            legs=[]
            for spec in pair.get('legs',[]):
                m=market_map.get(key(spec))
                if m:legs.append({'player':m.get('player'),'stat':m.get('stat'),'side':m.get('side'),'line':m.get('line'),'odds':m.get('odds'),'sportsbook':m.get('sportsbook')})
            if len(legs)==2:
                confidence=sum(num(market_map.get(key(x),{}).get('confidence')) or 50 for x in pair.get('legs',[]))/2
                row=finalize('SAME_GAME_CROSS_PLAYER',g.get('game'),legs,num(pair.get('joint_probability')) or 0,'DIRECT_FULL_GAME_SIMULATION',confidence,num(pair.get('correlation')) or 0)
                if row:out.append(row)
    return out
def cross_game(top:dict[str,Any])->list[dict[str,Any]]:
    pool=[r for r in top.get('portfolio',[]) if r.get('player') and num(r.get('hit_probability')) is not None and num(r.get('hit_probability'))>=MIN_LEG_PROB and num(r.get('odds')) is not None]
    out=[]
    for size in (2,3):
        for combo in itertools.combinations(pool,size):
            if len({r.get('player') for r in combo})<size or len({r.get('game') for r in combo})<size:continue
            legs=[{'player':r.get('player'),'stat':r.get('stat'),'side':r.get('side'),'line':r.get('line'),'odds':r.get('odds'),'sportsbook':r.get('sportsbook')} for r in combo]
            joint=math.prod(num(r.get('hit_probability')) or 0 for r in combo)*.94
            confidence=sum(num(r.get('confidence')) or 50 for r in combo)/size
            row=finalize('CROSS_GAME','Multiple',legs,joint,'CONSERVATIVE_INDEPENDENCE_ESTIMATE',confidence,0,'Cross-game probability is conservatively estimated, not jointly simulated.')
            if row:out.append(row)
    return out
def dedupe(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    best={}
    for r in rows:
        k=tuple(sorted(key(x) for x in r['legs']))
        if k not in best or r['score']>best[k]['score']:best[k]=r
    return list(best.values())
def build(target:str)->dict[str,Any]:
    rows=dedupe(same_player(load(UNIFIED,{}))+direct_full_game(load(FULL_GAME,{}),load(TOP,{}))+cross_game(load(TOP,{})))
    rows.sort(key=lambda r:(r['score'],num(r.get('expected_value_per_unit')) or -999),reverse=True)
    for i,r in enumerate(rows,1):r['rank']=i;r['recommended_units']=.25 if r['action']=='BET' else .1 if r['action']=='LEAN' else 0
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'candidates':len(rows),'same_player':sum(r['parlay_type']=='SAME_PLAYER' for r in rows),'direct_full_game':sum(r['calculation_method']=='DIRECT_FULL_GAME_SIMULATION' for r in rows),'estimated_cross_game':sum(r['calculation_method']=='CONSERVATIVE_INDEPENDENCE_ESTIMATE' for r in rows),'bets':sum(r['action']=='BET' for r in rows),'leans':sum(r['action']=='LEAN' for r in rows)},'parlays':rows[:30],'methodology':{'same_player':'direct unified-player joint simulation','same_game_cross_player':'direct full-game joint simulation','cross_game':'conservative independence estimate','pricing':'decimal odds multiplication is an estimate; sportsbook SGP repricing may differ'}}
    for p in OUTS:dump(p,payload)
    print('Parlay Optimizer v2:',payload['summary']);return payload
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();build(a.date)
if __name__=='__main__':main()
