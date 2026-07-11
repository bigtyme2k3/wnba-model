"""Build production injury intelligence, minute redistribution, and recommendation guardrails."""
from __future__ import annotations
import argparse,csv,json,math,os,re
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

RAW=Path('data/raw'); DASH=Path('data/dashboard'); WH=Path('data/warehouse')
MASTER_PATHS=[DASH/'wnba_master.json',Path('data/master/wnba_master.json')]
DECISION_PATHS=[
 WH/'wnba_decision_engine_final.json',DASH/'wnba_decision_engine_final.json',
 WH/'wnba_portfolio_optimizer_v2.json',DASH/'wnba_portfolio_optimizer_v2.json',
 WH/'wnba_risk_allocation.json',DASH/'wnba_risk_allocation.json',
 WH/'wnba_portfolio_dashboard.json',DASH/'wnba_portfolio_dashboard.json',
]
STATUS_FACTORS={'OUT':0.0,'DOUBTFUL':0.15,'QUESTIONABLE':0.65,'PROBABLE':0.92,'ACTIVE':1.0,'UNKNOWN':0.80}
CONF_PENALTY={'OUT':100,'DOUBTFUL':35,'QUESTIONABLE':15,'PROBABLE':4,'ACTIVE':0,'UNKNOWN':10}


def load_json(path:Path,default:Any):
 try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
 except Exception:return default


def dump(path:Path,data:Any):
 path.parent.mkdir(parents=True,exist_ok=True);json.dump(data,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)


def norm(v:Any)->str:
 s=str(v or '').lower().replace('’',"'");s=re.sub(r'\b(jr\.?|sr\.?|ii|iii|iv)\b','',s);return ' '.join(re.sub(r"[^a-z0-9' -]",'',s).split())


def sf(v:Any,d=0.0):
 try:
  x=float(v);return x if math.isfinite(x) else d
 except Exception:return d


def read_csv(path:Path):
 if not path.exists():return []
 try:return list(csv.DictReader(path.open(encoding='utf-8',newline='')))
 except Exception:return []


def player_pool():
 raw=load_json(RAW/'wnba_players_live.json',{})
 rows=[]
 if isinstance(raw,dict):
  for name,item in raw.items():
   if isinstance(item,dict):
    r=dict(item);r.setdefault('player',name);rows.append(r)
 elif isinstance(raw,list):rows=raw
 by={}
 for r in rows:
  name=str(r.get('player') or r.get('athlete_display_name') or r.get('name') or '')
  if not name:continue
  mpg=sf(r.get('roll5_mpg') or r.get('mpg') or r.get('minutes') or r.get('minutes_per_game') or r.get('avg_minutes'),0)
  usage=sf(r.get('usage_rate') or r.get('usage') or r.get('usg_pct'),0)
  if usage and usage<1:usage*=100
  by[norm(name)]={'player':name,'team':str(r.get('team') or r.get('team_name') or ''),'position':str(r.get('position') or r.get('pos') or ''),'mpg':mpg,'usage':usage,'raw':r}
 return by


def todays_teams(master,target_date):
 teams=set()
 games=master.get('games',[]) or master.get('today_games',[]) or []
 for g in games:
  game_date=str(g.get('game_date') or master.get('target_date') or '')[:10]
  bucket=str(g.get('bucket') or 'today')
  if game_date and game_date!=target_date:continue
  if bucket not in {'today',''}:continue
  for k in ('home_team','away_team','home','away'):
   if g.get(k):teams.add(str(g[k]))
 return teams


