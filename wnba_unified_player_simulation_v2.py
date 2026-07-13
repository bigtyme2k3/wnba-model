"""Unified Player Simulation Engine v2.

Generates one 10,000-run stat line per player so every supported market shares
identical simulated minutes, role, and game-level variance. Outputs include
MIN, PTS, REB, OREB, DREB, AST, 3PM, STL, BLK, TOV, PRA, PR, PA, and RA,
plus correlations, market probabilities, best EV, and same-player pair ideas.
"""
from __future__ import annotations
import argparse, hashlib, json, math, random
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

LOGS=Path('data/warehouse/wnba_player_game_logs.json')
MINUTES=Path('data/dashboard/wnba_minutes_projection_v2.json')
RANKS=Path('data/dashboard/wnba_pace_minutes_opponent_rankings.json')
MASTER_PATHS=[Path('data/dashboard/wnba_master.json'),Path('data/master/wnba_master.json')]
OUTS=[Path('data/warehouse/wnba_unified_player_simulation_v2.json'),Path('data/dashboard/wnba_unified_player_simulation_v2.json')]
SIMULATIONS=10_000
BASE_STATS=('MIN','PTS','REB','OREB','DREB','AST','3PM','STL','BLK','TOV')
ALL_STATS=BASE_STATS+('PRA','PR','PA','RA')

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
def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def clamp(v:float,a:float,b:float)->float:return max(a,min(b,v))
def percentile(v:list[float],p:float)->float:
    if not v:return 0.0
    z=(len(v)-1)*p;lo=math.floor(z);hi=math.ceil(z)
    return v[lo] if lo==hi else v[lo]*(hi-z)+v[hi]*(z-lo)
def implied(o:Any)->float|None:
    x=num(o)
    if x is None or x==0:return None
    return -x/(-x+100) if x<0 else 100/(x+100)
def decimal(o:Any)->float|None:
    x=num(o)
    if x is None or x==0:return None
    return 1+100/-x if x<0 else 1+x/100
def pos(v:Any)->str|None:
    t=str(v or '').upper().replace(' ','')
    if t.startswith('G') or 'GUARD' in t:return 'G'
    if t.startswith('F') or 'FORWARD' in t:return 'F'
    if t.startswith('C') or 'CENTER' in t:return 'C'
    return None

def histories()->dict[str,list[dict[str,Any]]]:
    out=defaultdict(list)
    for r in load(LOGS,{'records':[]}).get('records',[]):
        if not isinstance(r,dict) or not r.get('player'):continue
        m=num(r.get('minutes'));s=r.get('scoring',{});b=r.get('boxscore',{})
        required=[num(s.get('total_pts')),num(b.get('reb')),num(b.get('ast')),num(s.get('three_pm')),num(b.get('stl')),num(b.get('blk')),num(b.get('tov'))]
        if m is None or m<=0 or any(x is None for x in required):continue
        out[norm(r.get('player'))].append(r)
    for rows in out.values():rows.sort(key=lambda r:(str(r.get('game_date') or ''),str(r.get('game_id') or '')),reverse=True)
    return out

def minute_index()->dict[str,dict[str,Any]]:
    return {norm(r.get('player')):r for r in load(MINUTES,{'projections':[]}).get('projections',[]) if isinstance(r,dict) and r.get('player')}
def rank_index()->dict[tuple[str,str,str],dict[str,Any]]:
    out={}
    for r in load(RANKS,{'rankings':[]}).get('rankings',[]):
        if isinstance(r,dict):out[(norm(r.get('team')),str(r.get('stat') or '').upper(),str(r.get('position_group') or '').upper())]=r
    return out

def vector(r:dict[str,Any])->dict[str,float]:
    m=max(num(r.get('minutes')) or 1,1);s=r.get('scoring',{});b=r.get('boxscore',{})
    reb=num(b.get('reb')) or 0;oreb=num(b.get('oreb'));dreb=num(b.get('dreb'))
    if oreb is None and dreb is None:oreb=reb*.28;dreb=reb-oreb
    elif oreb is None:oreb=max(0,reb-(dreb or 0))
    elif dreb is None:dreb=max(0,reb-(oreb or 0))
    return {'PTS':(num(s.get('total_pts')) or 0)/m,'REB':reb/m,'OREB':(oreb or 0)/m,'DREB':(dreb or 0)/m,'AST':(num(b.get('ast')) or 0)/m,'3PM':(num(s.get('three_pm')) or 0)/m,'STL':(num(b.get('stl')) or 0)/m,'BLK':(num(b.get('blk')) or 0)/m,'TOV':(num(b.get('tov')) or 0)/m}
