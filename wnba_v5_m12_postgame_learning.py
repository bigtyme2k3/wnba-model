"""V5-M12 post-game learning + forward validation.

Persists every M11 live V5 score in an append-safe ledger, grades it only when a
verified actual later appears, and freezes available pregame context at issuance.
Issued rows are never enriched after the fact: missing context remains missing so
future challenger research cannot accidentally reconstruct features post-outcome.
"""
from __future__ import annotations

import csv,json,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean

INFERENCE=Path('data/dashboard/wnba_v5_live_inference.json')
FEATURES=Path('data/dashboard/wnba_v5_historical_features.csv')
PLAYER_LOGS=Path('data/warehouse/wnba_player_game_logs.json')
LEDGER=Path('data/history/wnba_v5_forward_predictions.jsonl')
OUT_CSV=Path('data/dashboard/wnba_v5_forward_validation.csv')
METRICS=Path('data/dashboard/wnba_v5_forward_metrics.json')
STATE=Path('data/dashboard/wnba_v5_learning_state.json')
REPORT=Path('data/dashboard/wnba_v5_m12_report.json')
MATCHUP=Path('data/dashboard/wnba_v5_matchup_adjustments.csv')
LINEUP=Path('data/dashboard/wnba_v5_lineup_adjustments.csv')
TEAMRANKINGS=Path('data/dashboard/wnba_v5_team_matchup_features.json')
CLV_REPORT=Path('data/dashboard/wnba_v5_s3_m04_report.json')
EPS=1e-12

def f(v,default=None):
 try:
  x=float(v);return x if math.isfinite(x) else default
 except Exception:return default

def norm(v):return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def clamp(p):return max(EPS,min(1.0-EPS,float(p)))
def implied(o):
 o=f(o)
 if o is None or o==0:return None
 return abs(o)/(abs(o)+100.0) if o<0 else 100.0/(o+100.0)
def unit_profit(odds,win):
 o=f(odds)
 if o is None or o==0:return None
 if not win:return -1.0
 return o/100.0 if o>0 else 100.0/abs(o)
def read_json(path,default):
 try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
 except Exception:return default
def read_ledger():
 if not LEDGER.exists():return []
 out=[]
 for line in LEDGER.read_text(encoding='utf-8').splitlines():
  if line.strip():
   try:out.append(json.loads(line))
   except Exception:pass
 return out
def prediction_id(r):return '|'.join([str(r.get('ranking_key') or ''),str(r.get('prediction_generated_at_utc') or ''),str(r.get('v5_probability') or '')])
def csv_index(path):
 out={}
 if not path.exists():return out
 try:
  for r in csv.DictReader(path.open(encoding='utf-8-sig',newline='')):
   k=str(r.get('ranking_key') or '').strip()
   if k:out[k]=r
 except Exception:pass
 return out

def issuance_context():
 mi=csv_index(MATCHUP);li=csv_index(LINEUP)
 return mi,li

def frozen_context(key,mi,li):
 m=mi.get(key,{}) if key else {}; l=li.get(key,{}) if key else {}
 return {'ctx_matchup_defense_index':f(m.get('defense_index')),'ctx_matchup_multiplier':f(m.get('matchup_multiplier')),'ctx_matchup_last5_allowed':f(m.get('last5_allowed_avg')),'ctx_matchup_last10_allowed':f(m.get('last10_allowed_avg')),'ctx_rotation_games_prior':f(l.get('rotation_games_prior')),'ctx_minutes_l5':f(l.get('minutes_l5')),'ctx_minutes_l10':f(l.get('minutes_l10')),'ctx_minutes_prior_mean':f(l.get('minutes_prior_mean')),'ctx_starter_rate_l5':f(l.get('starter_rate_l5')),'ctx_starter_rate_l10':f(l.get('starter_rate_l10')),'ctx_lineup_confidence':f(l.get('lineup_confidence')),'ctx_rotation_multiplier':f(l.get('rotation_multiplier')),'ctx_projected_role':l.get('projected_role'),'ctx_injury_status':l.get('injury_status'),'ctx_lineup_confirmation':l.get('lineup_confirmation'),'ctx_snapshot_matchup_generated_at_utc':datetime.fromtimestamp(MATCHUP.stat().st_mtime,timezone.utc).isoformat() if MATCHUP.exists() else None,'ctx_snapshot_lineup_generated_at_utc':datetime.fromtimestamp(LINEUP.stat().st_mtime,timezone.utc).isoformat() if LINEUP.exists() else None}

def game_log_actual(record,stat):
 s=record.get('scoring') if isinstance(record.get('scoring'),dict) else {};b=record.get('boxscore') if isinstance(record.get('boxscore'),dict) else {};d=record.get('derived') if isinstance(record.get('derived'),dict) else {}
 key=str(stat or '').upper().replace('THREES','3PM').replace(' ','_')
 return f({'PTS':s.get('total_pts'),'3PM':s.get('three_pm'),'REB':b.get('reb'),'AST':b.get('ast'),'STL':b.get('stl'),'BLK':b.get('blk'),'PRA':d.get('pra'),'PR':d.get('pr'),'PA':d.get('pa'),'RA':d.get('ra')}.get(key))
