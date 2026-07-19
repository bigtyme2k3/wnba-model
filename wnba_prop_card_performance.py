"""Archive, grade, and analyze calibrated WNBA prop bet cards."""
from __future__ import annotations
import argparse, json, math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

CARDS=Path('data/dashboard/wnba_prop_bet_cards.json')
LOGS=Path('data/warehouse/wnba_player_game_logs.json')
LEDGER=Path('data/history/wnba_prop_card_ledger.jsonl')
OUTS=[Path('data/dashboard/wnba_prop_card_performance.json'),Path('data/warehouse/wnba_prop_card_performance.json')]

def load(path:Path,default:Any):
 try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
 except Exception:return default

def num(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except Exception:return None

def norm(v):return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def key(r):return '|'.join([str(r.get('target_date') or r.get('date') or ''),norm(r.get('player')),str(r.get('stat') or '').upper(),str(r.get('side') or '').upper(),str(r.get('line'))])
def read_ledger():
 if not LEDGER.exists():return []
 out=[]
 for line in LEDGER.read_text(encoding='utf-8').splitlines():
  try:out.append(json.loads(line))
  except Exception:pass
 return out

def write_ledger(rows):
 LEDGER.parent.mkdir(parents=True,exist_ok=True)
 LEDGER.write_text('\n'.join(json.dumps(r,allow_nan=False,separators=(',',':')) for r in rows)+'\n',encoding='utf-8')

def archive(target):
 payload=load(CARDS,{})
 existing=read_ledger();seen={key(r) for r in existing}
 added=0
 for card in payload.get('ranked_cards',[]) or []:
  row=dict(card);row['target_date']=target;row['archived_at_utc']=datetime.now(timezone.utc).isoformat();row['status']='OPEN';row['result']=None;row['actual']=None
  k=key(row)
  if k not in seen:existing.append(row);seen.add(k);added+=1
 write_ledger(existing);print({'archived':added,'ledger_rows':len(existing)});return added

def stat_value(row,stat):
 scoring=row.get('scoring') or {};box=row.get('boxscore') or {}
 pts=num(scoring.get('total_pts'));reb=num(box.get('reb'));ast=num(box.get('ast'));th=num(scoring.get('three_pm'));stl=num(box.get('stl'));blk=num(box.get('blk'));tov=num(box.get('tov'))
 vals={'PTS':pts,'REB':reb,'AST':ast,'3PM':th,'STL':stl,'BLK':blk,'TOV':tov,'PRA':None if None in (pts,reb,ast) else pts+reb+ast,'PR':None if None in (pts,reb) else pts+reb,'PA':None if None in (pts,ast) else pts+ast,'RA':None if None in (reb,ast) else reb+ast}
 return vals.get(stat)

def actual_index():
 p=load(LOGS,{'records':[]});idx={}
 for r in p.get('records',[]) or []:
  d=str(r.get('game_date') or r.get('date') or '')[:10];name=norm(r.get('player'))
  if d and name:idx[(d,name)]=r
 return idx

def grade(target=None):
 rows=read_ledger();idx=actual_index();graded=0
 for r in rows:
  if r.get('status')!='OPEN':continue
  d=str(r.get('target_date') or '')[:10]
  if target and d!=target:continue
  actual_row=idx.get((d,norm(r.get('player'))))
  if not actual_row:continue
  actual=stat_value(actual_row,str(r.get('stat') or '').upper());line=num(r.get('line'))
  if actual is None or line is None:continue
  side=str(r.get('side') or '').upper();result='PUSH' if actual==line else 'WIN' if (actual>line if side=='OVER' else actual<line) else 'LOSS'
  odds=num(r.get('odds'));profit=0.0
  if result=='WIN' and odds is not None:profit=100/abs(odds) if odds<0 else odds/100
  elif result=='LOSS':profit=-1.0
  r.update({'status':'GRADED','result':result,'actual':actual,'profit_units':round(profit,4),'graded_at_utc':datetime.now(timezone.utc).isoformat()});graded+=1
 write_ledger(rows);print({'newly_graded':graded,'ledger_rows':len(rows)});return graded

def bucket(rows,field):
 groups=defaultdict(list)
 for r in rows:groups[str(r.get(field) if r.get(field) not in (None,'') else 'UNKNOWN')].append(r)
 out=[]
 for name,rs in groups.items():
  decisions=[x for x in rs if x.get('result') in ('WIN','LOSS')];wins=sum(x.get('result')=='WIN' for x in decisions);profit=sum(num(x.get('profit_units')) or 0 for x in rs)
  out.append({'group':name,'n':len(decisions),'wins':wins,'losses':len(decisions)-wins,'win_rate':round(wins/len(decisions),4) if decisions else None,'units':round(profit,3),'roi':round(profit/len(decisions),4) if decisions else None})
 return sorted(out,key=lambda x:(-(x['roi'] if x['roi'] is not None else -999),-x['n']))

def analyze(target=None):
 rows=read_ledger();graded=[r for r in rows if r.get('status')=='GRADED'];dec=[r for r in graded if r.get('result') in ('WIN','LOSS')];wins=sum(r.get('result')=='WIN' for r in dec);profit=sum(num(r.get('profit_units')) or 0 for r in graded)
 report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target or str(date.today()),'summary':{'archived':len(rows),'open':sum(r.get('status')=='OPEN' for r in rows),'graded':len(graded),'wins':wins,'losses':len(dec)-wins,'win_rate':round(wins/len(dec),4) if dec else None,'units':round(profit,3),'roi':round(profit/len(dec),4) if dec else None},'by_grade':bucket(graded,'letter_grade'),'by_stat':bucket(graded,'stat'),'by_action':bucket(graded,'action'),'by_sportsbook':bucket(graded,'sportsbook'),'by_ev_band':bucket([{**r,'ev_band':('10%+' if (num(r.get('expected_value')) or 0)>=.10 else '5-10%' if (num(r.get('expected_value')) or 0)>=.05 else '0-5%')} for r in graded],'ev_band'),'recent':list(reversed(graded[-30:]))}
 for p in OUTS:p.parent.mkdir(parents=True,exist_ok=True);json.dump(report,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
 print('PROP CARD PERFORMANCE',report['summary']);return report

def main():
 ap=argparse.ArgumentParser();ap.add_argument('command',choices=['archive','grade','analyze']);ap.add_argument('--date',default='');a=ap.parse_args();target=a.date or str(date.today())
 {'archive':archive,'grade':grade,'analyze':analyze}[a.command](target)
if __name__=='__main__':main()
