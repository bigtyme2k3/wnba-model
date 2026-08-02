"""Post-process injury redistribution with rotation and market-availability guardrails."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DASH=Path('data/dashboard')
WH=Path('data/warehouse')
MASTER_PATHS=[DASH/'wnba_master.json',Path('data/master/wnba_master.json')]
REPORT_PATHS=[DASH/'wnba_injury_intelligence.json',WH/'wnba_injury_intelligence.json']


def load(path:Path,default:Any):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default


def dump(path:Path,data:Any):
    path.parent.mkdir(parents=True,exist_ok=True)
    json.dump(data,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)


def norm(v:Any)->str:
    return ' '.join(str(v or '').strip().lower().split())


def prop_players()->set[str]:
    players=set()
    for path in MASTER_PATHS:
        data=load(path,{})
        for row in data.get('props',[]) or []:
            name=norm(row.get('player'))
            if name:players.add(name)
    return players


def guard(report:dict)->dict:
    markets=prop_players()
    adjusted=[]
    for row in report.get('adjustments',[]) or []:
        item=dict(row)
        if str(item.get('severity','')).upper()!='BENEFICIARY':
            adjusted.append(item);continue
        base=float(item.get('base_minutes') or 0)
        delta=float(item.get('minutes_delta') or 0)
        market_available=norm(item.get('player')) in markets
        rotation_player=base>=12
        verified=bool(market_available and rotation_player)
        # A player without a market can still play, but a large projected boost is
        # speculative. Cap it and remove it from headline winner rankings.
        max_delta=5.0 if verified else 2.5
        if not rotation_player:max_delta=min(max_delta,1.5)
        if delta>max_delta:
            item['minutes_delta_pre_guard']=round(delta,1)
            item['minutes_delta']=round(max_delta,1)
            item['projected_minutes']=round(base+max_delta,1)
            usage_delta=float(item.get('usage_delta') or 0)
            item['usage_delta']=round(min(usage_delta,2.0 if verified else 0.75),2)
            item['projection_factor']=round((item['projected_minutes']/max(base,1))*(1+item['usage_delta']/100),4)
        item['market_available']=market_available
        item['rotation_verified']=rotation_player
        item['beneficiary_tier']='VERIFIED' if verified else 'SPECULATIVE'
        item['headline_eligible']=verified
        if not verified:
            item['severity']='SPECULATIVE'
            item['detail']=(item.get('detail') or 'Minutes redistributed')+'; no verified prop market or rotation confirmation'
        adjusted.append(item)
    report['adjustments']=adjusted
    report.setdefault('summary',{})['verified_beneficiaries']=sum(1 for x in adjusted if x.get('headline_eligible'))
    report['summary']['speculative_beneficiaries']=sum(1 for x in adjusted if str(x.get('severity','')).upper()=='SPECULATIVE')
    report['summary']['beneficiary_guard']='verified prop market + 12 minute rotation baseline; speculative boosts capped and excluded from headlines'
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