def build_actual_index():
 buckets=defaultdict(list)
 if FEATURES.exists():
  for r in csv.DictReader(FEATURES.open(encoding='utf-8-sig',newline='')):
   date=str(r.get('game_date') or '')[:10];player=norm(r.get('player'));stat=str(r.get('stat') or '').upper();actual=f(r.get('target_actual'))
   if date and player and stat and actual is not None:buckets[(date,player,stat)].append(actual)
 logs=read_json(PLAYER_LOGS,{'records':[]})
 for r in logs.get('records',[]) if isinstance(logs,dict) else []:
  if not isinstance(r,dict):continue
  date=str(r.get('game_date') or '')[:10];player=norm(r.get('player'));minutes=f(r.get('minutes'))
  if not date or not player or (minutes is not None and minutes<=0):continue
  for stat in ('PTS','REB','AST','3PM','PRA','PR','PA','RA','STL','BLK'):
   actual=game_log_actual(r,stat)
   if actual is not None:buckets[(date,player,stat)].append(actual)
 idx={}
 for k,vals in buckets.items():
  uniq=sorted({round(x,8) for x in vals})
  if len(uniq)==1:idx[k]=uniq[0]
 return idx
def outcome(actual,line,side):
 if actual is None or line is None:return None
 if actual==line:return 'PUSH'
 if str(side or '').upper()=='OVER':return 'WIN' if actual>line else 'LOSS'
 if str(side or '').upper()=='UNDER':return 'WIN' if actual<line else 'LOSS'
 return None
def metric(rows,key,kind):
 q=[(f(r.get(key)),r.get('target_win')) for r in rows];q=[x for x in q if x[0] is not None and x[1] in (0,1)]
 if not q:return None
 if kind=='brier':return mean((p-y)**2 for p,y in q)
 if kind=='logloss':return mean(-(y*math.log(clamp(p))+(1-y)*math.log(clamp(1-p))) for p,y in q)
 if kind=='accuracy':return mean(int((p>=.5)==bool(y)) for p,y in q)
def ece(rows,key,bins=5):
 q=[(f(r.get(key)),r.get('target_win')) for r in rows];q=[x for x in q if x[0] is not None and x[1] in (0,1)]
 if not q:return None
 total=len(q);out=0.0
 for b in range(bins):
  lo=b/bins;hi=(b+1)/bins;z=[x for x in q if lo<=x[0]<(hi if b<bins-1 else hi+EPS)]
  if z:out+=len(z)/total*abs(mean(p for p,_ in z)-mean(y for _,y in z))
 return out
def r6(v):return None if v is None else round(v,6)

