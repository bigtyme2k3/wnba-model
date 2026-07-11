"""Backtest Phase 5 decisions and produce calibration, feature weights, and ensemble recommendations."""
from __future__ import annotations
import argparse,csv,json,math,os
from collections import defaultdict
from datetime import date,datetime,timezone
from typing import Any

HISTORY='data/history/wnba_model_history.jsonl'
OUT='data/warehouse/wnba_phase5_backtest.json'
DASH='data/dashboard/wnba_phase5_backtest.json'
WEIGHTS='config/wnba_learned_weights.json'

def sf(v,d=0.0):
 try:
  x=float(v);return x if math.isfinite(x) else d
 except Exception:return d

def load_jsonl(path):
 rows=[]
 if os.path.exists(path):
  for line in open(path,encoding='utf-8'):
   try:
    row=json.loads(line)
    if isinstance(row,dict):rows.append(row)
   except Exception:pass
 return rows

def corr(xs,ys):
 if len(xs)<5:return 0.0
 mx=sum(xs)/len(xs);my=sum(ys)/len(ys)
 num=sum((x-mx)*(y-my) for x,y in zip(xs,ys));dx=math.sqrt(sum((x-mx)**2 for x in xs));dy=math.sqrt(sum((y-my)**2 for y in ys))
 return num/(dx*dy) if dx and dy else 0.0

def roi(rows):
 profit=0;risk=0
 for r in rows:
  o=str(r.get('outcome') or '')
  if o not in {'WIN','LOSS'}:continue
  risk+=1;odds=sf(r.get('american_odds'),-110)
  if o=='WIN':profit+=(100/abs(odds) if odds<0 else odds/100)
  else:profit-=1
 return {'n':risk,'units':round(profit,3),'roi':round(profit/risk,4) if risk else None,'win_rate':round(sum(r.get('outcome')=='WIN' for r in rows)/risk,4) if risk else None}

def threshold_tests(rows,field,thresholds,direction='gte'):
 out=[]
 for t in thresholds:
  subset=[r for r in rows if (sf(r.get(field),-999)>=t if direction=='gte' else sf(r.get(field),999)<=t)]
  out.append({'threshold':t,**roi(subset)})
 return out

def build(target):
 rows=[r for r in load_jsonl(HISTORY) if r.get('outcome') in {'WIN','LOSS','PUSH'}]
 binary=[r for r in rows if r.get('outcome') in {'WIN','LOSS'}]
 features=['simulation_probability','consensus_score','edge_pct','ev_pct','book_count','history_games','final_score']
 correlations=[]
 for f in features:
  pairs=[(sf(r.get(f),float('nan')),1 if r.get('outcome')=='WIN' else 0) for r in binary]
  pairs=[p for p in pairs if math.isfinite(p[0])]
  c=corr([p[0] for p in pairs],[p[1] for p in pairs]) if pairs else 0
  correlations.append({'feature':f,'samples':len(pairs),'correlation':round(c,4),'importance':round(abs(c),4)})
 correlations.sort(key=lambda x:x['importance'],reverse=True)
 positive=[x for x in correlations if x['correlation']>0]
 total=sum(x['importance'] for x in positive) or 1
 learned={x['feature']:round(x['importance']/total,4) for x in positive}
 if len(binary)<50:
  learned={'simulation_probability':0.30,'consensus_score':0.25,'edge_pct':0.15,'ev_pct':0.15,'book_count':0.05,'history_games':0.10}
 by_stat=[]
 groups=defaultdict(list)
 for r in rows:groups[str(r.get('stat') or 'UNKNOWN')].append(r)
 for stat,items in groups.items():by_stat.append({'stat':stat,**roi(items)})
 by_stat.sort(key=lambda x:(x['n'],x['roi'] if x['roi'] is not None else -999),reverse=True)
 report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'graded_rows':len(rows),'binary_rows':len(binary),'overall':roi(rows),'thresholds':{
  'probability':threshold_tests(binary,'simulation_probability',[.52,.54,.56,.58,.60,.62,.65]),
  'edge_pct':threshold_tests(binary,'edge_pct',[2,3,4,5,6,8,10]),
  'ev_pct':threshold_tests(binary,'ev_pct',[1,2,3,4,5,7.5,10]),
  'history_games':threshold_tests(binary,'history_games',[2,3,5,7,10]),
  'book_count':threshold_tests(binary,'book_count',[1,2,3]),
  'final_score':threshold_tests(binary,'final_score',[55,60,65,70,75,80,85,90])},
  'feature_importance':correlations,'learned_weights':learned,'performance_by_stat':by_stat,
  'recommendations':{'minimum_probability':.56,'minimum_edge_pct':5,'minimum_ev_pct':2,'maximum_ev_pct':20,'minimum_history_games':5,'minimum_books':2},
  'learning_status':'active' if len(binary)>=200 else 'calibrating' if len(binary)>=50 else 'collecting'}
 os.makedirs('data/warehouse',exist_ok=True);os.makedirs('data/dashboard',exist_ok=True);os.makedirs('config',exist_ok=True)
 for p in [OUT,DASH]:json.dump(report,open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
 json.dump({'generated_at_utc':report['generated_at_utc'],'samples':len(binary),'status':report['learning_status'],'weights':learned},open(WEIGHTS,'w',encoding='utf-8'),indent=2)
 print(json.dumps({'graded':len(rows),'status':report['learning_status'],'weights':learned},indent=2))
 return report

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));args=ap.parse_args();build(args.date)
if __name__=='__main__':main()
