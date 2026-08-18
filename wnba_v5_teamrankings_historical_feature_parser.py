"""Parse frozen historical TeamRankings matchup pages into leakage-safe research rows.
No current snapshot fallback is permitted. This stage inventories point-in-time metrics
embedded in each frozen page and emits a normalized historical feature evidence table.
"""
from __future__ import annotations
import html,json,re
from datetime import datetime,timezone
from pathlib import Path

MAN=Path('data/warehouse/teamrankings/historical_matchup_manifest.json')
ROOT=Path('data/warehouse/teamrankings/historical')
OUT=Path('data/dashboard/wnba_v5_teamrankings_historical_features.json')
WARE=Path('data/warehouse/teamrankings/historical_features')
# Labels chosen to mirror the current V5 TeamRankings families while preserving raw values.
LABELS={
 'points_paint':['Opponent Points in Paint per Game','Points in Paint per Game'],
 'two_pt_pct':['Opponent 2 Point %','Opponent Two Point %','2 Point %'],
 'three_pt_pct':['Opponent 3 Point %','Opponent Three Point %','3 Point %'],
 'efg_pct':['Opponent Effective Field Goal %','Effective Field Goal %'],
 'off_reb':['Opponent Offensive Rebounding %','Offensive Rebounding %'],
 'def_reb':['Opponent Defensive Rebounding %','Defensive Rebounding %'],
 'assists':['Opponent Assists per Game','Assists per Game'],
 'turnovers':['Opponent Turnovers per Possession','Turnovers per Possession'],
 'possessions':['Possessions per Game'],
 'fouls':['Opponent Personal Fouls per Game','Personal Fouls per Game'],
 'fastbreak':['Opponent Fastbreak Points per Game','Fastbreak Points per Game'],
 'def_efficiency':['Defensive Efficiency'],
}
NUM=r'[-+]?\d+(?:\.\d+)?%?'
def textify(s):
 s=re.sub(r'<script\b[^>]*>.*?</script>',' ',s,flags=re.I|re.S); s=re.sub(r'<style\b[^>]*>.*?</style>',' ',s,flags=re.I|re.S)
 s=re.sub(r'<[^>]+>',' ',s); return re.sub(r'\s+',' ',html.unescape(s)).strip()
def extract(txt,label):
 # retain nearby numeric sequence; exact column semantics are audited in challenger stage
 m=re.search(re.escape(label)+r'.{0,220}?('+NUM+r'(?:\s+'+NUM+r'){1,8})',txt,re.I)
 if not m:return []
 return [float(x.rstrip('%')) for x in re.findall(NUM,m.group(1))]
def main():
 man=json.loads(MAN.read_text()); rows=[]; parsed=0
 for x in man.get('matchups',[]):
  date=x['date']; key=re.sub(r'[^a-z0-9]+','-',x['game'].lower()).strip('-')[:100]; p=ROOT/date/f'{key}.html'
  rec={k:x.get(k) for k in ('date','game','game_id','away_team','home_team')}; rec['raw_path']=str(p); rec['metrics']={}
  if not p.exists(): rec['status']='MISSING_FROZEN_EVIDENCE'; rows.append(rec); continue
  txt=textify(p.read_text(encoding='utf-8',errors='replace'))
  for metric,labels in LABELS.items():
   for label in labels:
    vals=extract(txt,label)
    if vals: rec['metrics'][metric]={'label':label,'values':vals}; break
  rec['metric_groups_found']=len(rec['metrics']); rec['status']='PARSED' if rec['metrics'] else 'NO_METRICS_FOUND'
  parsed+=rec['status']=='PARSED'; rows.append(rec)
 payload={'version':'V5','module':'TEAMRANKINGS_HISTORICAL_FEATURE_PARSER','status':'RESEARCH_ONLY','research_only':True,'production_ready':False,'lookahead_safe':True,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'games_manifest':len(rows),'games_parsed':parsed,'games_without_metrics':sum(r['status']!='PARSED' for r in rows),'policy':'Only frozen date-specific HTML is parsed; no current TeamRankings snapshot fallback. Numeric column semantics remain raw until audited before challenger use.','rows':rows}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2)+'\n')
 WARE.mkdir(parents=True,exist_ok=True); (WARE/'historical_feature_evidence.json').write_text(json.dumps(payload,indent=2)+'\n')
 print(json.dumps({k:payload[k] for k in ('games_manifest','games_parsed','games_without_metrics')},indent=2))
if __name__=='__main__':main()
