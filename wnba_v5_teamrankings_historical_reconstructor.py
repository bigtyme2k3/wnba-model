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

def get(url):
 req=Request(url,headers={'User-Agent':UA})
 with urlopen(req,timeout=25) as r:return r.read().decode('utf-8','replace')

def key_for(game,url):
 return re.sub(r'[^a-z0-9]+','-',str(game or url).lower()).strip('-')[:100]

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--manifest',default='data/warehouse/teamrankings/historical_matchup_manifest.json')
 ap.add_argument('--limit',type=int,default=200)
 ap.add_argument('--delay',type=float,default=.35)
 a=ap.parse_args()
 mp=Path(a.manifest)
 items=json.loads(mp.read_text()) if mp.exists() else []
 if isinstance(items,dict): items=items.get('matchups',[])
 rows=[]; attempted=0; newly_captured=0; reused=0
 for x in items:
  if attempted>=a.limit: break
  url=x.get('teamrankings_url'); date=x.get('date'); game=x.get('game')
  if not url or not date: continue
  d=OUT/date; raw=d/f'{key_for(game,url)}.html'
  rec={'date':date,'game':game,'game_id':x.get('game_id'),'teamrankings_url':url,'status':'MISSING','captured_at_utc':datetime.now(timezone.utc).isoformat()}
  if raw.exists() and raw.stat().st_size>1000:
   rec.update(status='CAPTURED_REUSED',raw_path=str(raw),bytes=raw.stat().st_size)
   rows.append(rec); reused+=1
   continue
  attempted+=1
  try:
   html=get(url)
   d.mkdir(parents=True,exist_ok=True); raw.write_text(html,encoding='utf-8')
   rec.update(status='CAPTURED_NEW',raw_path=str(raw),bytes=len(html)); newly_captured+=1
  except Exception as e:
   rec['error']=f'{type(e).__name__}: {e}'[:240]
  rows.append(rec); time.sleep(a.delay)
 # include all already-frozen evidence in coverage count, not just this batch
 frozen=list(OUT.glob('*/*.html')) if OUT.exists() else []
 captured_rows=sum(r['status'].startswith('CAPTURED') for r in rows)
 payload={'version':'V5','module':'TEAMRANKINGS_HISTORICAL_RECONSTRUCTOR','status':'RESEARCH_ONLY','production_ready':False,'research_only':True,'lookahead_policy':'Only date-specific historical TeamRankings evidence may be used. Current snapshots may never backfill prior dates.','generated_at_utc':datetime.now(timezone.utc).isoformat(),'manifest_games':len(items),'network_attempts_this_run':attempted,'newly_captured_this_run':newly_captured,'reused_this_run':reused,'frozen_html_files_total':len(frozen),'rows_reported':len(rows),'captured_rows_reported':captured_rows,'missing_rows_reported':sum(not r['status'].startswith('CAPTURED') for r in rows),'rows':rows}
 DASH.parent.mkdir(parents=True,exist_ok=True); DASH.write_text(json.dumps(payload,indent=2)+'\n')
 print(json.dumps({k:payload[k] for k in ('status','manifest_games','network_attempts_this_run','newly_captured_this_run','reused_this_run','frozen_html_files_total')},indent=2))
if __name__=='__main__':main()
