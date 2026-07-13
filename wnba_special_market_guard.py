"""Normalize supported WNBA prop markets and hide unsupported rows.

Double-double and triple-double markets are intentionally excluded from the WNBA
model because they are sparse, rarely priced consistently, and not part of the
current production market set.
"""
from __future__ import annotations
import json, math, re
from pathlib import Path
from typing import Any

MASTER_PATHS=[Path('data/dashboard/wnba_master.json'),Path('data/master/wnba_master.json')]
SUPPORTED={'PTS','REB','AST','PRA','PR','PA','RA','3PM','STL','BLK','TOV','BLK+STL'}
REMOVED={'DD','TD'}
ALIASES={
 'POINTS':'PTS','REBOUNDS':'REB','ASSISTS':'AST','THREES':'3PM','3PTM':'3PM','3-POINTERS':'3PM',
 'POINTS_REBOUNDS_ASSISTS':'PRA','POINTS+REBOUNDS+ASSISTS':'PRA','PTS+REB+AST':'PRA',
 'POINTS_REBOUNDS':'PR','PTS+REB':'PR','POINTS_ASSISTS':'PA','PTS+AST':'PA','REBOUNDS_ASSISTS':'RA','REB+AST':'RA',
 'BLOCKS_STEALS':'BLK+STL','BLOCKS+STEALS':'BLK+STL','STOCKS':'BLK+STL',
 'DOUBLE_DOUBLE':'DD','DOUBLE DOUBLE':'DD','DD YES':'DD','TRIPLE_DOUBLE':'TD','TRIPLE DOUBLE':'TD','TD YES':'TD'
}

def load(path,default):
 try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
 except Exception:return default

def clean_stat(value:Any)->str:
 raw=str(value or '').upper().strip().replace('-','_');raw=re.sub(r'\s+',' ',raw)
 return ALIASES.get(raw,ALIASES.get(raw.replace(' ','_'),raw.replace(' ','_')))

def sf(v,d=0.0):
 try:
  x=float(v);return x if math.isfinite(x) else d
 except Exception:return d

def special_value(item:dict[str,Any],stat:str):
 v=item.get('value')
 if v is not None and stat!='BLK+STL':return sf(v)
 if stat=='BLK+STL':return sf(item.get('blk'))+sf(item.get('stl'))
 return None

def main():
 for path in MASTER_PATHS:
  data=load(path,{})
  if not data:continue
  kept=[];hidden=[];removed=[];converted=0
  for prop in data.get('props',[]) or []:
   stat=clean_stat(prop.get('stat') or prop.get('market') or prop.get('stat_raw'));prop['stat']=stat
   if stat in REMOVED:
    prop['market_support']='removed';prop['support_reason']='Double-double and triple-double markets are excluded from WNBA production';removed.append(prop);continue
   if stat not in SUPPORTED:
    prop['market_support']='unsupported';prop['support_reason']='No reliable full-game grading rule';hidden.append(prop);continue
   prop['market_support']='supported';histories=prop.get('last10') or []
   if stat=='BLK+STL' and histories:
    rebuilt=[]
    for item in histories:
     val=special_value(item,stat)
     if val is None:continue
     row=dict(item);row['value']=int(val) if float(val).is_integer() else round(val,2);rebuilt.append(row)
    prop['last10']=rebuilt[:10];prop['last5']=rebuilt[:5];prop['last10_values']=[x['value'] for x in prop['last10']];prop['last5_values']=[x['value'] for x in prop['last5']];prop['history_games_available']=len(prop['last10']);converted+=1
   if len(prop.get('last5') or [])<5:
    prop['market_support']='limited_history';prop['support_reason']=f"Only {len(prop.get('last5') or [])} completed games"
   kept.append(prop)
  data['props']=kept;data['hidden_unsupported_props']=len(hidden);data['removed_rare_props']=len(removed)
  data['special_market_diagnostics']={'supported_rows':len(kept),'hidden_rows':len(hidden),'removed_rare_rows':len(removed),'special_rows_converted':converted,'supported_markets':sorted(SUPPORTED),'removed_markets':sorted(REMOVED)}
  if isinstance(data.get('summary'),dict):data['summary']['props']=len(kept)
  path.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8');print(path,data['special_market_diagnostics'])

if __name__=='__main__':main()