def matchup(opponent:Any,stat:str,position:Any,ranks:dict)->tuple[float,dict[str,Any]|None]:
    r=ranks.get((norm(opponent),stat,str(position or '')))
    if not r:return 0.0,None
    a=num(r.get('pace_minutes_adjusted_average_allowed'));raw=num(r.get('raw_average_allowed'))
    if a is None or raw is None or raw<=0:return 0.0,r
    return clamp(a/raw-1,-.15,.15),r

def poisson(rng:random.Random,lam:float,cap:int=70)->int:
    if lam<=0:return 0
    L=math.exp(-lam);k=0;p=1.0
    while p>L and k<cap:k+=1;p*=rng.random()
    return max(0,k-1)
def corr(x:list[float],y:list[float])->float|None:
    n=min(len(x),len(y))
    if n<3:return None
    mx=sum(x[:n])/n;my=sum(y[:n])/n
    vx=sum((a-mx)**2 for a in x[:n]);vy=sum((b-my)**2 for b in y[:n])
    if vx<=0 or vy<=0:return None
    return sum((x[i]-mx)*(y[i]-my) for i in range(n))/math.sqrt(vx*vy)
def normalize_stat(v:Any)->str:
    t=str(v or '').upper()
    replacements={'POINTS':'PTS','REBOUNDS':'REB','ASSISTS':'AST','THREE POINTERS MADE':'3PM','3-POINTERS MADE':'3PM','STEALS':'STL','BLOCKS':'BLK','TURNOVERS':'TOV','POINTS + REBOUNDS + ASSISTS':'PRA','POINTS + REBOUNDS':'PR','POINTS + ASSISTS':'PA','REBOUNDS + ASSISTS':'RA'}
    return replacements.get(t,t)

def project(player:str,rows:list[dict[str,Any]],minute:dict[str,Any],ranks:dict)->dict[str,Any]:
    vectors=[vector(r) for r in rows[:30]];position=pos(rows[0].get('position'));opp=minute.get('opponent')
    mins=num(minute.get('projected_minutes')) or 0;p10m=num(minute.get('minutes_p10')) or mins;p90m=num(minute.get('minutes_p90')) or mins;sigma=max(1,(p90m-p10m)/2.5632)
    adjustments={};contexts={}
    for stat in ('PTS','REB','AST','3PM','STL','BLK','TOV'):
        adjustments[stat],contexts[stat]=matchup(opp,stat,position,ranks)
    rng=random.Random(int(hashlib.sha256(f'{player}|{opp}|unified-v2'.encode()).hexdigest()[:16],16))
    sims={s:[] for s in ALL_STATS}
    for _ in range(SIMULATIONS):
        v=rng.choice(vectors);sm=clamp(rng.gauss(mins,sigma),0,40);game=rng.gauss(1,.08)
        pts=poisson(rng,max(0,sm*v['PTS']*(1+adjustments['PTS'])*game),80)
        reb=poisson(rng,max(0,sm*v['REB']*(1+adjustments['REB'])*game),35)
        ast=poisson(rng,max(0,sm*v['AST']*(1+adjustments['AST'])*game),25)
        threes=poisson(rng,max(0,sm*v['3PM']*(1+adjustments['3PM'])*game),15)
        stl=poisson(rng,max(0,sm*v['STL']*(1+adjustments['STL'])*game),10)
        blk=poisson(rng,max(0,sm*v['BLK']*(1+adjustments['BLK'])*game),10)
        tov=poisson(rng,max(0,sm*v['TOV']*(1+adjustments['TOV'])*game),15)
        oshare=v['OREB']/v['REB'] if v['REB']>0 else .28;oreb=round(reb*clamp(rng.gauss(oshare,.04),.05,.65));dreb=max(0,reb-oreb)
        values={'MIN':sm,'PTS':pts,'REB':reb,'OREB':oreb,'DREB':dreb,'AST':ast,'3PM':threes,'STL':stl,'BLK':blk,'TOV':tov,'PRA':pts+reb+ast,'PR':pts+reb,'PA':pts+ast,'RA':reb+ast}
        for s,val in values.items():sims[s].append(float(val))
    dists={}
    for stat,vals in sims.items():
        vals.sort();dists[stat]={'mean':round(sum(vals)/len(vals),2),'p10':round(percentile(vals,.10),2),'p25':round(percentile(vals,.25),2),'p50':round(percentile(vals,.50),2),'p75':round(percentile(vals,.75),2),'p90':round(percentile(vals,.90),2)}
    correlations={}
    pairs=[('PTS','REB'),('PTS','AST'),('REB','AST'),('PTS','3PM'),('AST','TOV'),('REB','BLK'),('STL','TOV')]
    for a,b in pairs:
        c=corr(sims[a],sims[b]);correlations[f'{a}_{b}']=round(c,4) if c is not None else None
    confidence=clamp(38+min(28,len(rows)*1.4)+(num(minute.get('confidence')) or 50)*.25+sum(2.5 for c in contexts.values() if c)- (12 if str(minute.get('injury_status')).upper() in {'QUESTIONABLE','GTD','DOUBTFUL','UNKNOWN'} else 0),0,100)
    return {'player':player,'team':minute.get('team') or rows[0].get('team'),'opponent':opp,'position_group':position,'simulation_count':SIMULATIONS,'confidence':round(confidence,1),'data_quality_status':'complete' if len(rows)>=10 and minute.get('data_quality_status')=='complete' else 'partial' if len(rows)>=5 else 'limited','distributions':dists,'correlations':correlations,'matchup_adjustments_pct':{k:round(v*100,2) for k,v in adjustments.items()},'matchup_context':contexts,'profile':{'floor':{s:dists[s]['p10'] for s in ALL_STATS},'median':{s:dists[s]['p50'] for s in ALL_STATS},'ceiling':{s:dists[s]['p90'] for s in ALL_STATS}},'reasons':[f'Unified minutes median {dists["MIN"]["p50"]:.1f}',f'Historical games used {len(rows)}','All markets share the same simulated stat line','Combo props calculated inside each simulation'],'simulation_values':sims}
