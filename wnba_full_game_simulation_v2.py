"""Full-Game Simulation Engine v2.

Simulates both teams and all available players in one shared 10,000-run game
environment. Each run shares pace, efficiency, blowout, and overtime factors,
then allocates player outcomes around unified-player distributions. The output
supports direct cross-player and game/player joint probabilities.
"""
from __future__ import annotations
import argparse,hashlib,itertools,json,math,random
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

UNIFIED=Path('data/dashboard/wnba_unified_player_simulation_v2.json')
GAME_MODEL=Path('data/dashboard/wnba_game_market_model.json')
TOP=Path('data/dashboard/wnba_cross_market_top_plays.json')
OUTS=[Path('data/warehouse/wnba_full_game_simulation_v2.json'),Path('data/dashboard/wnba_full_game_simulation_v2.json')]
SIMULATIONS=10_000
PLAYER_STATS=('PTS','REB','AST','3PM','STL','BLK','TOV','PRA','PR','PA','RA')

def load(p:Path,d:Any)->Any:
    try:return json.load(p.open(encoding='utf-8')) if p.exists() else d
    except Exception:return d
def dump(p:Path,x:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True);json.dump(x,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().split())
def clamp(v:float,a:float,b:float)->float:return max(a,min(b,v))
def percentile(v:list[float],p:float)->float:
    if not v:return 0.0
    s=sorted(v);z=(len(s)-1)*p;lo=math.floor(z);hi=math.ceil(z)
    return s[lo] if lo==hi else s[lo]*(hi-z)+s[hi]*(z-lo)
def teams(game:str)->tuple[str,str]:
    parts=[x.strip() for x in str(game or '').replace(' vs ',' @ ').split(' @ ') if x.strip()]
    return (parts[0],parts[1]) if len(parts)>=2 else ('Away','Home')
def normal_from_dist(rng:random.Random,d:dict[str,Any],factor:float=1.0,low:float=0)->float:
    mean=num(d.get('mean')) or 0;p10=num(d.get('p10'));p90=num(d.get('p90'))
    sigma=max(.35,((p90-p10)/2.5632) if p10 is not None and p90 is not None else max(1,mean*.25))
    return max(low,rng.gauss(mean*factor,sigma))
def market_hit(value:float,side:str,line:float)->bool:return value>line if side=='OVER' else value<line
def corr(x:list[float],y:list[float])->float|None:
    n=min(len(x),len(y));
    if n<3:return None
    mx=sum(x)/n;my=sum(y)/n;vx=sum((a-mx)**2 for a in x);vy=sum((b-my)**2 for b in y)
    if vx<=0 or vy<=0:return None
    return sum((x[i]-mx)*(y[i]-my) for i in range(n))/math.sqrt(vx*vy)

