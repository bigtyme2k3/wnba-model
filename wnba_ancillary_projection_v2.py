"""Projection Engine v2 for 3PM, STL, BLK, and TOV.

Uses verified player-game rates, Minutes Projection v2, position/pace matchup
context, and 10,000 shared player-level simulations. Sportsbook prices are used
only after the basketball projection is complete.
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
OUTS=[Path('data/warehouse/wnba_ancillary_projection_v2.json'),Path('data/dashboard/wnba_ancillary_projection_v2.json')]
STATS=('3PM','STL','BLK','TOV');SIMULATIONS=10_000

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
def implied(o:Any)->float|None:
    x=num(o)
    if x is None or x==0:return None
    return -x/(-x+100) if x<0 else 100/(x+100)
def decimal(o:Any)->float|None:
    x=num(o)
    if x is None or x==0:return None
    return 1+100/-x if x<0 else 1+x/100
def percentile(v:list[float],p:float)->float:
    if not v:return 0.0
    z=(len(v)-1)*p;lo=math.floor(z);hi=math.ceil(z)
    return v[lo] if lo==hi else v[lo]*(hi-z)+v[hi]*(z-lo)
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
        vals=[num(s.get('three_pm')),num(b.get('stl')),num(b.get('blk')),num(b.get('tov'))]
        if m is None or m<=0 or any(x is None for x in vals):continue
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

def rate_vector(r:dict[str,Any])->dict[str,float]:
    m=max(num(r.get('minutes')) or 1,1);s=r.get('scoring',{});b=r.get('boxscore',{})
    return {'3PM':(num(s.get('three_pm')) or 0)/m,'STL':(num(b.get('stl')) or 0)/m,'BLK':(num(b.get('blk')) or 0)/m,'TOV':(num(b.get('tov')) or 0)/m}
def adjustment(opponent:Any,stat:str,position:Any,ranks:dict)->tuple[float,dict[str,Any]|None]:
    r=ranks.get((norm(opponent),stat,str(position or '')))
    if not r:return 0.0,None
    a=num(r.get('pace_minutes_adjusted_average_allowed'));raw=num(r.get('raw_average_allowed'))
    if a is None or raw is None or raw<=0:return 0.0,r
    return clamp(a/raw-1,-.15,.15),r

def project(player:str,rows:list[dict[str,Any]],minute:dict[str,Any],ranks:dict)->dict[str,Any]:
    vectors=[rate_vector(r) for r in rows[:30]];position=pos(rows[0].get('position'));opp=minute.get('opponent')
    mins=num(minute.get('projected_minutes')) or 0;p10m=num(minute.get('minutes_p10')) or mins;p90m=num(minute.get('minutes_p90')) or mins;sigma=max(1,(p90m-p10m)/2.5632)
    adjs={};contexts={}
    for stat in STATS:adjs[stat],contexts[stat]=adjustment(opp,stat,position,ranks)
    rng=random.Random(int(hashlib.sha256(f'{player}|{opp}|ancillary-v2'.encode()).hexdigest()[:16],16))
    sims={s:[] for s in STATS}
    for _ in range(SIMULATIONS):
        v=rng.choice(vectors);sm=clamp(rng.gauss(mins,sigma),0,40);common=rng.gauss(1,.08)
        for stat in STATS:
            lam=max(0,sm*v[stat]*(1+adjs[stat])*common*rng.gauss(1,.12))
            # Poisson via Knuth for realistic count outcomes.
            L=math.exp(-lam);k=0;p=1.0
            while p>L and k<25:k+=1;p*=rng.random()
            sims[stat].append(float(max(0,k-1)))
    projections={}
    for stat,vals in sims.items():
        vals.sort();projections[stat]={'mean':round(sum(vals)/len(vals),2),'p10':round(percentile(vals,.10),2),'p25':round(percentile(vals,.25),2),'p50':round(percentile(vals,.50),2),'p75':round(percentile(vals,.75),2),'p90':round(percentile(vals,.90),2)}
    conf=clamp(40+min(25,len(rows)*1.4)+(num(minute.get('confidence')) or 50)*.25+sum(4 for x in contexts.values() if x)- (12 if str(minute.get('injury_status')).upper() in {'QUESTIONABLE','GTD','DOUBTFUL','UNKNOWN'} else 0),0,100)
    return {'player':player,'team':minute.get('team') or rows[0].get('team'),'opponent':opp,'position_group':position,'projected_minutes':round(mins,1),'simulation_count':SIMULATIONS,'confidence':round(conf,1),'data_quality_status':'complete' if len(rows)>=10 and minute.get('data_quality_status')=='complete' else 'partial' if len(rows)>=5 else 'limited','projections':projections,'projected_3pm':projections['3PM']['mean'],'projected_steals':projections['STL']['mean'],'projected_blocks':projections['BLK']['mean'],'projected_turnovers':projections['TOV']['mean'],'adjustments':{k:round(v*100,2) for k,v in adjs.items()},'matchup_context':contexts,'reasons':[f'Projected minutes {mins:.1f}',f'3PM rate {sum(v["3PM"] for v in vectors[:10])/len(vectors[:10]):.3f}/min',f'STL rate {sum(v["STL"] for v in vectors[:10])/len(vectors[:10]):.3f}/min',f'BLK rate {sum(v["BLK"] for v in vectors[:10])/len(vectors[:10]):.3f}/min',f'TOV rate {sum(v["TOV"] for v in vectors[:10])/len(vectors[:10]):.3f}/min'],'simulation_values':sims}

def normalize_stat(v:Any)->str:
    t=str(v or '').upper().replace('THREE POINTERS MADE','3PM').replace('3-POINTERS MADE','3PM').replace('STEALS','STL').replace('BLOCKS','BLK').replace('TURNOVERS','TOV')
    return t
def candidates(prop:dict[str,Any])->list[dict[str,Any]]:
    stat=normalize_stat(prop.get('stat'))
    if stat not in STATS:return []
    line=num(prop.get('line') or prop.get('alt_line'))
    if line is None:return []
    rows=[{'stat':stat,'side':'OVER','line':line,'odds':prop.get('best_over_price') or prop.get('over_price') or prop.get('best_odds'),'book':prop.get('best_over_book') or prop.get('best_book') or prop.get('book')},{'stat':stat,'side':'UNDER','line':line,'odds':prop.get('best_under_price') or prop.get('under_price'),'book':prop.get('best_under_book') or prop.get('book')}]
    return rows
def compare(result:dict[str,Any],props:list[dict[str,Any]])->list[dict[str,Any]]:
    sims=result.pop('simulation_values');out=[]
    for prop in props:
        for m in candidates(prop):
            vals=sims[m['stat']];line=m['line'];side=m['side'];prob=sum(x>line for x in vals)/len(vals) if side=='OVER' else sum(x<line for x in vals)/len(vals)
            imp=implied(m.get('odds'));dec=decimal(m.get('odds'));edge=None if imp is None else prob-imp;ev=None if dec is None else prob*(dec-1)-(1-prob);b=None if dec is None else dec-1;kelly=None if b is None or b<=0 else clamp((b*prob-(1-prob))/b,0,1)
            out.append({'stat':m['stat'],'side':side,'line':line,'odds':num(m.get('odds')),'sportsbook':m.get('book'),'hit_probability':round(prob,4),'implied_probability':round(imp,4) if imp is not None else None,'probability_edge':round(edge,4) if edge is not None else None,'expected_value_per_unit':round(ev,4) if ev is not None else None,'recommended_units':round(min(1,(kelly or 0)*2.5),2),'action':'BET' if ev is not None and ev>=.05 and prob>=.56 else 'LEAN' if ev is not None and ev>0 else 'PASS'})
    out.sort(key=lambda x:x.get('expected_value_per_unit') if x.get('expected_value_per_unit') is not None else -999,reverse=True);return out

def attach(index:dict[str,dict[str,Any]])->int:
    count=0
    for path in MASTER_PATHS:
        master=load(path,{})
        if not master:continue
        props=[]
        for p in master.get('props',[]) or []:
            row=dict(p);r=index.get(norm(row.get('player')));stat=normalize_stat(row.get('stat'))
            if r and stat in STATS:
                d=r['projections'][stat];row['ancillary_projection_v2']=r;row['projection']=d['mean'];row['proj']=d['mean'];row['projection_floor']=d['p10'];row['projection_median']=d['p50'];row['projection_ceiling']=d['p90'];row['projection_confidence_v2']=r['confidence'];count+=1
            props.append(row)
        master['props']=props;master['ancillary_projection_v2']={'summary':{'players':len(index),'props_attached':sum(1 for x in props if x.get('ancillary_projection_v2'))},'source':'data/dashboard/wnba_ancillary_projection_v2.json'};dump(path,master)
    return count

def build(target:str)->dict[str,Any]:
    hs=histories();mins=minute_index();ranks=rank_index();master=next((load(p,{}) for p in MASTER_PATHS if p.exists()),{});props=defaultdict(list)
    for p in master.get('props',[]) or []:
        if p.get('player'):props[norm(p.get('player'))].append(p)
    rows=[];idx={}
    for key,m in mins.items():
        h=hs.get(key,[])
        if not h:continue
        r=project(str(m.get('player')),h,m,ranks);r['markets']=compare(r,props.get(key,[]));rows.append(r);idx[key]=r
    rows.sort(key=lambda r:(r.get('team') or '',-r['projected_3pm'],r['player']));attached=attach(idx);markets=[m for r in rows for m in r.get('markets',[])]
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','schema_version':'2.0','summary':{'players_projected':len(rows),'props_attached':attached,'simulations_per_player':SIMULATIONS,'market_comparisons':len(markets),'bet_markets':sum(m['action']=='BET' for m in markets),'complete':sum(r['data_quality_status']=='complete' for r in rows),'partial':sum(r['data_quality_status']=='partial' for r in rows),'limited':sum(r['data_quality_status']=='limited' for r in rows)},'projections':rows,'top_market_edges':sorted(markets,key=lambda m:m.get('expected_value_per_unit') if m.get('expected_value_per_unit') is not None else -999,reverse=True)[:25],'methodology':{'simulation':'10,000 shared minute-based count simulations per player','distribution':'Poisson count outcomes around historical per-minute rates','matchup_policy':'pace/minutes/position adjusted stat allowance when sample-qualified','market_policy':'sportsbook lines do not alter projections','missing_data_policy':'neutral fallback with explicit quality status'}}
    for p in OUTS:dump(p,report)
    print('Ancillary Projection v2:',report['summary']);return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();build(a.date)
if __name__=='__main__':main()