def candidates(prop:dict[str,Any])->list[dict[str,Any]]:
    stat=normalize_stat(prop.get('stat'))
    if stat not in ALL_STATS or stat=='MIN':return []
    line=num(prop.get('line') or prop.get('alt_line'))
    if line is None:return []
    return [{'stat':stat,'side':'OVER','line':line,'odds':prop.get('best_over_price') or prop.get('over_price') or prop.get('best_odds'),'book':prop.get('best_over_book') or prop.get('best_book') or prop.get('book')},{'stat':stat,'side':'UNDER','line':line,'odds':prop.get('best_under_price') or prop.get('under_price'),'book':prop.get('best_under_book') or prop.get('book')}]
def compare(result:dict[str,Any],props:list[dict[str,Any]])->list[dict[str,Any]]:
    sims=result['simulation_values'];out=[];seen=set()
    for prop in props:
        for m in candidates(prop):
            key=(m['stat'],m['side'],m['line'],str(m.get('book') or ''))
            if key in seen:continue
            seen.add(key);vals=sims[m['stat']];prob=sum(x>m['line'] for x in vals)/len(vals) if m['side']=='OVER' else sum(x<m['line'] for x in vals)/len(vals)
            imp=implied(m.get('odds'));dec=decimal(m.get('odds'));edge=None if imp is None else prob-imp;ev=None if dec is None else prob*(dec-1)-(1-prob);b=None if dec is None else dec-1;kelly=None if b is None or b<=0 else clamp((b*prob-(1-prob))/b,0,1)
            out.append({'stat':m['stat'],'side':m['side'],'line':m['line'],'odds':num(m.get('odds')),'sportsbook':m.get('book'),'hit_probability':round(prob,4),'implied_probability':round(imp,4) if imp is not None else None,'probability_edge':round(edge,4) if edge is not None else None,'expected_value_per_unit':round(ev,4) if ev is not None else None,'recommended_units':round(min(1,(kelly or 0)*2.5),2),'action':'BET' if ev is not None and ev>=.05 and prob>=.56 else 'LEAN' if ev is not None and ev>0 else 'PASS'})
    out.sort(key=lambda x:x.get('expected_value_per_unit') if x.get('expected_value_per_unit') is not None else -999,reverse=True);return out
