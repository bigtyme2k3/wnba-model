"""Live In-Game Projection Engine v1.

Combines ESPN live scoreboard/box-score state with pregame unified and full-game
priors. Early-game estimates remain prior-heavy; observed pace, score, minutes,
usage, and foul trouble gain weight as elapsed time increases.
"""
from __future__ import annotations
import argparse,json,math,random,hashlib
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any
import requests

UNIFIED=Path('data/dashboard/wnba_unified_player_simulation_v2.json')
FULL=Path('data/dashboard/wnba_full_game_simulation_v2.json')
OUTS=[Path('data/warehouse/wnba_live_projection_v1.json'),Path('data/dashboard/wnba_live_projection_v1.json')]
ESPN='https://site.api.espn.com/apis/site/v2/sports/basketball/wnba'
SIMS=5000
STATS=('PTS','REB','AST','3PM','STL','BLK','TOV','PRA','PR','PA','RA')

def load(p:Path,d:Any)->Any:
    try:return json.load(p.open(encoding='utf-8')) if p.exists() else d
    except Exception:return d
def dump(p:Path,x:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True);json.dump(x,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def clamp(v:float,a:float,b:float)->float:return max(a,min(b,v))
def pct(v:list[float],p:float)->float:
    if not v:return 0
    s=sorted(v);z=(len(s)-1)*p;lo=math.floor(z);hi=math.ceil(z)
    return s[lo] if lo==hi else s[lo]*(hi-z)+s[hi]*(z-lo)
def fetch_json(url:str,params:dict[str,Any]|None=None)->dict[str,Any]:
    r=requests.get(url,params=params,headers={'User-Agent':'Mozilla/5.0 WNBA model'},timeout=20);r.raise_for_status();return r.json()
def clock_seconds(display:str)->int:
    try:
        m,s=str(display).split(':');return int(m)*60+int(float(s))
    except Exception:return 0
def elapsed(period:int,clock:str)->float:
    if period<=0:return 0
    regulation_elapsed=(period-1)*600+(600-clock_seconds(clock))
    if period>4:regulation_elapsed=2400+(period-5)*300+(300-clock_seconds(clock))
    return clamp(regulation_elapsed,0,2700)
def parse_box(summary:dict[str,Any])->list[dict[str,Any]]:
    rows=[]
    for team in summary.get('boxscore',{}).get('players',[]):
        t=team.get('team',{}).get('displayName','')
        for group in team.get('statistics',[]):
            labels=group.get('labels',[])
            for a in group.get('athletes',[]):
                vals=dict(zip(labels,a.get('stats',[])))
                def g(k):return num(vals.get(k))
                pts=g('PTS') or 0;reb=g('REB') or 0;ast=g('AST') or 0
                rows.append({'player':a.get('athlete',{}).get('displayName',''),'team':t,'starter':bool(a.get('starter')),'minutes':g('MIN') or 0,'fouls':g('PF') or 0,'PTS':pts,'REB':reb,'AST':ast,'3PM':g('3PM') or 0,'STL':g('STL') or 0,'BLK':g('BLK') or 0,'TOV':g('TO') or 0,'PRA':pts+reb+ast,'PR':pts+reb,'PA':pts+ast,'RA':reb+ast})
    return rows
def priors()->tuple[dict[str,dict[str,Any]],dict[str,dict[str,Any]]]:
    u=load(UNIFIED,{'players':[]});f=load(FULL,{'games':[]})
    return ({norm(r.get('player')):r for r in u.get('players',[])},{norm(g.get('game')):g for g in f.get('games',[])})
def project_player(row:dict[str,Any],prior:dict[str,Any],progress:float,remaining_minutes:float)->dict[str,Any]:
    dists=prior.get('distributions',{});live_min=num(row.get('minutes')) or 0;pre_min=num(dists.get('MIN',{}).get('mean')) or live_min
    foul_penalty=clamp((num(row.get('fouls')) or 0)-2,0,4)*.6
    expected_remaining=max(0,min(remaining_minutes,pre_min-live_min-foul_penalty))
    final_minutes=live_min+expected_remaining
    weight=clamp(progress**1.35,.05,.95)
    rng=random.Random(int(hashlib.sha256(f"{row.get('player')}|{progress:.3f}".encode()).hexdigest()[:16],16))
    sims={s:[] for s in STATS}
    for _ in range(SIMS):
        minute_sim=clamp(rng.gauss(final_minutes,max(1,(1-progress)*3)),live_min,45)
        vals={}
        for stat in ('PTS','REB','AST','3PM','STL','BLK','TOV'):
            observed=num(row.get(stat)) or 0;pre_mean=num(dists.get(stat,{}).get('mean')) or observed
            pre_rate=pre_mean/max(pre_min,1);live_rate=observed/max(live_min,1) if live_min>0 else pre_rate
            rate=(1-weight)*pre_rate+weight*live_rate
            vals[stat]=max(observed,round(observed+max(0,minute_sim-live_min)*max(0,rng.gauss(rate,max(.02,rate*.25)))))
        vals['PRA']=vals['PTS']+vals['REB']+vals['AST'];vals['PR']=vals['PTS']+vals['REB'];vals['PA']=vals['PTS']+vals['AST'];vals['RA']=vals['REB']+vals['AST']
        for s,v in vals.items():sims[s].append(float(v))
    out={s:{'mean':round(sum(v)/len(v),2),'p10':round(pct(v,.1),2),'p50':round(pct(v,.5),2),'p90':round(pct(v,.9),2)} for s,v in sims.items()}
    return {'player':row.get('player'),'team':row.get('team'),'live_minutes':live_min,'projected_final_minutes':round(final_minutes,1),'fouls':row.get('fouls'),'prior_weight':round(1-weight,3),'live_weight':round(weight,3),'distributions':out,'foul_trouble':bool((num(row.get('fouls')) or 0)>=4)}
def build(target:str)->dict[str,Any]:
    board=fetch_json(f'{ESPN}/scoreboard',{'dates':target.replace('-','')});player_priors,game_priors=priors();games=[]
    for event in board.get('events',[]):
        status=event.get('status',{});state=status.get('type',{}).get('name','')
        if 'IN_PROGRESS' not in state.upper() and 'PROGRESS' not in state.upper():continue
        comp=(event.get('competitions') or [{}])[0];teams=comp.get('competitors',[]);home=next((x for x in teams if x.get('homeAway')=='home'),{});away=next((x for x in teams if x.get('homeAway')=='away'),{})
        home_name=home.get('team',{}).get('displayName','');away_name=away.get('team',{}).get('displayName','');game=f'{away_name} @ {home_name}'
        period=int(status.get('period') or 0);clock=status.get('displayClock') or '0:00';elapsed_s=elapsed(period,clock);progress=clamp(elapsed_s/2400,0,1);remaining=max(0,(2400-elapsed_s)/60)
        summary=fetch_json(f'{ESPN}/summary',{'event':event.get('id')});box=parse_box(summary);players=[]
        for row in box:
            prior=player_priors.get(norm(row.get('player')))
            if prior:players.append(project_player(row,prior,progress,remaining))
        gp=game_priors.get(norm(game),{}).get('score_distribution',{});hs=num(home.get('score')) or 0;ascore=num(away.get('score')) or 0;pre_total=num(gp.get('total_mean')) or max(hs+ascore,150)
        live_rate=(hs+ascore)/max(elapsed_s/60,1);live_final=live_rate*40;blend=(1-progress)*pre_total+progress*live_final
        margin_live=hs-ascore;pre_margin=num(gp.get('margin_mean')) or 0;projected_margin=(1-progress)*pre_margin+progress*(margin_live/max(progress,.15))
        games.append({'game_id':event.get('id'),'game':game,'period':period,'clock':clock,'progress':round(progress,4),'home_score':hs,'away_score':ascore,'projected_final_total':round(blend,1),'projected_final_margin':round(projected_margin,1),'remaining_minutes':round(remaining,2),'players':players,'status':state})
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'live_games':len(games),'players_projected':sum(len(g['players']) for g in games),'simulations_per_player':SIMS},'games':games,'methodology':{'prior':'pregame unified player and full-game simulations','update_rule':'pregame prior weight decays as elapsed game fraction rises','live_inputs':'score, period, clock, player minutes, stats, and fouls','foul_policy':'four or more fouls reduces remaining-minute expectation','market_policy':'live sportsbook lines are not required and never drive projections'}}
    for p in OUTS:dump(p,payload)
    print('Live Projection v1:',payload['summary']);return payload
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();build(a.date)
if __name__=='__main__':main()
