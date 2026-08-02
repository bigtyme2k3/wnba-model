"""Post-process injury redistribution with rotation, role and market guardrails."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

DASH=Path('data/dashboard')
WH=Path('data/warehouse')
RAW=Path('data/raw')
MASTER_PATHS=[DASH/'wnba_master.json',Path('data/master/wnba_master.json')]
REPORT_PATHS=[DASH/'wnba_injury_intelligence.json',WH/'wnba_injury_intelligence.json']
PLAYERS_PATH=RAW/'wnba_players_live.json'


def load(path:Path,default:Any):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default


def dump(path:Path,data:Any):
    path.parent.mkdir(parents=True,exist_ok=True)
    json.dump(data,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)


def norm(v:Any)->str:
    return ' '.join(str(v or '').strip().lower().split())


def sf(v:Any,d:float=0.0)->float:
    try:return float(v)
    except Exception:return d


def position_group(value:Any)->str:
    s=str(value or '').upper().replace('-','/').replace(' ','')
    if 'C' in s:return 'BIG'
    if 'F' in s:return 'WING'
    if 'G' in s:return 'GUARD'
    return 'UNKNOWN'


def player_context()->dict[str,dict]:
    raw=load(PLAYERS_PATH,{})
    rows=[]
    if isinstance(raw,dict):
        for name,item in raw.items():
            if isinstance(item,dict):
                row=dict(item);row.setdefault('player',name);rows.append(row)
    elif isinstance(raw,list):rows=raw
    out={}
    for row in rows:
        name=row.get('player') or row.get('name') or row.get('athlete_display_name')
        if not name:continue
        out[norm(name)]={
            'position':str(row.get('position') or row.get('pos') or ''),
            'position_group':position_group(row.get('position') or row.get('pos')),
            'starter':bool(row.get('starter') or row.get('is_starter') or row.get('projected_starter')),
            'usage':sf(row.get('usage_rate') or row.get('usage') or row.get('usg_pct')),
        }
    return out


def prop_players()->set[str]:
    players=set()
    for path in MASTER_PATHS:
        data=load(path,{})
        for row in data.get('props',[]) or []:
            name=norm(row.get('player'))
            if name:players.add(name)
    return players


def compatibility(candidate_group:str, missing_groups:set[str])->float:
    if not missing_groups or candidate_group=='UNKNOWN':return 1.0
    if candidate_group in missing_groups:return 1.35
    if candidate_group=='WING':return 1.12
    return 0.82


def role_score(item:dict,ctx:dict,market_available:bool,missing_groups:set[str])->float:
    base=sf(item.get('base_minutes'))
    usage=sf(item.get('usage') or ctx.get('usage'))
    if 0<usage<1:usage*=100
    headroom=max(0.0,38.0-base)
    rotation=min(1.5,max(.35,base/24.0))
    market=1.25 if market_available else .62
    starter=1.18 if ctx.get('starter') else 1.0
    fit=compatibility(ctx.get('position_group','UNKNOWN'),missing_groups)
    return max(.01,rotation*market*starter*fit*(1+max(0,usage)/150.0)*max(.35,headroom/12.0))


def guard(report:dict)->dict:
    markets=prop_players();contexts=player_context()
    rows=[dict(x) for x in report.get('adjustments',[]) or []]
    injured_by_team=defaultdict(list);beneficiaries_by_team=defaultdict(list)
    for item in rows:
        severity=str(item.get('severity','')).upper()
        if severity=='BENEFICIARY':beneficiaries_by_team[str(item.get('team') or '')].append(item)
        elif severity in {'OUT','DOUBTFUL','QUESTIONABLE','PROBABLE'}:injured_by_team[str(item.get('team') or '')].append(item)

    for team,beneficiaries in beneficiaries_by_team.items():
        missing_groups={contexts.get(norm(x.get('player')),{}).get('position_group','UNKNOWN') for x in injured_by_team.get(team,[])}-{'UNKNOWN'}
        requested_total=sum(max(0,sf(x.get('minutes_delta_pre_guard',x.get('minutes_delta')))) for x in beneficiaries)
        scored=[]
        for item in beneficiaries:
            key=norm(item.get('player'));ctx=contexts.get(key,{})
            base=sf(item.get('base_minutes'));market_available=key in markets
            rotation_player=base>=12
            verified=bool(market_available and rotation_player)
            score=role_score(item,ctx,market_available,missing_groups)
            cap=(6.5 if verified else 2.5)
            if ctx.get('starter') and verified:cap=8.0
            if not rotation_player:cap=min(cap,1.5)
            cap=min(cap,max(0,38-base))
            scored.append((item,ctx,market_available,rotation_player,verified,score,cap))
        total_score=sum(x[5] for x in scored) or 1.0
        provisional=[]
        for item,ctx,market_available,rotation_player,verified,score,cap in scored:
            allocation=min(cap,requested_total*(score/total_score))
            provisional.append([item,ctx,market_available,rotation_player,verified,score,cap,allocation])
        # Redistribute leftover only to candidates with remaining capacity.
        leftover=max(0,requested_total-sum(x[7] for x in provisional))
        for _ in range(4):
            eligible=[x for x in provisional if x[7]+.05<x[6]]
            if leftover<.05 or not eligible:break
            denom=sum(x[5] for x in eligible) or 1
            used=0.0
            for x in eligible:
                add=min(x[6]-x[7],leftover*(x[5]/denom));x[7]+=add;used+=add
            leftover=max(0,leftover-used)
        for item,ctx,market_available,rotation_player,verified,score,cap,allocation in provisional:
            original=sf(item.get('minutes_delta_pre_guard',item.get('minutes_delta')))
            base=sf(item.get('base_minutes'));allocation=round(allocation,1)
            item['minutes_delta_pre_guard']=round(original,1)
            item['minutes_delta']=allocation
            item['projected_minutes']=round(base+allocation,1)
            usage_original=sf(item.get('usage_delta'))
            usage_cap=2.5 if verified else .75
            share=(allocation/requested_total) if requested_total else 0
            item['usage_delta']=round(min(usage_cap,max(0,usage_original,share*4.0)),2)
            item['projection_factor']=round((item['projected_minutes']/max(base,1))*(1+item['usage_delta']/100),4)
            item['market_available']=market_available
            item['rotation_verified']=rotation_player
            item['position_group']=ctx.get('position_group','UNKNOWN')
            item['role_score']=round(score,3)
            item['redistribution_method']='role_weighted_v2'
            item['beneficiary_tier']='VERIFIED' if verified else 'SPECULATIVE'
            item['headline_eligible']=verified
            if not verified:
                item['severity']='SPECULATIVE'
                item['detail']=(item.get('detail') or 'Minutes redistributed')+'; speculative until prop market and rotation are confirmed'
            else:
                item['detail']=(item.get('detail') or 'Minutes redistributed')+'; weighted by rotation, position fit, usage, headroom and market availability'

    report['adjustments']=rows
    summary=report.setdefault('summary',{})
    summary['verified_beneficiaries']=sum(1 for x in rows if x.get('headline_eligible'))
    summary['speculative_beneficiaries']=sum(1 for x in rows if str(x.get('severity','')).upper()=='SPECULATIVE')
    summary['beneficiary_guard']='role-weighted v2: rotation, position fit, usage, starter status, headroom and market availability'
    summary['redistribution_unallocated_minutes']=round(sum(max(0,sf(i.get('missing_minutes'))-sf(i.get('minutes_reallocated'))) for i in report.get('team_impacts',[]) or []),1)
    return report


def main():
    latest=None
    for path in REPORT_PATHS:
        data=load(path,None)
        if data is None:continue
        latest=guard(data);dump(path,latest)
    if latest is None:raise SystemExit('injury intelligence report missing')
    print(json.dumps(latest.get('summary',{}),indent=2))

if __name__=='__main__':main()