def pair_ideas(result:dict[str,Any],markets:list[dict[str,Any]])->list[dict[str,Any]]:
    sims=result['simulation_values'];ideas=[]
    qualified=[m for m in markets if m['action'] in {'BET','LEAN'} and m['hit_probability']>=.52][:8]
    for i,a in enumerate(qualified):
        for b in qualified[i+1:]:
            if a['stat']==b['stat']:continue
            av=sims[a['stat']];bv=sims[b['stat']]
            hits=0
            for j in range(len(av)):
                ah=av[j]>a['line'] if a['side']=='OVER' else av[j]<a['line'];bh=bv[j]>b['line'] if b['side']=='OVER' else bv[j]<b['line'];hits+=int(ah and bh)
            joint=hits/len(av);ind=a['hit_probability']*b['hit_probability'];lift=joint-ind
            ideas.append({'legs':[{'stat':a['stat'],'side':a['side'],'line':a['line']},{'stat':b['stat'],'side':b['side'],'line':b['line']}],'joint_probability':round(joint,4),'independent_probability':round(ind,4),'correlation_lift':round(lift,4),'classification':'POSITIVE_CORRELATION' if lift>.02 else 'NEGATIVE_CORRELATION' if lift<-.02 else 'NEUTRAL'})
    ideas.sort(key=lambda x:(x['joint_probability'],x['correlation_lift']),reverse=True);return ideas[:10]
def attach(index:dict[str,dict[str,Any]])->int:
    count=0
    for path in MASTER_PATHS:
        master=load(path,{})
        if not master:continue
        props=[]
        for p in master.get('props',[]) or []:
            row=dict(p);r=index.get(norm(row.get('player')));stat=normalize_stat(row.get('stat'))
            if r and stat in r['distributions']:
                d=r['distributions'][stat];row['unified_simulation_v2']={'player':r['player'],'confidence':r['confidence'],'data_quality_status':r['data_quality_status'],'distribution':d,'correlations':r['correlations'],'best_market':r.get('best_market')};row['projection']=d['mean'];row['proj']=d['mean'];row['projection_floor']=d['p10'];row['projection_median']=d['p50'];row['projection_ceiling']=d['p90'];row['projection_confidence_v2']=r['confidence'];count+=1
            props.append(row)
        master['props']=props;master['unified_player_simulation_v2']={'summary':{'players':len(index),'props_attached':sum(1 for x in props if x.get('unified_simulation_v2'))},'source':'data/dashboard/wnba_unified_player_simulation_v2.json'};dump(path,master)
    return count
def build(target:str)->dict[str,Any]:
    hs=histories();mins=minute_index();ranks=rank_index();master=next((load(p,{}) for p in MASTER_PATHS if p.exists()),{});props=defaultdict(list)
    for p in master.get('props',[]) or []:
        if p.get('player'):props[norm(p.get('player'))].append(p)
    rows=[];idx={};all_markets=[]
    for key,m in mins.items():
        h=hs.get(key,[])
        if not h:continue
        r=project(str(m.get('player')),h,m,ranks);r['markets']=compare(r,props.get(key,[]));r['best_market']=r['markets'][0] if r['markets'] else None;r['same_player_pairs']=pair_ideas(r,r['markets']);r.pop('simulation_values',None);rows.append(r);idx[key]=r;all_markets.extend(r['markets'])
    rows.sort(key=lambda r:(r.get('team') or '',-(r.get('best_market') or {}).get('expected_value_per_unit',-999),r['player']));attached=attach(idx)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','schema_version':'2.0','summary':{'players_simulated':len(rows),'props_attached':attached,'simulations_per_player':SIMULATIONS,'supported_stats':len(ALL_STATS),'market_comparisons':len(all_markets),'bet_markets':sum(m['action']=='BET' for m in all_markets),'same_player_pairs':sum(len(r.get('same_player_pairs',[])) for r in rows),'complete':sum(r['data_quality_status']=='complete' for r in rows),'partial':sum(r['data_quality_status']=='partial' for r in rows),'limited':sum(r['data_quality_status']=='limited' for r in rows)},'players':rows,'top_market_edges':sorted(all_markets,key=lambda m:m.get('expected_value_per_unit') if m.get('expected_value_per_unit') is not None else -999,reverse=True)[:30],'methodology':{'single_stat_line':'all supported statistics generated inside the same simulation run','simulations_per_player':SIMULATIONS,'historical_sampling':'bootstrap of verified player-game per-minute stat vectors','shared_uncertainty':'same simulated minutes and game-level factor for every statistic','combo_policy':'PRA/PR/PA/RA calculated per simulation','market_policy':'sportsbook lines and prices never alter the basketball simulation','pair_policy':'joint hit probability measured directly from unified simulations'}}
    for p in OUTS:dump(p,report)
    print('Unified Player Simulation v2:',report['summary']);return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();build(a.date)
if __name__=='__main__':main()
