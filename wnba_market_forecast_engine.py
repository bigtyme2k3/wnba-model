"""Sprint 17 Commit 1: forecast closing market lines from stored timeline state.

The model is deliberately transparent. It learns average remaining movement from
historical pregame observations grouped by sportsbook, market, selection, time window,
movement direction, volatility and market signal. Forecasts are research estimates,
not guarantees and not wager instructions.
"""
from __future__ import annotations
import json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

TIMELINE=Path('data/market/market_timeline.json')
MOVES=Path('data/market/line_movements.json')
SIGNALS=Path('data/market/movement_classifications.json')
OUT=Path('data/forecast/market_forecasts.json')
PERF=Path('data/forecast/market_forecast_performance.json')
DASH=Path('data/dashboard/wnba_market_forecast_summary.json')
MIN_SAMPLE=12

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def parse(v): return datetime.fromisoformat(str(v).replace('Z','+00:00'))
def load(path,key):
    if not path.exists(): return []
    raw=json.loads(path.read_text(encoding='utf-8')).get(key,[])
    return raw if isinstance(raw,list) else []
def num(v):
    try:return float(v)
    except (TypeError,ValueError):return None
def delta(a,b):
    a=num(a); b=num(b)
    return None if a is None or b is None else b-a
def window(minutes):
    m=float(minutes or 0)
    if m>=1440:return '24H_PLUS'
    if m>=720:return '12_TO_24H'
    if m>=360:return '6_TO_12H'
    if m>=180:return '3_TO_6H'
    if m>=60:return '1_TO_3H'
    return 'FINAL_HOUR'
def band(v):
    v=float(v or 0)
    return 'HIGH' if v>=70 else ('MEDIUM' if v>=35 else 'LOW')
def direction(opening,current):
    d=delta(opening,current)
    if d is None or abs(d)<1e-9:return 'NEUTRAL'
    if d>0:return 'STRONG_UP' if abs(d)>=2 else 'UP'
    return 'STRONG_DOWN' if abs(d)>=2 else 'DOWN'
def key_for(book,market,selection,w,d,v,s):
    return (str(book),str(market),str(selection),str(w),str(d),str(v),str(s))
def confidence(sample,mae,dispersion):
    reliability=min(55,math.log10(max(sample,1))*24)
    accuracy=max(0,30-min(30,float(mae or 0)*12))
    stability=max(0,15-min(15,float(dispersion or 0)*8))
    return round(min(100,reliability+accuracy+stability),2)

