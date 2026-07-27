"""Sprint 17 Commit 2: probability-space closing line predictor with walk-forward validation."""
from __future__ import annotations
import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

TIMELINE=Path('data/market/market_timeline.json')
MOVES=Path('data/market/line_movements.json')
SIGNALS=Path('data/market/movement_classifications.json')
OUT=Path('data/forecast/closing_line_predictions.json')
PERF=Path('data/forecast/closing_line_predictor_performance.json')
DASH=Path('data/dashboard/wnba_closing_line_predictor_summary.json')
MIN_SAMPLE=12

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def parse(v): return datetime.fromisoformat(str(v).replace('Z','+00:00'))
def load(path,key):
    if not path.exists(): return []
    x=json.loads(path.read_text(encoding='utf-8')).get(key,[])
    return x if isinstance(x,list) else []
def num(v):
    try:return float(v)
    except (TypeError,ValueError):return None
def implied(price):
    p=num(price)
    if p is None or p==0:return None
    return (-p)/((-p)+100) if p<0 else 100/(p+100)
def american(prob):
    if prob is None:return None
    p=min(.99,max(.01,float(prob)))
    return int(round(-100*p/(1-p))) if p>=.5 else int(round(100*(1-p)/p))
def delta(a,b):
    a=num(a); b=num(b)
    return None if a is None or b is None else b-a
def window(m):
    m=float(m or 0)
    if m>=1440:return '24H_PLUS'
    if m>=720:return '12_TO_24H'
    if m>=360:return '6_TO_12H'
    if m>=180:return '3_TO_6H'
    if m>=60:return '1_TO_3H'
    return 'FINAL_HOUR'
def band(v):
    v=float(v or 0); return 'HIGH' if v>=70 else ('MEDIUM' if v>=35 else 'LOW')
def direction(a,b):
    d=delta(a,b)
    if d is None or abs(d)<1e-9:return 'NEUTRAL'
    if d>0:return 'STRONG_UP' if abs(d)>=2 else 'UP'
    return 'STRONG_DOWN' if abs(d)>=2 else 'DOWN'
def key(t,row,mins,m,s):
    return (str(t.get('bookmaker')),str(t.get('market')),str(t.get('selection')),window(mins),direction((t.get('observations') or [{}])[0].get('point'),row.get('point')),band(m.get('volatility_score')),str(s.get('classification','NORMAL')))
def pct(vals,q):
    if not vals:return None
    z=sorted(vals); i=(len(z)-1)*q; lo=int(math.floor(i)); hi=int(math.ceil(i))
    return z[lo] if lo==hi else z[lo]+(z[hi]-z[lo])*(i-lo)
def build_model(rows):
    point=[x['point_move'] for x in rows if x['point_move'] is not None]
    prob=[x['prob_move'] for x in rows if x['prob_move'] is not None]
    return {'sample_size':len(rows),'point_mean':mean(point) if point else None,'point_lo':pct(point,.1),'point_hi':pct(point,.9),'prob_mean':mean(prob) if prob else None,'prob_lo':pct(prob,.1),'prob_hi':pct(prob,.9)}
