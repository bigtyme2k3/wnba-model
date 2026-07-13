"""Projection Engine v2 for REB, AST, PRA, PR, PA, and RA.

The engine uses a shared 10,000-run player simulation so points, rebounds, and
assists remain correlated. Each simulation bootstraps a verified historical
player-game rate vector, applies the same simulated minutes, and then applies
bounded stat-specific matchup context. Combo markets are calculated from the
same run, never by adding independent probability distributions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

LOGS=Path('data/warehouse/wnba_player_game_logs.json')
MINUTES=Path('data/dashboard/wnba_minutes_projection_v2.json')
POINTS=Path('data/dashboard/wnba_points_projection_v2.json')
RANKS=Path('data/dashboard/wnba_pace_minutes_opponent_rankings.json')
MASTER_PATHS=[Path('data/dashboard/wnba_master.json'),Path('data/master/wnba_master.json')]
OUTS=[Path('data/warehouse/wnba_rebounds_assists_projection_v2.json'),Path('data/dashboard/wnba_rebounds_assists_projection_v2.json')]
SIMULATIONS=10_000
STATS=('REB','AST','PRA','PR','PA','RA')


def load(path:Path,default:Any)->Any:
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def dump(path:Path,payload:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8') as handle:json.dump(payload,handle,indent=2,allow_nan=False)

def num(value:Any)->float|None:
    try:
        result=float(value);return result if math.isfinite(result) else None
    except Exception:return None

def norm(value:Any)->str:return ' '.join(str(value or '').strip().lower().replace('’',"'").split())
def clamp(value:float,low:float,high:float)->float:return max(low,min(high,value))
def implied(odds:Any)->float|None:
    price=num(odds)
    if price is None or price==0:return None
    return -price/(-price+100) if price<0 else 100/(price+100)
def decimal(odds:Any)->float|None:
    price=num(odds)
    if price is None or price==0:return None
    return 1+100/-price if price<0 else 1+price/100
def position_group(value:Any)->str|None:
    text=str(value or '').strip().upper().replace(' ','')
    if text.startswith('G') or 'GUARD' in text:return 'G'
    if text.startswith('F') or 'FORWARD' in text:return 'F'
    if text.startswith('C') or 'CENTER' in text:return 'C'
    return None

def percentile(values:list[float],p:float)->float:
    if not values:return 0.0
    location=(len(values)-1)*p;lo=math.floor(location);hi=math.ceil(location)
    return values[lo] if lo==hi else values[lo]*(hi-location)+values[hi]*(location-lo)

def history_index()->dict[str,list[dict[str,Any]]]:
    payload=load(LOGS,{'records':[]});out=defaultdict(list)
    for row in payload.get('records',[]):
        if not isinstance(row,dict) or not row.get('player'):continue
        minutes=num(row.get('minutes'));sc=row.get('scoring',{});box=row.get('boxscore',{})
        if minutes is None or minutes<=0 or num(sc.get('total_pts')) is None or num(box.get('reb')) is None or num(box.get('ast')) is None:continue
        out[norm(row.get('player'))].append(row)
    for rows in out.values():rows.sort(key=lambda r:(str(r.get('game_date') or ''),str(r.get('game_id') or '')),reverse=True)
    return out

def minutes_index()->dict[str,dict[str,Any]]:
    return {norm(r.get('player')):r for r in load(MINUTES,{'projections':[]}).get('projections',[]) if isinstance(r,dict) and r.get('player')}
def points_index()->dict[str,dict[str,Any]]:
    return {norm(r.get('player')):r for r in load(POINTS,{'projections':[]}).get('projections',[]) if isinstance(r,dict) and r.get('player')}
def ranking_index()->dict[tuple[str,str,str],dict[str,Any]]:
    out={}
    for row in load(RANKS,{'rankings':[]}).get('rankings',[]):
        if not isinstance(row,dict):continue
        out[(norm(row.get('team')),str(row.get('stat') or '').upper(),str(row.get('position_group') or '').upper())]=row
    return out

def stat_adjustment(opponent:str|None,stat:str,position:str|None,index:dict)->tuple[float,dict[str,Any]|None]:
    row=index.get((norm(opponent),stat,position or ''))
    if not row:return 0.0,None
    adjusted=num(row.get('pace_minutes_adjusted_average_allowed'));raw=num(row.get('raw_average_allowed'))
    if adjusted is None or raw is None or raw<=0:return 0.0,row
    return clamp(adjusted/raw-1,-0.14,0.14),row

def historical_vector(row:dict[str,Any])->tuple[float,float,float,float,float]:
    minutes=max(num(row.get('minutes')) or 1,1);sc=row.get('scoring',{});box=row.get('boxscore',{})
    pts=num(sc.get('total_pts')) or 0;reb=num(box.get('reb')) or 0;ast=num(box.get('ast')) or 0
    oreb=num(box.get('oreb'));dreb=num(box.get('dreb'))
    if oreb is None and dreb is None:oreb=reb*.28;dreb=reb-oreb
    elif oreb is None:oreb=max(0,reb-(dreb or 0))
    elif dreb is None:dreb=max(0,reb-oreb)
    return pts/minutes,reb/minutes,ast/minutes,(oreb or 0)/minutes,(dreb or 0)/minutes

def projection(player:str,rows:list[dict[str,Any]],minute:dict[str,Any],point:dict[str,Any]|None,ranks:dict)->dict[str,Any]:
    position=position_group(rows[0].get('position'));opponent=minute.get('opponent')
    reb_adj,reb_rank=stat_adjustment(opponent,'REB',position,ranks);ast_adj,ast_rank=stat_adjustment(opponent,'AST',position,ranks)
    vectors=[historical_vector(row) for row in rows[:30]]
    recent=vectors[:10] or vectors
    baseline_reb=sum(v[1] for v in recent)/len(recent);baseline_ast=sum(v[2] for v in recent)/len(recent)
    target_minutes=num(minute.get('projected_minutes')) or 0
    p10m=num(minute.get('minutes_p10')) or target_minutes;p90m=num(minute.get('minutes_p90')) or target_minutes
    minute_sigma=max(1,(p90m-p10m)/2.5632)
    seed=int(hashlib.sha256(f'{player}|{opponent}|joint-v2'.encode()).hexdigest()[:16],16);rng=random.Random(seed)
    sim={'PTS':[],'REB':[],'AST':[],'OREB':[],'DREB':[],'PRA':[],'PR':[],'PA':[],'RA':[]}
    point_mean=num((point or {}).get('projected_points'))
    historical_ppm=sum(v[0] for v in recent)/len(recent)
    point_scale=(point_mean/target_minutes/historical_ppm) if point_mean is not None and target_minutes>0 and historical_ppm>0 else 1.0
    point_scale=clamp(point_scale,.75,1.25)
    for _ in range(SIMULATIONS):
        vector=rng.choice(vectors);minutes_sim=clamp(rng.gauss(target_minutes,minute_sigma),0,40)
        common=rng.gauss(1,0.08)
        pts=max(0,minutes_sim*vector[0]*point_scale*common*rng.gauss(1,0.08))
        reb=max(0,minutes_sim*vector[1]*(1+reb_adj)*common*rng.gauss(1,0.10))
        ast=max(0,minutes_sim*vector[2]*(1+ast_adj)*common*rng.gauss(1,0.12))
        oshare=vector[3]/vector[1] if vector[1]>0 else .28;oreb=reb*clamp(rng.gauss(oshare,.04),.05,.65);dreb=max(0,reb-oreb)
        pts=round(pts);reb=round(reb);ast=round(ast);oreb=round(oreb);dreb=round(dreb)
        for key,value in {'PTS':pts,'REB':reb,'AST':ast,'OREB':oreb,'DREB':dreb,'PRA':pts+reb+ast,'PR':pts+reb,'PA':pts+ast,'RA':reb+ast}.items():sim[key].append(float(value))
    for values in sim.values():values.sort()
    distributions={}
    for stat,values in sim.items():
        distributions[stat]={'mean':round(sum(values)/len(values),2),'p10':round(percentile(values,.10),2),'p25':round(percentile(values,.25),2),'p50':round(percentile(values,.50),2),'p75':round(percentile(values,.75),2),'p90':round(percentile(values,.90),2)}
    confidence=clamp(38+min(28,len(rows)*1.4)+(num(minute.get('confidence')) or 50)*.25+(7 if reb_rank else 0)+(7 if ast_rank else 0)- (12 if str(minute.get('injury_status')).upper() in {'QUESTIONABLE','GTD','DOUBTFUL','UNKNOWN'} else 0),0,100)
    return {'player':player,'team':minute.get('team') or rows[0].get('team'),'opponent':opponent,'position_group':position,'projected_minutes':round(target_minutes,1),'simulation_count':SIMULATIONS,'confidence':round(confidence,1),'data_quality_status':'complete' if len(rows)>=10 and minute.get('data_quality_status')=='complete' else 'partial' if len(rows)>=5 else 'limited','projections':distributions,'projected_rebounds':distributions['REB']['mean'],'projected_assists':distributions['AST']['mean'],'projected_oreb':distributions['OREB']['mean'],'projected_dreb':distributions['DREB']['mean'],'projected_pra':distributions['PRA']['mean'],'projected_pr':distributions['PR']['mean'],'projected_pa':distributions['PA']['mean'],'projected_ra':distributions['RA']['mean'],'rate_context':{'rebounds_per_minute':round(baseline_reb,4),'assists_per_minute':round(baseline_ast,4)},'adjustments':{'reb_matchup_pct':round(reb_adj*100,2),'ast_matchup_pct':round(ast_adj*100,2)},'matchup_context':{'REB':reb_rank,'AST':ast_rank},'reasons':[f'Projected minutes {target_minutes:.1f}',f'Historical rebound rate {baseline_reb:.3f}/min',f'Historical assist rate {baseline_ast:.3f}/min',str((reb_rank or {}).get('rank_label') or 'Neutral rebound matchup'),str((ast_rank or {}).get('rank_label') or 'Neutral assist matchup')],'simulation_values':sim}

def market_candidates(prop:dict[str,Any])->list[dict[str,Any]]:
    stat=str(prop.get('stat') or '').upper().replace('REBOUNDS','REB').replace('ASSISTS','AST').replace('POINTS + REBOUNDS + ASSISTS','PRA').replace('POINTS + REBOUNDS','PR').replace('POINTS + ASSISTS','PA').replace('REBOUNDS + ASSISTS','RA')
    if stat not in STATS:return []
    line=num(prop.get('line') or prop.get('alt_line'))
    if line is None:return []
    rows=[{'stat':stat,'side':'OVER','line':line,'odds':prop.get('best_over_price') or prop.get('over_price') or prop.get('best_odds'),'book':prop.get('best_over_book') or prop.get('best_book') or prop.get('book')},{'stat':stat,'side':'UNDER','line':line,'odds':prop.get('best_under_price') or prop.get('under_price'),'book':prop.get('best_under_book') or prop.get('book')}]
    if prop.get('side'):rows.append({'stat':stat,'side':str(prop.get('side')).upper(),'line':line,'odds':prop.get('best_odds'),'book':prop.get('best_book')})
    return rows

def compare_markets(result:dict[str,Any],props:list[dict[str,Any]])->list[dict[str,Any]]:
    sim=result.pop('simulation_values');out=[];seen=set()
    for prop in props:
        for market in market_candidates(prop):
            key=(market['stat'],market['side'],market['line'],str(market.get('book') or ''))
            if key in seen:continue
            seen.add(key);values=sim[market['stat']];line=market['line'];side=market['side']
            wins=sum(value>line for value in values) if side=='OVER' else sum(value<line for value in values);prob=wins/len(values);imp=implied(market.get('odds'));dec=decimal(market.get('odds'));edge=None if imp is None else prob-imp;ev=None if dec is None else prob*(dec-1)-(1-prob)
            b=None if dec is None else dec-1;kelly=None if b is None or b<=0 else clamp((b*prob-(1-prob))/b,0,1)
            out.append({'stat':market['stat'],'side':side,'line':line,'odds':num(market.get('odds')),'sportsbook':market.get('book'),'hit_probability':round(prob,4),'implied_probability':round(imp,4) if imp is not None else None,'probability_edge':round(edge,4) if edge is not None else None,'expected_value_per_unit':round(ev,4) if ev is not None else None,'full_kelly_fraction':round(kelly,4) if kelly is not None else None,'recommended_units':round(min(1,(kelly or 0)*2.5),2),'action':'BET' if ev is not None and ev>=.05 and prob>=.56 else 'LEAN' if ev is not None and ev>0 else 'PASS'})
    out.sort(key=lambda r:r.get('expected_value_per_unit') if r.get('expected_value_per_unit') is not None else -999,reverse=True);return out

def attach(projections:dict[str,dict[str,Any]])->int:
    attached=0
    for path in MASTER_PATHS:
        master=load(path,{})
        if not master:continue
        props=[]
        for prop in master.get('props',[]) or []:
            row=dict(prop);result=projections.get(norm(row.get('player')));stat=str(row.get('stat') or '').upper().replace('REBOUNDS','REB').replace('ASSISTS','AST')
            if result and stat in STATS:
                dist=result['projections'][stat];row['joint_projection_v2']=result;row['projection']=dist['mean'];row['proj']=dist['mean'];row['projection_floor']=dist['p10'];row['projection_median']=dist['p50'];row['projection_ceiling']=dist['p90'];row['projection_confidence_v2']=result['confidence'];attached+=1
            props.append(row)
        master['props']=props;master['rebounds_assists_projection_v2']={'summary':{'players':len(projections),'props_attached':sum(1 for row in props if row.get('joint_projection_v2'))},'source':'data/dashboard/wnba_rebounds_assists_projection_v2.json'};dump(path,master)
    return attached

def build(target:str)->dict[str,Any]:
    histories=history_index();minutes=minutes_index();points=points_index();ranks=ranking_index();master=next((load(p,{}) for p in MASTER_PATHS if p.exists()),{});props_by=defaultdict(list)
    for prop in master.get('props',[]) or []:
        if prop.get('player'):props_by[norm(prop.get('player'))].append(prop)
    projections=[];by_key={}
    for key,minute in minutes.items():
        rows=histories.get(key,[])
        if not rows:continue
        result=projection(str(minute.get('player')),rows,minute,points.get(key),ranks);result['markets']=compare_markets(result,props_by.get(key,[]));projections.append(result);by_key[key]=result
    projections.sort(key=lambda r:(r.get('team') or '',-r['projected_pra'],r['player']));attached=attach(by_key);markets=[m for r in projections for m in r.get('markets',[])]
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','schema_version':'2.0','summary':{'players_projected':len(projections),'props_attached':attached,'simulations_per_player':SIMULATIONS,'market_comparisons':len(markets),'bet_markets':sum(m['action']=='BET' for m in markets),'complete':sum(r['data_quality_status']=='complete' for r in projections),'partial':sum(r['data_quality_status']=='partial' for r in projections),'limited':sum(r['data_quality_status']=='limited' for r in projections)},'projections':projections,'top_market_edges':sorted(markets,key=lambda m:m.get('expected_value_per_unit') if m.get('expected_value_per_unit') is not None else -999,reverse=True)[:25],'methodology':{'joint_simulation':'10,000 shared simulations per player; PTS, REB, and AST use the same historical game-rate vector and simulated minutes','correlation_policy':'combo markets derive from each joint simulation, never independent distribution addition','matchup_policy':'pace/minutes/position adjusted REB and AST context when sample-qualified','market_policy':'lines and prices are comparison inputs only','missing_data_policy':'neutral fallback with explicit data-quality status','kelly_policy':'quarter-Kelly style sizing capped at 1 unit'}}
    for path in OUTS:dump(path,report)
    print('Rebounds/Assists Projection v2:',report['summary']);return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--date',default=str(date.today()));args=parser.parse_args();build(args.date)
if __name__=='__main__':main()