def run():
    timelines=load(TIMELINE,'markets')
    move_map={x['market_id']:x for x in load(MOVES,'movements')}
    signal_map={x['market_id']:x for x in load(SIGNALS,'classifications')}
    examples=[]
    for t in timelines:
        obs=t.get('observations') or []
        if len(obs)<2: continue
        close=obs[-1]; close_point=num(close.get('point')); close_price=num(close.get('american_price'))
        m=move_map.get(t['market_id'],{}); s=signal_map.get(t['market_id'],{})
        for i,row in enumerate(obs[:-1]):
            mins=(parse(t['commence_time_utc'])-parse(row['snapshot_time_utc'])).total_seconds()/60
            opening=obs[0]
            k=key_for(t.get('bookmaker'),t.get('market'),t.get('selection'),window(mins),direction(opening.get('point'),row.get('point')),band(m.get('volatility_score')),s.get('classification','NORMAL'))
            examples.append({'key':k,'market_id':t['market_id'],'event_id':t['event_id'],'time':row['snapshot_time_utc'],'current_point':num(row.get('point')),'current_price':num(row.get('american_price')),'closing_point':close_point,'closing_price':close_price,'remaining_point_move':delta(row.get('point'),close_point),'remaining_price_move':delta(row.get('american_price'),close_price)})
    groups=defaultdict(list)
    for x in examples: groups[x['key']].append(x)
    models={}
    for k,rows in groups.items():
        p=[x['remaining_point_move'] for x in rows if x['remaining_point_move'] is not None]
        q=[x['remaining_price_move'] for x in rows if x['remaining_price_move'] is not None]
        if len(rows)<MIN_SAMPLE: continue
        pavg=mean(p) if p else None; qavg=mean(q) if q else None
        pmae=mean(abs(v-pavg) for v in p) if p and pavg is not None else None
        pdisp=median(abs(v-median(p)) for v in p) if p else None
        models[k]={'sample_size':len(rows),'average_remaining_point_move':None if pavg is None else round(pavg,6),'average_remaining_price_move':None if qavg is None else round(qavg,6),'point_mae':None if pmae is None else round(pmae,6),'point_dispersion':None if pdisp is None else round(pdisp,6),'confidence':confidence(len(rows),pmae,pdisp)}
    backtests=[]
    for x in examples:
        model=models.get(x['key'])
        if not model: continue
        pp=None if x['current_point'] is None or model['average_remaining_point_move'] is None else round(x['current_point']+model['average_remaining_point_move'],6)
        pr=None if x['current_price'] is None or model['average_remaining_price_move'] is None else round(x['current_price']+model['average_remaining_price_move'],6)
        err=None if pp is None or x['closing_point'] is None else abs(pp-x['closing_point'])
        backtests.append({'market_id':x['market_id'],'event_id':x['event_id'],'predicted_closing_point':pp,'actual_closing_point':x['closing_point'],'absolute_point_error':err,'predicted_closing_price':pr,'actual_closing_price':x['closing_price'],'confidence':model['confidence'],'sample_size':model['sample_size']})
    forecasts=[]
    for t in timelines:
        obs=t.get('observations') or []
        if not obs: continue
        current=obs[-1]; opening=obs[0]
        mins=(parse(t['commence_time_utc'])-parse(current['snapshot_time_utc'])).total_seconds()/60
        m=move_map.get(t['market_id'],{}); s=signal_map.get(t['market_id'],{})
        k=key_for(t.get('bookmaker'),t.get('market'),t.get('selection'),window(mins),direction(opening.get('point'),current.get('point')),band(m.get('volatility_score')),s.get('classification','NORMAL'))
        model=models.get(k); cp=num(current.get('point')); price=num(current.get('american_price'))
        status='MODEL_READY' if model else 'INSUFFICIENT_HISTORY'
        pp=None if not model or cp is None or model['average_remaining_point_move'] is None else round(cp+model['average_remaining_point_move'],6)
        pr=None if not model or price is None or model['average_remaining_price_move'] is None else round(price+model['average_remaining_price_move'],6)
        forecasts.append({'market_id':t['market_id'],'event_id':t['event_id'],'commence_time_utc':t['commence_time_utc'],'home_team':t['home_team'],'away_team':t['away_team'],'bookmaker':t['bookmaker'],'market':t['market'],'participant':t.get('participant'),'selection':t.get('selection'),'current_time_utc':current['snapshot_time_utc'],'minutes_to_tip':round(mins,2),'current_point':cp,'current_price':price,'projected_closing_point':pp,'projected_closing_price':pr,'expected_point_move':None if not model else model['average_remaining_point_move'],'expected_price_move':None if not model else model['average_remaining_price_move'],'forecast_confidence':0 if not model else model['confidence'],'model_sample_size':0 if not model else model['sample_size'],'forecast_status':status,'signal':s.get('classification','NORMAL'),'volatility_score':m.get('volatility_score',0),'methodology':'historical analog average remaining movement'})
    valid_errors=[x['absolute_point_error'] for x in backtests if x['absolute_point_error'] is not None]
    generated=now(); OUT.parent.mkdir(parents=True,exist_ok=True); DASH.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({'generated_at_utc':generated,'warning':'Forecasts are estimates from historical analogs, not guarantees.','forecasts':forecasts},indent=2),encoding='utf-8')
    performance={'generated_at_utc':generated,'training_examples':len(examples),'models':len(models),'backtest_predictions':len(backtests),'point_mae':round(mean(valid_errors),6) if valid_errors else None,'within_half_point_rate':round(sum(e<=.5 for e in valid_errors)/len(valid_errors),6) if valid_errors else None,'within_one_point_rate':round(sum(e<=1 for e in valid_errors)/len(valid_errors),6) if valid_errors else None,'records':backtests[:5000]}
    PERF.write_text(json.dumps(performance,indent=2),encoding='utf-8')
    ready=[x for x in forecasts if x['forecast_status']=='MODEL_READY']
    summary={'generated_at_utc':generated,'status':'READY' if forecasts else 'STANDBY','markets_scored':len(forecasts),'model_ready':len(ready),'insufficient_history':len(forecasts)-len(ready),'historical_examples':len(examples),'analog_models':len(models),'backtest_point_mae':performance['point_mae'],'within_half_point_rate':performance['within_half_point_rate'],'within_one_point_rate':performance['within_one_point_rate'],'top_expected_moves':sorted(ready,key=lambda x:-abs(float(x.get('expected_point_move') or 0)))[:25],'warning':'Projected closing lines are research estimates and require live validation.'}
    DASH.write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2)); return summary
if __name__=='__main__': run()
