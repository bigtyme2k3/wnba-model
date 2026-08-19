"""Parse frozen historical TeamRankings matchup pages into leakage-safe research rows.

Only genuine date-specific matchup pages are eligible. TeamRankings may return a
200 OK schedule page when a matchup URL does not exist; those fallbacks are explicitly
quarantined rather than treated as missing stats or parsed as evidence.
"""
from __future__ import annotations
import html,json,re
from datetime import datetime,timezone
from pathlib import Path

MAN=Path('data/warehouse/teamrankings/historical_matchup_manifest.json')
ROOT=Path('data/warehouse/teamrankings/historical')
OUT=Path('data/dashboard/wnba_v5_teamrankings_historical_features.json')
WARE=Path('data/warehouse/teamrankings/historical_features')
LABELS={
 'points_paint':['Opp Pts in Paint/Gm','Opponent Points in Paint per Game','Pts in Paint/Gm','Points in Paint per Game'],
 'two_pt_pct':['Opp Two Point %','Opponent 2 Point %','Opponent Two Point %','Two Point %','2 Point %'],
 'three_pt_pct':['Opp Three Point %','Opponent 3 Point %','Opponent Three Point %','Three Point %','3 Point %'],
 'efg_pct':['Opp Effective FG %','Opponent Effective Field Goal %','Effective FG %','Effective Field Goal %'],
 'off_reb':['Opp Off Rebound %','Opponent Offensive Rebounding %','Off Rebound %','Offensive Rebounding %'],
 'def_reb':['Opp Def Rebound %','Opponent Defensive Rebounding %','Def Rebound %','Defensive Rebounding %'],
 'assists':['Opp Assists/FGM','Opponent Assists/FGM','Assists/FGM','Opp Assists/Game','Opponent Assists per Game','Assists/Game'],
 'turnovers':['Opp Turnovers/Play','Opponent Turnovers per Possession','Turnovers/Play','Turnovers per Possession'],
 'possessions':['Possessions/Gm','Possessions per Game'],
 'fouls':['Opp Personal Fouls/Gm','Opponent Personal Fouls per Game','Personal Fouls/Gm','Personal Fouls per Game'],
 'fastbreak':['Opp Fastbreak Pts/Gm','Opponent Fastbreak Points per Game','Fastbreak Pts/Gm','Fastbreak Points per Game'],
 'def_efficiency':['Def Efficiency','Defensive Efficiency'],
}
NUM=r'[-+]?\d+(?:\.\d+)?%?'
def textify(s):
 s=re.sub(r'<script\b[^>]*>.*?</script>',' ',s,flags=re.I|re.S)
 s=re.sub(r'<style\b[^>]*>.*?</style>',' ',s,flags=re.I|re.S)
 s=re.sub(r'<[^>]+>',' ',s)
 return re.sub(r'\s+',' ',html.unescape(s)).strip()
def title_of(s):
 m=re.search(r'<title>(.*?)</title>',s,re.I|re.S)
 return textify(m.group(1)) if m else ''
def extract(txt,label):
 m=re.search(re.escape(label)+r'.{0,260}?('+NUM+r'(?:\s+'+NUM+r'){1,10})',txt,re.I)
 if not m:return []
 return [float(x.rstrip('%')) for x in re.findall(NUM,m.group(1))]
def matchup_identity_ok(raw,away,home):
 title=title_of(raw)
 if not title:return False,'MISSING_TITLE',title
 if 'Daily Schedule' in title:return False,'SCHEDULE_FALLBACK',title
 if 'WNBA Games:' not in title:return False,'NON_MATCHUP_PAGE',title
 # Valid matchup pages identify the teams in title/body. Use surname/franchise tokens,
 # avoiding brittle dependence on exact city naming.
 txt=textify(raw[:120000]).lower()
 at=(away or '').lower().split()[-1]; ht=(home or '').lower().split()[-1]
 if at not in txt or ht not in txt:return False,'TEAM_IDENTITY_MISMATCH',title
 return True,'VALID_MATCHUP',title

def main():
 man=json.loads(MAN.read_text()); rows=[]; parsed=0; valid=0; invalid=0
 for x in man.get('matchups',[]):
  date=x['date']; key=re.sub(r'[^a-z0-9]+','-',x['game'].lower()).strip('-')[:100]; p=ROOT/date/f'{key}.html'
  rec={k:x.get(k) for k in ('date','game','game_id','away_team','home_team','teamrankings_url')}; rec['raw_path']=str(p); rec['metrics']={}
  if not p.exists(): rec['status']='MISSING_FROZEN_EVIDENCE'; rows.append(rec); continue
  raw=p.read_text(encoding='utf-8',errors='replace')
  ok,identity,title=matchup_identity_ok(raw,x.get('away_team'),x.get('home_team'))
  rec['page_title']=title; rec['page_identity']=identity
  if not ok:
   rec['status']='INVALID_PAGE_IDENTITY'; invalid+=1; rows.append(rec); continue
  valid+=1; txt=textify(raw)
  for metric,labels in LABELS.items():
   for label in labels:
    vals=extract(txt,label)
    if vals: rec['metrics'][metric]={'label':label,'values':vals}; break
  rec['metric_groups_found']=len(rec['metrics'])
  rec['status']='PARSED' if rec['metrics'] else 'VALID_PAGE_NO_METRICS'
  parsed+=rec['status']=='PARSED'; rows.append(rec)
 payload={'version':'V5','module':'TEAMRANKINGS_HISTORICAL_FEATURE_PARSER','status':'RESEARCH_ONLY','research_only':True,'production_ready':False,'lookahead_safe':True,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'games_manifest':len(rows),'valid_matchup_pages':valid,'invalid_fallback_pages':invalid,'games_parsed':parsed,'valid_pages_without_metrics':sum(r['status']=='VALID_PAGE_NO_METRICS' for r in rows),'missing_frozen_evidence':sum(r['status']=='MISSING_FROZEN_EVIDENCE' for r in rows),'policy':'Only frozen date-specific HTML with verified matchup-page identity is parsed. Schedule fallbacks and identity mismatches are quarantined. No current TeamRankings snapshot fallback. Numeric column semantics remain raw until audited before challenger use.','rows':rows}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2)+'\n')
 WARE.mkdir(parents=True,exist_ok=True); (WARE/'historical_feature_evidence.json').write_text(json.dumps(payload,indent=2)+'\n')
 print(json.dumps({k:payload[k] for k in ('games_manifest','valid_matchup_pages','invalid_fallback_pages','games_parsed','valid_pages_without_metrics')},indent=2))
if __name__=='__main__':main()
