"""V5 TeamRankings matchup intelligence collector.

Research/shadow data source only. Fetches selected public WNBA team-stat tables,
normalizes season/recent/home/away splits, and freezes daily snapshots. It does
not alter production predictions.
"""
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BASE='https://www.teamrankings.com/wnba/stat/'
METRICS={
 'opp_points_paint':'opponent-points-in-paint-per-game',
 'def_efficiency':'defensive-efficiency',
 'opp_efg_pct':'opponent-effective-field-goal-pct',
 'opp_two_pt_pct':'opponent-two-point-pct',
 'opp_three_pt_pct':'opponent-three-point-pct',
 'opp_two_pt_rate':'opponent-two-point-rate',
 'opp_three_pt_rate':'opponent-three-point-rate',
 'opp_off_reb_pct':'opponent-offensive-rebounding-pct',
 'opp_def_reb_pct':'opponent-defensive-rebounding-pct',
 'opp_assists_game':'opponent-assists-per-game',
 'opp_assists_fgm':'opponent-assists-per-fgm',
 'opp_turnovers_poss':'opponent-turnovers-per-possession',
 'opp_personal_fouls_game':'opponent-personal-fouls-per-game',
 'opp_fta_fga':'opponent-fta-per-fga',
 'possessions_game':'possessions-per-game',
 'opp_fastbreak_points':'opponent-fastbreak-points-per-game',
}
TEAM_MAP={'Golden State':'GS','Washington':'WAS','Minnesota':'MIN','Phoenix':'PHX','New York':'NY','Seattle':'SEA','Las Vegas':'LV','Connecticut':'CON','Atlanta':'ATL','Portland':'POR','Chicago':'CHI','Dallas':'DAL','Los Angeles':'LA','Toronto':'TOR','Indiana':'IND'}

def fetch(slug):
 req=Request(BASE+slug,headers={'User-Agent':'Mozilla/5.0 WNBA research collector'})
 with urlopen(req,timeout=25) as r:return r.read().decode('utf-8','ignore')

def clean(s):return re.sub(r'<[^>]+>',' ',s).replace('&nbsp;',' ').strip()
def value(s):
 s=clean(s).replace(',','').strip(); pct=s.endswith('%'); s=s.rstrip('%')
 try:return float(s)/100.0 if pct else float(s)
 except:return None

def parse_table(html):
 # Public TeamRankings tables expose rank/team plus season,last3,last1,home,away,prior.
 tables=re.findall(r'<table[^>]*>(.*?)</table>',html,re.S|re.I)
 for table in tables:
  rows=re.findall(r'<tr[^>]*>(.*?)</tr>',table,re.S|re.I)
  parsed=[]
  for row in rows:
   cells=re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>',row,re.S|re.I)
   vals=[clean(x) for x in cells]
   if len(vals)>=7 and vals[1] in TEAM_MAP:
    parsed.append({'team':vals[1],'team_code':TEAM_MAP[vals[1]],'season':value(cells[2]),'last3':value(cells[3]),'last1':value(cells[4]),'home':value(cells[5]),'away':value(cells[6]),'prior_season':value(cells[7]) if len(cells)>7 else None})
  if parsed:return parsed
 return []

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--date');args=ap.parse_args()
 target=args.date or datetime.now().date().isoformat(); now=datetime.now(timezone.utc).isoformat()
 teams={}; status={}
 for key,slug in METRICS.items():
  try: rows=parse_table(fetch(slug)); status[key]={'slug':slug,'rows':len(rows),'ok':bool(rows)}
  except Exception as e: rows=[];status[key]={'slug':slug,'rows':0,'ok':False,'error':str(e)[:180]}
  for r in rows:
   t=teams.setdefault(r['team_code'],{'team':r['team'],'team_code':r['team_code'],'metrics':{}})
   vals={k:r[k] for k in ('season','last3','last1','home','away','prior_season')};
   if vals['season'] is not None and vals['last3'] is not None: vals['recent_delta']=vals['last3']-vals['season']
   t['metrics'][key]=vals
 payload={'version':'V5','module':'TEAMRANKINGS_MATCHUP_INTELLIGENCE','status':'READY_SHADOW' if teams else 'SOURCE_UNAVAILABLE','production_ready':False,'research_only':True,'target_date':target,'generated_at_utc':now,'source':'TeamRankings public WNBA team-stat tables','source_policy':'Derived matchup features only; never canonical outcomes. Freeze before games and validate out-of-sample before promotion.','metric_status':status,'teams':teams}
 out=Path('data/warehouse/teamrankings');out.mkdir(parents=True,exist_ok=True)
 (out/f'wnba_team_matchup_{target}.json').write_text(json.dumps(payload,indent=2)+'\n')
 Path('data/dashboard/wnba_v5_team_matchup_intelligence.json').write_text(json.dumps(payload,indent=2)+'\n')
 print(json.dumps({'status':payload['status'],'teams':len(teams),'metrics_ok':sum(x['ok'] for x in status.values()),'metrics_total':len(status),'target_date':target},indent=2))
if __name__=='__main__':main()