def run():
    timelines=load(TIMELINE,'markets'); moves={x['market_id']:x for x in load(MOVES,'movements')}; sigs={x['market_id']:x for x in load(SIGNALS,'classifications')}
    examples=[]
    for t in timelines:
        obs=t.get('observations') or []
        if len(obs)<2:continue
        close=obs[-1]; cp=num(close.get('point')); cprob=implied(close.get('american_price')); m=moves.get(t['market_id'],{}); s=sigs.get(t['market_id'],{})
        for row in obs[:-1]:
            mins=(parse(t['commence_time_utc'])-parse(row['snapshot_time_utc'])).total_seconds()/60
            examples.append({'key':key(t,row,mins,m,s),'market_id':t['market_id'],'event_id':t['event_id'],'time':row['snapshot_time_utc'],'current_point':num(row.get('point')),'current_prob':implied(row.get('american_price')),'close_point':cp,'close_prob':cprob,'point_move':delta(row.get('point'),cp),'prob_move':delta(implied(row.get('american_price')),cprob)})
    examples.sort(key=lambda x:(x['time'],x['market_id']))
    history=defaultdict(list); back=[]
    for x in examples:
        prior=history[x['key']]
        if len(prior)>=MIN_SAMPLE:
            model=build_model(prior)
            pp=None if x['current_point'] is None or model['point_mean'] is None else x['current_point']+model['point_mean']
            pprob=None if x['current_prob'] is None or model['prob_mean'] is None else x['current_prob']+model['prob_mean']
            err=None if pp is None or x['close_point'] is None else abs(pp-x['close_point'])
            dir_ok=None
            if x['point_move'] is not None and model['point_mean'] is not None: dir_ok=(x['point_move']==0 and model['point_mean']==0) or (x['point_move']*model['point_mean']>0)
            back.append({'market_id':x['market_id'],'event_id':x['event_id'],'predicted_point':None if pp is None else round(pp,6),'actual_point':x['close_point'],'point_error':None if err is None else round(err,6),'predicted_price':american(pprob),'actual_price':american(x['close_prob']),'direction_correct':dir_ok,'sample_size':model['sample_size']})
        prior.append(x)
    grouped=defaultdict(list)
    for x in examples:grouped[x['key']].append(x)
    models={k:build_model(v) for k,v in grouped.items() if len(v)>=MIN_SAMPLE}
    forecasts=[]
    for t in timelines:
        obs=t.get('observations') or []
        if not obs:continue
        row=obs[-1]; m=moves.get(t['market_id'],{}); s=sigs.get(t['market_id'],{}); snapshot=row.get('snapshot_time_utc'); mins=(parse(t['commence_time_utc'])-parse(snapshot)).total_seconds()/60; k=key(t,row,mins,m,s); model=models.get(k); cp=num(row.get('point')); cprob=implied(row.get('american_price'))
        rec={'market_id':t['market_id'],'event_id':t['event_id'],'commence_time_utc':t['commence_time_utc'],'home_team':t['home_team'],'away_team':t['away_team'],'bookmaker':t['bookmaker'],'market':t['market'],'participant':t.get('participant'),'selection':t.get('selection'),'snapshot_time_utc':snapshot,'current_time_utc':snapshot,'market_last_update_utc':row.get('market_last_update_utc'),'bookmaker_last_update_utc':row.get('bookmaker_last_update_utc'),'minutes_to_tip':round(mins,2),'current_point':cp,'current_price':row.get('american_price'),'forecast_status':'MODEL_READY' if model else 'INSUFFICIENT_HISTORY','sample_size':0 if not model else model['sample_size']}
        if model:
            prob=None if cprob is None or model['prob_mean'] is None else cprob+model['prob_mean']
            rec.update({'projected_closing_point':None if cp is None or model['point_mean'] is None else round(cp+model['point_mean'],6),'projected_point_interval':[None if cp is None or model['point_lo'] is None else round(cp+model['point_lo'],6),None if cp is None or model['point_hi'] is None else round(cp+model['point_hi'],6)],'projected_closing_price':american(prob),'projected_price_interval':[american(None if cprob is None or model['prob_lo'] is None else cprob+model['prob_lo']),american(None if cprob is None or model['prob_hi'] is None else cprob+model['prob_hi'])]})
        forecasts.append(rec)
    errs=[x['point_error'] for x in back if x['point_error'] is not None]; dirs=[x['direction_correct'] for x in back if x['direction_correct'] is not None]
    performance={'generated_at_utc':now(),'walk_forward_predictions':len(back),'point_mae':round(mean(errs),6) if errs else None,'within_half_point_rate':round(sum(e<=.5 for e in errs)/len(errs),6) if errs else None,'within_one_point_rate':round(sum(e<=1 for e in errs)/len(errs),6) if errs else None,'directional_accuracy':round(sum(dirs)/len(dirs),6) if dirs else None,'records':back[:5000]}
    generated=now(); OUT.parent.mkdir(parents=True,exist_ok=True); DASH.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({'generated_at_utc':generated,'methodology':'probability-space price forecasting with 80% empirical intervals','forecasts':forecasts},indent=2),encoding='utf-8')
    PERF.write_text(json.dumps(performance,indent=2),encoding='utf-8')
    ready=[x for x in forecasts if x['forecast_status']=='MODEL_READY']
    summary={'generated_at_utc':generated,'status':'READY' if forecasts else 'STANDBY','markets_scored':len(forecasts),'model_ready':len(ready),'insufficient_history':len(forecasts)-len(ready),'walk_forward_predictions':performance['walk_forward_predictions'],'point_mae':performance['point_mae'],'within_half_point_rate':performance['within_half_point_rate'],'within_one_point_rate':performance['within_one_point_rate'],'directional_accuracy':performance['directional_accuracy'],'top_forecasts':ready[:25],'warning':'Forecasts are research estimates and require continued live validation.'}
    DASH.write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2)); return summary
if __name__=='__main__':run()