def guard_rows(rows,adjustments):
 out=[]
 for r in rows or []:
  row=dict(r);adj=adjustments.get(norm(row.get('player')))
  if adj:
   row['injury_status']=adj['severity'];row['injury_detail']=adj.get('detail');row['injury_adjusted']=True
   row['projected_minutes']=adj['projected_minutes'];row['minutes_delta']=adj['minutes_delta'];row['injury_projection_factor']=adj['projection_factor']
   if adj['is_out']:
    row['final_action']='PASS';row['recommendation']='PASS';row['eligible']=False;row['eligible_for_bet']=False;row['blocked_reason']=f"{adj['severity']} injury status"
    failures=list(row.get('guardrail_failures') or [])
    if row['blocked_reason'] not in failures:failures.append(row['blocked_reason'])
    row['guardrail_failures']=failures
   elif adj['severity'] in {'QUESTIONABLE','UNKNOWN'}:
    row['risk_level']='HIGH';row['injury_warning']=True
    row['confidence']=max(0,round(sf(row.get('confidence',row.get('final_score')),0)-adj['confidence_penalty'],1))
    row['final_score']=row['confidence']
  out.append(row)
 return out


def build(target_date:str):
 master=next((load_json(p,{}) for p in MASTER_PATHS if p.exists()),{})
 teams=todays_teams(master,target_date);players=player_pool();injuries=read_csv(RAW/f'injuries_{target_date}.csv') or read_csv(RAW/'injuries_today.csv')
 filtered=[]
 for r in injuries:
  if teams and r.get('team') not in teams:continue
  sev=str(r.get('severity') or r.get('status') or 'UNKNOWN').upper()
  if sev not in STATUS_FACTORS:sev='UNKNOWN'
  item=dict(r);item['severity']=sev;item['player_key']=norm(r.get('player'));filtered.append(item)
 injury_by={r['player_key']:r for r in filtered if r['player_key']}
 roster=defaultdict(list)
 for p in players.values():
  if p['team']:roster[p['team']].append(p)
 adjustments={};beneficiaries=[];team_impacts=[]
 for team in teams or roster.keys():
  missing_minutes=0.0;missing_usage=0.0;team_inj=[r for r in filtered if r.get('team')==team]
  for inj in team_inj:
   p=players.get(inj['player_key'],{});base=sf(p.get('mpg'),25);usage=sf(p.get('usage'),18)
   factor=STATUS_FACTORS[inj['severity']];proj=round(base*factor,1)
   adjustments[inj['player_key']]={'player':inj.get('player'),'team':team,'severity':inj['severity'],'base_minutes':base,'projected_minutes':proj,'minutes_delta':round(proj-base,1),'usage':usage,'projection_factor':factor,'confidence_penalty':CONF_PENALTY[inj['severity']],'is_out':inj['severity'] in {'OUT','DOUBTFUL'},'detail':inj.get('detail',''),'source':inj.get('source','')}
   missing_minutes+=max(0,base-proj);missing_usage+=max(0,usage*(1-factor))
  candidates=[p for p in roster.get(team,[]) if norm(p['player']) not in injury_by and p['mpg']>0]
  candidates.sort(key=lambda p:p['mpg'],reverse=True);weights=[]
  for p in candidates[:8]:
   headroom=max(0,38-p['mpg']);role=max(1,p['mpg'])*(1+max(0,p['usage'])/100)*max(.2,headroom/10);weights.append((p,role,headroom))
  total=sum(w for _,w,_ in weights) or 1;allocated=0
  for p,w,headroom in weights:
   share=w/total;boost=min(headroom,missing_minutes*share);usage_boost=min(7.0,missing_usage*share)
   if boost<0.2 and usage_boost<0.2:continue
   key=norm(p['player']);base=p['mpg'];proj=min(38,base+boost);allocated+=boost
   adjustments[key]={'player':p['player'],'team':team,'severity':'BENEFICIARY','base_minutes':base,'projected_minutes':round(proj,1),'minutes_delta':round(proj-base,1),'usage':p['usage'],'usage_delta':round(usage_boost,2),'projection_factor':round((proj/max(base,1))*(1+usage_boost/100),4),'confidence_penalty':0,'is_out':False,'detail':'Minutes/usage redistributed from unavailable teammates','source':'injury_intelligence'}
   beneficiaries.append(adjustments[key])
  team_impacts.append({'team':team,'injuries':len(team_inj),'missing_minutes':round(missing_minutes,1),'minutes_reallocated':round(allocated,1),'impact_level':'HIGH' if missing_minutes>=45 else 'MED' if missing_minutes>=20 else 'LOW'})
 blocked=limited=adjusted=0
 for path in MASTER_PATHS:
  data=load_json(path,{})
  if not data:continue
  props=[]
  for prop in data.get('props',[]) or []:
   key=norm(prop.get('player'));adj=adjustments.get(key);row=dict(prop)
   if adj:
    row['injury_status']=adj['severity'];row['injury_detail']=adj['detail'];row['injury_adjusted']=True;row['projected_minutes']=adj['projected_minutes'];row['minutes_delta']=adj['minutes_delta'];row['injury_projection_factor']=adj['projection_factor']
    projection=row.get('projection',row.get('proj'))
    if projection not in (None,''):
     newp=round(sf(projection)*adj['projection_factor'],2);row['projection_pre_injury']=projection;row['projection']=newp;row['proj']=newp
    conf=sf(row.get('confidence',row.get('final_score')),0);row['confidence_pre_injury']=conf;row['confidence']=max(0,round(conf-adj['confidence_penalty'],1))
    if adj['is_out']:
     row['eligible']=False;row['eligible_for_bet']=False;row['final_action']='PASS';row['recommendation']='PASS';row['blocked_reason']=f"{adj['severity']} injury status";blocked+=1
    elif adj['severity'] in {'QUESTIONABLE','UNKNOWN'}:row['injury_warning']=True;limited+=1
    adjusted+=1
   props.append(row)
  data['props']=props
  data['injury_intelligence']={'target_date':target_date,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'injuries':filtered,'adjustments':list(adjustments.values()),'team_impacts':team_impacts,'summary':{'teams_on_slate':len(teams),'injuries_on_slate':len(filtered),'out_or_doubtful':sum(r['severity'] in {'OUT','DOUBTFUL'} for r in filtered),'questionable':sum(r['severity']=='QUESTIONABLE' for r in filtered),'beneficiaries':len(beneficiaries),'props_adjusted':adjusted,'props_blocked':blocked,'props_limited':limited}}
  dump(path,data)
 for path in DECISION_PATHS:
  data=load_json(path,None)
  if data is None:continue
  if isinstance(data,list):data=guard_rows(data,adjustments)
  elif isinstance(data,dict):
   for k in ('rows','decisions','top_decisions','qualified_bets','final_decisions','recommended_card','candidates','bets','portfolio','allocations'):
    if isinstance(data.get(k),list):data[k]=guard_rows(data[k],adjustments)
   if 'summary' in data and isinstance(data['summary'],dict):
    data['summary']['injury_blocked']=sum(1 for k in ('qualified_bets','recommended_card') for r in data.get(k,[]) if r.get('blocked_reason'))
  dump(path,data)
 report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target_date,'freshness_minutes':0,'teams':sorted(teams),'injuries':filtered,'adjustments':list(adjustments.values()),'team_impacts':team_impacts,'summary':{'injuries_on_slate':len(filtered),'out_or_doubtful':sum(r['severity'] in {'OUT','DOUBTFUL'} for r in filtered),'questionable':sum(r['severity']=='QUESTIONABLE' for r in filtered),'probable':sum(r['severity']=='PROBABLE' for r in filtered),'beneficiaries':len(beneficiaries),'recommendations_blocked':blocked,'recommendations_limited':limited}}
 dump(WH/'wnba_injury_intelligence.json',report);dump(DASH/'wnba_injury_intelligence.json',report)
 with (RAW/'minute_projections.csv').open('w',encoding='utf-8',newline='') as f:
  cols=['game_date','player','team','severity','base_minutes','proj_min','minutes_delta','usage_delta','projection_factor','is_out'];w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
  for a in adjustments.values():w.writerow({'game_date':target_date,'player':a['player'],'team':a['team'],'severity':a['severity'],'base_minutes':a['base_minutes'],'proj_min':a['projected_minutes'],'minutes_delta':a['minutes_delta'],'usage_delta':a.get('usage_delta',0),'projection_factor':a['projection_factor'],'is_out':a['is_out']})
 print(json.dumps(report['summary'],indent=2));return report


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--date',required=True);args=ap.parse_args();build(args.date)
if __name__=='__main__':main()
