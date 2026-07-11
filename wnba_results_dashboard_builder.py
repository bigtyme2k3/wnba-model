"""Attach readable recent graded wagers and daily summaries to the Phase 5 dashboard payload."""
from __future__ import annotations
import json,os
from collections import defaultdict
from datetime import datetime,timezone

HISTORY='data/history/wnba_model_history.jsonl'
TARGETS=['data/warehouse/wnba_phase5_learning.json','data/dashboard/wnba_phase5_learning.json']

def rows():
 out=[]
 if os.path.exists(HISTORY):
  for line in open(HISTORY,encoding='utf-8'):
   try:
    r=json.loads(line)
    if r.get('outcome') in {'WIN','LOSS','PUSH'}:out.append(r)
   except Exception:pass
 return out

def main():
 graded=rows();graded.sort(key=lambda r:(str(r.get('date') or ''),str(r.get('graded_at_utc') or '')),reverse=True)
 daily=defaultdict(lambda:{'wins':0,'losses':0,'pushes':0,'units':0.0})
 for r in graded:
  d=str(r.get('date') or '')[:10];o=r.get('outcome');odds=float(r.get('american_odds') or -110)
  if o=='WIN':daily[d]['wins']+=1;daily[d]['units']+=(100/abs(odds) if odds<0 else odds/100)
  elif o=='LOSS':daily[d]['losses']+=1;daily[d]['units']-=1
  elif o=='PUSH':daily[d]['pushes']+=1
 for d,x in daily.items():
  risk=x['wins']+x['losses'];x['date']=d;x['units']=round(x['units'],3);x['roi']=round(x['units']/risk,4) if risk else None
 summary=sorted(daily.values(),key=lambda x:x['date'],reverse=True)
 for path in TARGETS:
  try:data=json.load(open(path,encoding='utf-8'))
  except Exception:data={}
  data['recent_graded']=graded[:100];data['daily_results']=summary[:60];data['results_updated_at_utc']=datetime.now(timezone.utc).isoformat()
  os.makedirs(os.path.dirname(path),exist_ok=True);json.dump(data,open(path,'w',encoding='utf-8'),indent=2,allow_nan=False)
 print('Results dashboard rows:',len(graded))
if __name__=='__main__':main()