def main():
 now=datetime.now(timezone.utc).isoformat();payload=read_json(INFERENCE,{});inf_report=payload.get('report',{}) if isinstance(payload,dict) else {};current=payload.get('scored',[]) if isinstance(payload,dict) else []
 ledger=read_ledger();seen={prediction_id(r) for r in ledger};added=0;generated=inf_report.get('generated_at_utc');mi,li=issuance_context()
 for s in current:
  row={'ranking_key':s.get('ranking_key'),'prediction_generated_at_utc':generated,'date':str(s.get('date') or '')[:10],'player':s.get('player'),'game':s.get('game'),'stat':str(s.get('market') or '').upper(),'side':str(s.get('side') or '').upper(),'line':f(s.get('line')),'odds':f(s.get('odds')),'book':s.get('best_book'),'model':s.get('model') or 'KNN','v5_probability':f(s.get('v5_probability')),'knn_probability':f(s.get('knn_probability')),'market_probability':f(s.get('market_implied_probability')),'probability_edge':f(s.get('probability_edge')),'confidence_score':f(s.get('confidence_score')),'uncertainty_score':f(s.get('uncertainty_score')),'neighbor_count':s.get('neighbor_count'),'neighbor_hit_rate':f(s.get('neighbor_hit_rate')),'average_neighbor_distance':f(s.get('average_neighbor_distance')),'actual':None,'outcome':'PENDING','target_win':None,'graded_at_utc':None,'research_only':True}
  row.update(frozen_context(str(row.get('ranking_key') or ''),mi,li));pid=prediction_id(row);row['prediction_id']=pid
  if pid not in seen:ledger.append(row);seen.add(pid);added+=1
 actuals=build_actual_index();newly_graded=0
 for r in ledger:
  if r.get('outcome') not in (None,'','PENDING'):continue
  actual=actuals.get((str(r.get('date') or '')[:10],norm(r.get('player')),str(r.get('stat') or '').upper()));out=outcome(actual,f(r.get('line')),r.get('side'))
  if out:r['actual']=actual;r['outcome']=out;r['graded_at_utc']=now;r['target_win']=1 if out=='WIN' else (0 if out=='LOSS' else None);r['actual_source']='canonical_player_game_log_or_certified_feature_store';newly_graded+=1
 LEDGER.parent.mkdir(parents=True,exist_ok=True)
 with LEDGER.open('w',encoding='utf-8') as h:
  for r in sorted(ledger,key=lambda x:(x.get('date',''),x.get('ranking_key',''),x.get('prediction_generated_at_utc',''))):h.write(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n')
 resolved=[r for r in ledger if r.get('outcome') in {'WIN','LOSS','PUSH'}];binary=[r for r in resolved if r.get('target_win') in (0,1)];pending=[r for r in ledger if r.get('outcome')=='PENDING']
 bets=[];posedge=[]
 for r in binary:
  p=f(r.get('v5_probability'));mp=f(r.get('market_probability'));o=f(r.get('odds'))
  if p is not None and p>=.5 and o is not None:
   u=unit_profit(o,int(r['target_win']));bets.append(u) if u is not None else None
  if p is not None and mp is not None and p>mp and o is not None:
   u=unit_profit(o,int(r['target_win']));posedge.append(u) if u is not None else None
 metrics={'forward_predictions':len(ledger),'resolved_predictions':len(resolved),'binary_graded_predictions':len(binary),'pushes':sum(r.get('outcome')=='PUSH' for r in resolved),'pending_predictions':len(pending),'v5_brier':r6(metric(binary,'v5_probability','brier')),'market_brier':r6(metric(binary,'market_probability','brier')),'v5_log_loss':r6(metric(binary,'v5_probability','logloss')),'market_log_loss':r6(metric(binary,'market_probability','logloss')),'v5_ece_5bin':r6(ece(binary,'v5_probability')),'market_ece_5bin':r6(ece(binary,'market_probability')),'v5_accuracy':r6(metric(binary,'v5_probability','accuracy')),'market_accuracy':r6(metric(binary,'market_probability','accuracy')),'model_bets_at_0_5':len(bets),'model_profit_units_at_0_5':round(sum(bets),4) if bets else 0.0,'model_roi_at_0_5':r6(sum(bets)/len(bets)) if bets else None,'positive_edge_bets':len(posedge),'positive_edge_profit_units':round(sum(posedge),4) if posedge else 0.0,'positive_edge_roi':r6(sum(posedge)/len(posedge)) if posedge else None}
 context_fields=[k for k in (ledger[-1].keys() if ledger else []) if k.startswith('ctx_')];context_rows=sum(any(r.get(k) is not None for k in context_fields) for r in ledger)
 minimum_rows=300;minimum_clv=60.0
 clv_report=read_json(CLV_REPORT,{})
 explicit_clv_coverage=f(clv_report.get('explicit_clv_coverage_pct'),0.0) if isinstance(clv_report,dict) else 0.0
 promotion_ready=(len(binary)>=minimum_rows and explicit_clv_coverage>=minimum_clv and metrics['v5_brier'] is not None and metrics['market_brier'] is not None and metrics['v5_brier']<metrics['market_brier'])
 status='READY_FORWARD_LEARNING' if ledger else 'WAITING_FOR_M11_PREDICTIONS'
 if ledger and not binary:status='WAITING_FOR_CERTIFIED_OUTCOMES'
 state={'version':'V5','module':'V5-M12','status':status,'generated_at_utc':now,'research_champion':'KNN','new_predictions_appended':added,'newly_graded':newly_graded,'metrics':metrics,'context_snapshot':{'policy':'Context is copied only when a new prediction is issued; historical ledger rows are never backfilled.','fields':context_fields,'rows_with_frozen_context':context_rows,'matchup_source':str(MATCHUP),'lineup_source':str(LINEUP)},'promotion_gate':{'production_ready':promotion_ready,'minimum_forward_rows':minimum_rows,'current_forward_rows':len(binary),'minimum_explicit_clv_coverage_pct':minimum_clv,'explicit_clv_coverage_pct':explicit_clv_coverage,'explicit_clv_source':str(CLV_REPORT),'reason':'V4 remains production champion until >=300 graded forward predictions, >=60% explicit CLV coverage, and V5 beats market forward Brier.'},'learning_policy':'Append predictions and available context before outcomes; grade only from later verified actuals; never rewrite issued probabilities or backfill context.','actual_sources':['certified_v5_historical_feature_store','canonical_player_game_log_warehouse'],'next_module':'V5-M13 Production Readiness + Shadow Monitoring'}
 report=dict(state);report['pending_examples']=[{'date':r.get('date'),'player':r.get('player'),'stat':r.get('stat'),'side':r.get('side')} for r in pending[:10]]
 OUT_CSV.parent.mkdir(parents=True,exist_ok=True);fields=['prediction_id','ranking_key','prediction_generated_at_utc','date','player','game','stat','side','line','odds','book','model','v5_probability','market_probability','probability_edge','confidence_score','uncertainty_score']+context_fields+['actual','outcome','target_win','graded_at_utc']
 with OUT_CSV.open('w',encoding='utf-8',newline='') as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows([{k:r.get(k) for k in fields} for r in ledger])
 METRICS.write_text(json.dumps(metrics,indent=2,allow_nan=False)+'\n',encoding='utf-8');STATE.write_text(json.dumps(state,indent=2,allow_nan=False)+'\n',encoding='utf-8');REPORT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8');print(json.dumps(report,indent=2,allow_nan=False))
if __name__=='__main__':main()
