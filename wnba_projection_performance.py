"""Projection Performance: snapshot, grade, diagnose, and recommend.

Pregame unified projections are frozen in JSONL history. Final results are read
only from the verified player-game-log warehouse. Model changes are never
applied automatically before minimum sample thresholds are met.
"""
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

UNIFIED=Path('data/dashboard/wnba_unified_player_simulation_v2.json')
TOP=Path('data/dashboard/wnba_cross_market_top_plays.json')
LOGS=Path('data/warehouse/wnba_player_game_logs.json')
HISTORY=Path('data/history/wnba_projection_history.jsonl')
OUTS=[Path('data/warehouse/wnba_projection_performance.json'),Path('data/dashboard/wnba_projection_performance.json')]
STATS=('MIN','PTS','REB','OREB','DREB','AST','3PM','STL','BLK','TOV','PRA','PR','PA','RA')

def load(p:Path,d:Any)->Any:
    try:return json.load(p.open(encoding='utf-8')) if p.exists() else d
    except Exception:return d
def read_jsonl(p:Path)->list[dict[str,Any]]:
    out=[]
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            try:
                r=json.loads(line)
                if isinstance(r,dict):out.append(r)
            except Exception:pass
    return out
def write_jsonl(p:Path,rows:list[dict[str,Any]])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(''.join(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n' for r in rows),encoding='utf-8')
def dump(p:Path,x:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True);json.dump(x,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def actuals(row:dict[str,Any])->dict[str,float]:
    s=row.get('scoring',{}) if isinstance(row.get('scoring'),dict) else {};b=row.get('boxscore',{}) if isinstance(row.get('boxscore'),dict) else {}
    pts=num(s.get('total_pts')) or 0;reb=num(b.get('reb')) or 0;ast=num(b.get('ast')) or 0
    oreb=num(b.get('oreb'));dreb=num(b.get('dreb'))
    if oreb is None and dreb is None:oreb=0;dreb=reb
    elif oreb is None:oreb=max(0,reb-(dreb or 0))
    elif dreb is None:dreb=max(0,reb-(oreb or 0))
    return {'MIN':num(row.get('minutes')) or 0,'PTS':pts,'REB':reb,'OREB':oreb or 0,'DREB':dreb or 0,'AST':ast,'3PM':num(s.get('three_pm')) or 0,'STL':num(b.get('stl')) or 0,'BLK':num(b.get('blk')) or 0,'TOV':num(b.get('tov')) or 0,'PRA':pts+reb+ast,'PR':pts+reb,'PA':pts+ast,'RA':reb+ast}
def snapshot(target:str)->dict[str,int]:
    payload=load(UNIFIED,{'players':[]});top=load(TOP,{});existing=read_jsonl(HISTORY);seen={r.get('projection_id') for r in existing};markets=defaultdict(list)
    for r in top.get('top_plays',[]):
        if r.get('player'):markets[norm(r.get('player'))].append(r)
    added=0
    for p in payload.get('players',[]):
        for stat in STATS:
            d=(p.get('distributions') or {}).get(stat)
            if not isinstance(d,dict):continue
            pid='|'.join([target,norm(p.get('player')),stat])
            if pid in seen:continue
            market=next((m for m in markets[norm(p.get('player'))] if str(m.get('stat'))==stat),None)
            existing.append({'projection_id':pid,'date':target,'captured_at_utc':datetime.now(timezone.utc).isoformat(),'player':p.get('player'),'team':p.get('team'),'opponent':p.get('opponent'),'stat':stat,'mean':d.get('mean'),'p10':d.get('p10'),'p25':d.get('p25'),'p50':d.get('p50'),'p75':d.get('p75'),'p90':d.get('p90'),'confidence':p.get('confidence'),'data_quality_status':p.get('data_quality_status'),'line':market.get('line') if market else None,'side':market.get('side') if market else None,'odds':market.get('odds') if market else None,'predicted_probability':market.get('hit_probability') if market else None,'decision':market.get('decision') if market else None,'recommended_units':market.get('recommended_units_final') if market else None,'actual':None,'outcome':'PENDING','source':'unified_player_simulation_v2'})
            added+=1;seen.add(pid)
    write_jsonl(HISTORY,existing);return {'added':added,'total':len(existing)}
def grade()->dict[str,int]:
    history=read_jsonl(HISTORY);logs=load(LOGS,{'records':[]}).get('records',[]);idx={}
    for r in logs:
        key=(str(r.get('game_date') or '')[:10],norm(r.get('player')))
        idx[key]=r
    graded=0
    for r in history:
        if r.get('outcome')!='PENDING':continue
        log=idx.get((str(r.get('date')),norm(r.get('player'))))
        if not log:continue
        a=actuals(log).get(str(r.get('stat')));mean=num(r.get('mean'))
        if a is None or mean is None:continue
        r['actual']=a;r['absolute_error']=round(abs(mean-a),4);r['bias']=round(mean-a,4);r['inside_p10_p90']=bool((num(r.get('p10')) or -1e9)<=a<=(num(r.get('p90')) or 1e9));r['actual_source']='player_game_log_warehouse'
        line=num(r.get('line'));side=str(r.get('side') or '').upper()
        if line is None or not side:r['outcome']='GRADED_NO_MARKET';r['profit_loss']=None
        elif a==line:r['outcome']='PUSH';r['profit_loss']=0.0
        else:
            win=(a>line) if side=='OVER' else (a<line);r['outcome']='WIN' if win else 'LOSS';odds=num(r.get('odds'))
            r['profit_loss']=round((100/abs(odds) if odds and odds<0 else odds/100 if odds else 0),4) if win else -1.0
        graded+=1
    write_jsonl(HISTORY,history);return {'graded':graded,'total':len(history)}
def summarize(rows:list[dict[str,Any]])->dict[str,Any]:
    g=[r for r in rows if r.get('actual') is not None]
    wins=[r for r in g if r.get('outcome') in {'WIN','LOSS','PUSH'}]
    return {'graded':len(g),'mae':round(sum(num(r.get('absolute_error')) or 0 for r in g)/len(g),4) if g else None,'bias':round(sum(num(r.get('bias')) or 0 for r in g)/len(g),4) if g else None,'p10_p90_coverage':round(sum(bool(r.get('inside_p10_p90')) for r in g)/len(g),4) if g else None,'market_decisions':len(wins),'wins':sum(r.get('outcome')=='WIN' for r in wins),'losses':sum(r.get('outcome')=='LOSS' for r in wins),'pushes':sum(r.get('outcome')=='PUSH' for r in wins),'hit_rate':round(sum(r.get('outcome')=='WIN' for r in wins)/sum(r.get('outcome') in {'WIN','LOSS'} for r in wins),4) if sum(r.get('outcome') in {'WIN','LOSS'} for r in wins) else None,'profit_loss':round(sum(num(r.get('profit_loss')) or 0 for r in wins),4),'roi':round(sum(num(r.get('profit_loss')) or 0 for r in wins)/len(wins),4) if wins else None}
def grouped(rows:list[dict[str,Any]],field:str)->list[dict[str,Any]]:
    groups=defaultdict(list)
    for r in rows:groups[str(r.get(field) or 'Unknown')].append(r)
    return sorted([{'group':k,**summarize(v)} for k,v in groups.items()],key=lambda x:x['graded'],reverse=True)
def probability_bands(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    bands=[(.50,.55),(.55,.60),(.60,.65),(.65,.70),(.70,1.01)];out=[]
    for lo,hi in bands:
        subset=[r for r in rows if (num(r.get('predicted_probability')) is not None and lo<=num(r.get('predicted_probability'))<hi and r.get('outcome') in {'WIN','LOSS'})]
        if not subset:continue
        predicted=sum(num(r.get('predicted_probability')) or 0 for r in subset)/len(subset);actual=sum(r.get('outcome')=='WIN' for r in subset)/len(subset)
        out.append({'band':f'{int(lo*100)}-{int(min(hi,1)*100)}%','count':len(subset),'predicted':round(predicted,4),'actual':round(actual,4),'calibration_error':round(actual-predicted,4)})
    return out
def recommendations(by_stat:list[dict[str,Any]])->list[dict[str,Any]]:
    out=[]
    for r in by_stat:
        n=r['graded'];bias=num(r.get('bias'));coverage=num(r.get('p10_p90_coverage'))
        if n<50:status='LOCKED';text='Collect at least 50 graded projections before diagnosing directional bias.'
        elif n<100:status='DIAGNOSE_ONLY';text=f"Observed bias {bias:+.2f}; do not change stat weights before 100 graded projections."
        elif n<200:status='WEIGHT_REVIEW';text=f"Review baseline/matchup weights for persistent bias {bias:+.2f}; simulation variance remains locked until 200."
        else:status='CALIBRATION_ELIGIBLE';text=f"Eligible for controlled stat-weight and variance recalibration. P10-P90 coverage: {coverage:.1%}." if coverage is not None else 'Eligible for controlled recalibration.'
        out.append({'stat':r['group'],'graded':n,'status':status,'recommendation':text})
    return out
def analyze(target:str)->dict[str,Any]:
    rows=read_jsonl(HISTORY);by_stat=grouped(rows,'stat');payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':summarize(rows),'by_stat':by_stat,'by_confidence':grouped(rows,'confidence'),'by_quality':grouped(rows,'data_quality_status'),'probability_calibration':probability_bands(rows),'recommendations':recommendations(by_stat),'thresholds':{'bias_reporting':50,'stat_weight_adjustment':100,'simulation_variance_adjustment':200},'policy':{'automatic_recalibration':False,'actual_source':'player_game_log_warehouse','snapshot_immutability':'pregame projection fields are never rewritten','minimum_samples_enforced':True}}
    for p in OUTS:dump(p,payload)
    return payload
def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('snapshot','grade','analyze','all'));ap.add_argument('--date',default=str(date.today()));a=ap.parse_args()
    if a.mode in {'snapshot','all'}:print('snapshot',snapshot(a.date))
    if a.mode in {'grade','all'}:print('grade',grade())
    if a.mode in {'analyze','all'}:print('analyze',analyze(a.date)['summary'])
if __name__=='__main__':main()
