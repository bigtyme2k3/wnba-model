"""Historical TeamRankings matchup reconstruction for V5 research.

Builds point-in-time team matchup snapshots for completed historical games by
requesting date-specific TeamRankings matchup/stat pages. Historical values are
never substituted with today's snapshot. Missing point-in-time evidence remains
missing to prevent look-ahead leakage.
"""
from __future__ import annotations
import argparse,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen

OUT=Path('data/warehouse/teamrankings/historical')
DASH=Path('data/dashboard/wnba_v5_teamrankings_historical_reconstruction.json')
UA='Mozilla/5.0 (compatible; WNBA-V5-Research/1.0)'

# TeamRankings matchup URLs are discovered from historical schedule/game evidence.
def get(url):
 req=Request(url,headers={'User-Agent':UA})
 with urlopen(req,timeout=25) as r:return r.read().decode('utf-8','replace')

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--manifest',default='data/warehouse/teamrankings/historical_matchup_manifest.json'); ap.add_argument('--limit',type=int,default=30); a=ap.parse_args()
 mp=Path(a.manifest)
 items=json.loads(mp.read_text()) if mp.exists() else []
 if isinstance(items,dict): items=items.get('matchups',[])
 rows=[]
 for x in items[:a.limit]:
  url=x.get('teamrankings_url'); date=x.get('date'); game=x.get('game')
  if not url or not date: continue
  rec={'date':date,'game':game,'teamrankings_url':url,'status':'MISSING','captured_at_utc':datetime.now(timezone.utc).isoformat()}
  try:
   html=get(url)
   # Preserve immutable raw evidence; parsing/feature extraction is a separate audited stage.
   d=OUT/date; d.mkdir(parents=True,exist_ok=True)
   key=re.sub(r'[^a-z0-9]+','-',str(game or url).lower()).strip('-')[:100]
   raw=d/f'{key}.html'; raw.write_text(html,encoding='utf-8')
   rec.update(status='CAPTURED',raw_path=str(raw),bytes=len(html))
  except Exception as e: rec['error']=f'{type(e).__name__}: {e}'[:240]
  rows.append(rec); time.sleep(.35)
 payload={'version':'V5','module':'TEAMRANKINGS_HISTORICAL_RECONSTRUCTOR','status':'RESEARCH_ONLY','production_ready':False,'research_only':True,'lookahead_policy':'Only date-specific historical TeamRankings evidence may be used. Current snapshots may never backfill prior dates.','generated_at_utc':datetime.now(timezone.utc).isoformat(),'requested':len(items[:a.limit]),'captured':sum(r['status']=='CAPTURED' for r in rows),'missing':sum(r['status']!='CAPTURED' for r in rows),'rows':rows}
 DASH.parent.mkdir(parents=True,exist_ok=True); DASH.write_text(json.dumps(payload,indent=2)+'\n')
 print(json.dumps({k:payload[k] for k in ('status','requested','captured','missing')},indent=2))
if __name__=='__main__':main()
