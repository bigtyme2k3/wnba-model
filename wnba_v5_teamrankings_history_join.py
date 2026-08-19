"""Leakage-safe research join: archived V5 predictions/outcomes + audited TeamRankings evidence.

Join path:
1) audited TeamRankings PARSED rows identify canonical game_id/date
2) canonical scores map date + normalized matchup text to game_id
3) archived model history rows resolve to the same game_id/date
4) only graded rows (actual + WIN/LOSS/PUSH/VOID) enter challenger-ready subset

No production prediction files are modified.
"""
from __future__ import annotations
import csv,json,re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

TR=Path('data/dashboard/wnba_v5_teamrankings_historical_features.json')
HIST=Path('data/history/wnba_model_history.jsonl')
SCORES=Path('data/raw/scores.csv')
OUT=Path('data/dashboard/wnba_v5_teamrankings_history_join.json')
WARE=Path('data/warehouse/teamrankings/joined')


def norm(s): return re.sub(r'[^a-z0-9]+',' ',str(s or '').lower()).strip()
def matchup_key(date,game):
 parts=[norm(x) for x in re.split(r'\s+@\s+',str(game or ''),maxsplit=1)]
 return (str(date or '')[:10],tuple(parts)) if len(parts)==2 else (str(date or '')[:10],(norm(game),))
def load_history():
 out=[]
 if not HIST.exists(): return out
 for line in HIST.read_text(encoding='utf-8').splitlines():
  try:
   r=json.loads(line)
   if isinstance(r,dict): out.append(r)
  except Exception: pass
 return out

def main():
 tr=json.loads(TR.read_text(encoding='utf-8'))
 assert tr.get('lookahead_safe') is True
 parsed={str(r.get('game_id')):r for r in tr.get('rows',[]) if r.get('status')=='PARSED' and r.get('game_id')}
 score_by_key={}; score_by_id={}
 with SCORES.open(newline='',encoding='utf-8') as f:
  for r in csv.DictReader(f):
   gid=str(r.get('game_id') or '')
   away=r.get('away_team'); home=r.get('home_team'); date=r.get('game_date')
   key=matchup_key(date,f'{away} @ {home}')
   score_by_key[key]=gid; score_by_id[gid]=r
 history=load_history(); joined=[]; unmatched=[]
 for h in history:
  date=str(h.get('date') or '')[:10]; game=h.get('game')
  gid=score_by_key.get(matchup_key(date,game))
  if not gid:
   unmatched.append({'reason':'NO_CANONICAL_GAME_ID','history_key':h.get('history_key'),'date':date,'game':game}); continue
  trrow=parsed.get(gid)
  if not trrow: continue
  item={
   'game_id':gid,'date':date,'game':game,'player':h.get('player'),'team':h.get('team'),'stat':h.get('stat'),
   'line':h.get('line'),'projection':h.get('pred'),'signal':h.get('signal') or h.get('recommendation'),
   'confidence':h.get('confidence'),'edge':h.get('edge'),'sportsbook':h.get('sportsbook'),'american_odds':h.get('american_odds'),
   'model_version':h.get('model_version'),'result_scope':h.get('result_scope'),'actual':h.get('actual'),'outcome':h.get('outcome'),
   'captured_at_utc':h.get('captured_at_utc'),'graded_at_utc':h.get('graded_at_utc'),
   'teamrankings_page_title':trrow.get('page_title'),'teamrankings_raw_path':trrow.get('raw_path'),
   'teamrankings_metric_groups_found':trrow.get('metric_groups_found'),'teamrankings_metrics_raw':trrow.get('metrics'),
  }
  item['graded']=item['outcome'] in {'WIN','LOSS','PUSH','VOID'} and item['actual'] is not None
  joined.append(item)
 graded=[r for r in joined if r['graded']]
 payload={
  'version':'V5','module':'TEAMRANKINGS_HISTORY_JOIN','status':'READY_RESEARCH_JOIN','research_only':True,'production_ready':False,'lookahead_safe':True,
  'generated_at_utc':datetime.now(timezone.utc).isoformat(),
  'join_policy':'Audited TeamRankings PARSED game_id + canonical scores mapping + archived history date/matchup. No fuzzy player join and no current snapshot fallback.',
  'teamrankings_valid_games':len(parsed),'history_rows_total':len(history),'joined_history_rows':len(joined),'graded_join_rows':len(graded),
  'joined_unique_games':len({r['game_id'] for r in joined}),'graded_unique_games':len({r['game_id'] for r in graded}),
  'graded_by_stat':dict(sorted(Counter(str(r.get('stat') or 'UNKNOWN') for r in graded).items())),
  'graded_by_outcome':dict(sorted(Counter(str(r.get('outcome') or 'UNKNOWN') for r in graded).items())),
  'unmatched_history_rows_without_canonical_game':len(unmatched),
  'challenger_ready':len(graded)>=50 and len({r['game_id'] for r in graded})>=10,
  'feature_semantics_policy':'TeamRankings numeric arrays remain raw/unaudited; this join proves alignment only. Challenger must not assign season/last3/venue semantics until audited.',
  'graded_rows':graded,'all_joined_rows':joined,'unmatched_sample':unmatched[:50],
 }
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
 WARE.mkdir(parents=True,exist_ok=True); (WARE/'wnba_v5_teamrankings_history_join.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
 print(json.dumps({k:payload[k] for k in ('teamrankings_valid_games','history_rows_total','joined_history_rows','graded_join_rows','joined_unique_games','graded_unique_games','challenger_ready')},indent=2))
if __name__=='__main__': main()