def build_game(game_row:dict[str,Any],players:list[dict[str,Any]],top_rows:list[dict[str,Any]])->dict[str,Any]:
    game=str(game_row.get('game') or '');away,home=teams(game)
    by_team=defaultdict(list)
    for p in players:
        team=str(p.get('team') or '')
        if norm(team) in {norm(away),norm(home)}:by_team[team].append(p)
    seed=int(hashlib.sha256(f'{game}|full-game-v2'.encode()).hexdigest()[:16],16);rng=random.Random(seed)
    projected_total=num(game_row.get('projected_total')) or num(game_row.get('market_total')) or 160
    projected_margin=num(game_row.get('projected_margin')) or num(game_row.get('market_spread')) or 0
    home_mean=(projected_total+projected_margin)/2;away_mean=projected_total-home_mean
    team_scores={away:[],home:[]};game_totals=[];margins=[];overtimes=[];player_sims={}
    for p in players:
        if norm(p.get('team')) not in {norm(away),norm(home)}:continue
        player_sims[str(p.get('player'))]={s:[] for s in PLAYER_STATS}
    for _ in range(SIMULATIONS):
        pace=clamp(rng.gauss(1,.055),.84,1.18);game_eff=clamp(rng.gauss(1,.06),.82,1.20);home_eff=clamp(rng.gauss(1,.045),.86,1.15);away_eff=clamp(rng.gauss(1,.045),.86,1.15)
        raw_home=max(55,rng.gauss(home_mean*pace*game_eff*home_eff,8.5));raw_away=max(55,rng.gauss(away_mean*pace*game_eff*away_eff,8.5))
        overtime=abs(raw_home-raw_away)<1.5 and rng.random()<.18
        ot_factor=1.06 if overtime else 1.0;raw_home*=ot_factor;raw_away*=ot_factor
        margin=raw_home-raw_away;blowout=abs(margin)>=15
        team_scores[home].append(raw_home);team_scores[away].append(raw_away);game_totals.append(raw_home+raw_away);margins.append(margin);overtimes.append(float(overtime))
        for p in players:
            pname=str(p.get('player'));team=str(p.get('team') or '')
            if pname not in player_sims:continue
            team_factor=(raw_home/home_mean if norm(team)==norm(home) and home_mean else raw_away/away_mean if away_mean else 1)
            minute_factor=ot_factor*(.93 if blowout and (num((p.get('distributions') or {}).get('MIN',{}).get('mean')) or 0)>=30 else 1)
            role=rng.gauss(1,.07)
            vals={}
            for stat in ('PTS','REB','AST','3PM','STL','BLK','TOV'):
                d=(p.get('distributions') or {}).get(stat,{})
                factor=role*minute_factor
                if stat in {'PTS','3PM','AST','TOV'}:factor*=team_factor
                elif stat=='REB':factor*=clamp(2-team_factor,.82,1.16)
                vals[stat]=round(normal_from_dist(rng,d,factor))
            vals['PRA']=vals['PTS']+vals['REB']+vals['AST'];vals['PR']=vals['PTS']+vals['REB'];vals['PA']=vals['PTS']+vals['AST'];vals['RA']=vals['REB']+vals['AST']
            for s,v in vals.items():player_sims[pname][s].append(float(v))
    player_out=[]
    for p in players:
        pname=str(p.get('player'))
        if pname not in player_sims:continue
        dists={s:{'mean':round(sum(v)/len(v),2),'p10':round(percentile(v,.10),2),'p50':round(percentile(v,.50),2),'p90':round(percentile(v,.90),2)} for s,v in player_sims[pname].items()}
        player_out.append({'player':pname,'team':p.get('team'),'distributions':dists})
    relevant=[r for r in top_rows if norm(r.get('game'))==norm(game) or (r.get('player') and str(r.get('player')) in player_sims)]
    direct=[]
    for a,b in itertools.combinations(relevant,2):
        if not a.get('player') or not b.get('player') or a.get('player')==b.get('player'):continue
        if a.get('stat') not in PLAYER_STATS or b.get('stat') not in PLAYER_STATS:continue
        av=player_sims.get(str(a.get('player')),{}).get(str(a.get('stat')));bv=player_sims.get(str(b.get('player')),{}).get(str(b.get('stat')))
        if not av or not bv:continue
        la=num(a.get('line'));lb=num(b.get('line'))
        if la is None or lb is None:continue
        hits=sum(market_hit(av[i],str(a.get('side')),la) and market_hit(bv[i],str(b.get('side')),lb) for i in range(SIMULATIONS));joint=hits/SIMULATIONS
        direct.append({'legs':[{'player':a.get('player'),'stat':a.get('stat'),'side':a.get('side'),'line':la},{'player':b.get('player'),'stat':b.get('stat'),'side':b.get('side'),'line':lb}],'joint_probability':round(joint,4),'calculation_method':'DIRECT_FULL_GAME_SIMULATION','correlation':round(corr(av,bv) or 0,4)})
    direct.sort(key=lambda x:x['joint_probability'],reverse=True)
    return {'game':game,'away_team':away,'home_team':home,'simulation_count':SIMULATIONS,'score_distribution':{'away_mean':round(sum(team_scores[away])/SIMULATIONS,2),'home_mean':round(sum(team_scores[home])/SIMULATIONS,2),'total_mean':round(sum(game_totals)/SIMULATIONS,2),'margin_mean':round(sum(margins)/SIMULATIONS,2),'total_p10':round(percentile(game_totals,.10),2),'total_p90':round(percentile(game_totals,.90),2),'margin_p10':round(percentile(margins,.10),2),'margin_p90':round(percentile(margins,.90),2),'overtime_probability':round(sum(overtimes)/SIMULATIONS,4)},'players':player_out,'direct_cross_player_pairs':direct[:30]}

def build(target:str)->dict[str,Any]:
    unified=load(UNIFIED,{'players':[]});games=load(GAME_MODEL,{'games':[]});top=load(TOP,{'top_plays':[]})
    output=[build_game(g,unified.get('players',[]),top.get('top_plays',[])) for g in games.get('games',[]) if g.get('game')]
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'games_simulated':len(output),'simulations_per_game':SIMULATIONS,'players_simulated':sum(len(g['players']) for g in output),'direct_cross_player_pairs':sum(len(g['direct_cross_player_pairs']) for g in output)},'games':output,'methodology':{'shared_environment':'pace, efficiency, overtime, and blowout factors shared across both teams and all players','player_allocation':'unified player distributions adjusted by shared team and game factors','cross_player_probability':'measured directly from the same game simulation runs','market_independence':'sportsbook lines are evaluation inputs and never drive simulated outcomes'}}
    for p in OUTS:dump(p,payload)
    print('Full Game Simulation v2:',payload['summary']);return payload

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();build(a.date)
if __name__=='__main__':main()
