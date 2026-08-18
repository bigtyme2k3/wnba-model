import csv,json,re
from pathlib import Path
SRC=Path('data/raw/scores.csv')
OUT=Path('data/warehouse/teamrankings/historical_matchup_manifest.json')
ALIASES={'Golden State Valkyries':'valkyries','Toronto Tempo':'tempo','Las Vegas Aces':'aces','New York Liberty':'liberty','Los Angeles Sparks':'sparks','Minnesota Lynx':'lynx','Connecticut Sun':'sun','Indiana Fever':'fever','Washington Mystics':'mystics','Atlanta Dream':'dream','Seattle Storm':'storm','Dallas Wings':'wings','Phoenix Mercury':'mercury','Chicago Sky':'sky','Portland Fire':'fire'}
def slug(team):
 return ALIASES.get(team,re.sub(r'[^a-z]+','-',team.lower()).strip('-').split('-')[-1])
rows=[]
with SRC.open(newline='',encoding='utf-8') as f:
 for r in csv.DictReader(f):
  if str(r.get('is_final','')).lower()!='true': continue
  date=r['game_date']; away=r['away_team']; home=r['home_team']
  pair=f'{slug(away)}-{slug(home)}-{date}'
  rows.append({'date':date,'game':f'{away} @ {home}','game_id':r.get('game_id'),'away_team':away,'home_team':home,'teamrankings_url':f'https://www.teamrankings.com/wnba/matchup/{pair}/splits'})
rows.sort(key=lambda x:(x['date'],x.get('game_id') or ''),reverse=True)
payload={'version':'V5','source':'data/raw/scores.csv','research_only':True,'lookahead_safe':True,'matchups':rows}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
print({'completed_games':len(rows),'newest':rows[0]['date'] if rows else None,'oldest':rows[-1]['date'] if rows else None})
