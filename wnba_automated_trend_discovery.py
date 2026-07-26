"""Sprint 16 Commit 1: automated trend discovery from market intelligence artifacts.

This engine mines repeatable market-timing patterns. Until enough graded outcomes exist,
patterns are validated on CLV quality rather than claimed betting profitability.
"""
from __future__ import annotations
import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

CLV=Path('data/market/clv_results.json')
MOVES=Path('data/market/line_movements.json')
SIGNALS=Path('data/market/movement_classifications.json')
OUT=Path('data/trends/automated_trends.json')
CAND=Path('data/trends/trend_candidates.json')
DASH=Path('data/dashboard/wnba_trend_discovery_summary.json')
MIN_SAMPLE=20

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def load(path,key):
    if not path.exists(): return []
    x=json.loads(path.read_text(encoding='utf-8')).get(key,[])
    return x if isinstance(x,list) else []
def bucket_minutes(v):
    v=float(v or 0)
    if v>=1440:return '24H_PLUS'
    if v>=720:return '12_TO_24H'
    if v>=360:return '6_TO_12H'
    if v>=180:return '3_TO_6H'
    if v>=60:return '1_TO_3H'
    return 'FINAL_HOUR'
def grade(sample,pos,avg):
    if sample>=75 and pos>=.58 and avg>0:return 'A'
    if sample>=40 and pos>=.55 and avg>=0:return 'B'
    if sample>=MIN_SAMPLE and pos>=.52:return 'C'
    return 'RESEARCH'
def score(sample,pos,avg):
    reliability=min(30,math.log10(max(sample,1))*12)
    edge=max(0,(pos-.5)*100)*1.2
    quality=min(25,max(0,avg*500))
    return round(min(100,reliability+edge+quality),2)
def run():
    clv=[x for x in load(CLV,'records') if not x.get('is_closing_observation')]
    moves={x['market_id']:x for x in load(MOVES,'movements')}
    sigs={x['market_id']:x for x in load(SIGNALS,'classifications')}
    groups=defaultdict(list)
    for r in clv:
        m=moves.get(r['market_id'],{}); s=sigs.get(r['market_id'],{})
        features={
          'bookmaker':r.get('bookmaker','UNKNOWN'),'market':r.get('market','UNKNOWN'),
          'selection':r.get('selection','UNKNOWN'),'window':bucket_minutes(r.get('minutes_to_tip')),
          'movement_direction':m.get('direction','UNKNOWN'),
          'volatility_band':'HIGH' if float(m.get('volatility_score') or 0)>=70 else ('MEDIUM' if float(m.get('volatility_score') or 0)>=35 else 'LOW'),
          'signal':s.get('classification','NORMAL')}
        keys=[('bookmaker',),('market',),('window',),('bookmaker','market'),('market','window'),('bookmaker','market','window'),('market','signal'),('market','movement_direction'),('market','volatility_band')]
        for dims in keys: groups[tuple((d,features[d]) for d in dims)].append(r)
    trends=[]; candidates=[]
    for key,rows in groups.items():
        sample=len(rows); pos=sum(x.get('clv_class')=='POSITIVE' for x in rows); neg=sum(x.get('clv_class')=='NEGATIVE' for x in rows)
        vals=[float(x['implied_probability_clv']) for x in rows if x.get('implied_probability_clv') is not None]
        avg=mean(vals) if vals else 0.0; rate=pos/sample if sample else 0
        rec={'dimensions':dict(key),'sample_size':sample,'positive_clv':pos,'negative_clv':neg,'positive_clv_rate':round(rate,6),'average_implied_probability_clv':round(avg,6),'trend_score':score(sample,rate,avg),'grade':grade(sample,rate,avg),'validation_basis':'CLV_ONLY'}
        (trends if sample>=MIN_SAMPLE and rate>=.52 else candidates).append(rec)
    trends.sort(key=lambda x:(-x['trend_score'],-x['sample_size']))
    candidates.sort(key=lambda x:(-x['sample_size'],-x['positive_clv_rate']))
    generated=now(); OUT.parent.mkdir(parents=True,exist_ok=True); DASH.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({'generated_at_utc':generated,'methodology':'Pattern mining on historical CLV; not proof of betting profitability.','trends':trends},indent=2),encoding='utf-8')
    CAND.write_text(json.dumps({'generated_at_utc':generated,'candidates':candidates[:500]},indent=2),encoding='utf-8')
    summary={'generated_at_utc':generated,'status':'READY' if clv else 'STANDBY','observations_analyzed':len(clv),'groups_tested':len(groups),'qualified_trends':len(trends),'research_candidates':len(candidates),'grade_counts':{g:sum(x['grade']==g for x in trends) for g in ['A','B','C','RESEARCH']},'top_trends':trends[:25],'warning':'These are CLV timing patterns, not guaranteed profitable betting systems.'}
    DASH.write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2)); return summary
if __name__=='__main__': run()
