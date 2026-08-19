"""Chronological V5 TeamRankings challenger.

Research-only test of whether audited historical TeamRankings matchup evidence
adds predictive value over the archived V5 baseline. Uses only prior dated rows
to fit each test fold. Production predictions are never modified.
"""
from __future__ import annotations
import json, math, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SRC=Path('data/dashboard/wnba_v5_teamrankings_history_join.json')
OUT=Path('data/dashboard/wnba_v5_teamrankings_challenger.json')
WARE=Path('data/warehouse/teamrankings/challenger')

# Raw numeric arrays remain semantically unaudited. Use only invariant summaries
# (mean, spread, endpoint delta) so we do not pretend a particular column is
# season/last3/home/away until that schema is explicitly audited.

def sf(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None

def metric_summary(metrics):
    feats={}
    for name,obj in (metrics or {}).items():
        vals=[sf(x) for x in (obj or {}).get('values',[])]; vals=[x for x in vals if x is not None]
        if not vals: continue
        feats[f'{name}__mean']=statistics.fmean(vals)
        feats[f'{name}__range']=max(vals)-min(vals)
        feats[f'{name}__endpoint_delta']=vals[-1]-vals[0] if len(vals)>1 else 0.0
    return feats

def dot(w,x): return sum(w.get(k,0.0)*v for k,v in x.items())

def fit_ridge(rows, target='residual', lam=8.0, iters=450, lr=0.002):
    if not rows:return {}
    keys=sorted({k for r in rows for k in r['x']})
    means={k:statistics.fmean([r['x'].get(k,0.0) for r in rows]) for k in keys}
    sds={}
    for k in keys:
        arr=[r['x'].get(k,0.0) for r in rows]; sd=statistics.pstdev(arr)
        sds[k]=sd if sd>1e-9 else 1.0
    norm=[]
    for r in rows:
        z={k:(r['x'].get(k,0.0)-means[k])/sds[k] for k in keys}
        norm.append((z,r[target]))
    w={k:0.0 for k in keys}; b=statistics.fmean([y for _,y in norm])
    n=len(norm)
    for _ in range(iters):
        gb=0.0; gw={k:0.0 for k in keys}
        for x,y in norm:
            e=(b+dot(w,x))-y; gb+=e
            for k,v in x.items(): gw[k]+=e*v
        b-=lr*(2*gb/n)
        for k in keys:w[k]-=lr*((2*gw[k]/n)+(2*lam*w[k]/n))
    return {'b':b,'w':w,'means':means,'sds':sds,'keys':keys}

def pred(model,x):
    if not model:return 0.0
    z={k:(x.get(k,0.0)-model['means'][k])/model['sds'][k] for k in model['keys']}
    return model['b']+dot(model['w'],z)

def mae(rows,key):
    a=[abs(r[key]-r['actual']) for r in rows if sf(r.get(key)) is not None and sf(r.get('actual')) is not None]
    return statistics.fmean(a) if a else None

def side_result(proj,line,actual):
    if proj is None or line is None or actual is None:return None
    side='OVER' if proj>line else 'UNDER'
    if actual==line:return 'PUSH'
    return 'WIN' if (actual>line)==(side=='OVER') else 'LOSS'

def hit(rows,key):
    vals=[]
    for r in rows:
        z=side_result(r.get(key),r.get('line'),r.get('actual'))
        if z in {'WIN','LOSS'}:vals.append(z=='WIN')
    return sum(vals)/len(vals) if vals else None

def main():
    src=json.loads(SRC.read_text())
    assert src.get('challenger_ready') is True and src.get('lookahead_safe') is True
    base=[]
    for r in src.get('graded_rows',[]):
        if r.get('outcome')=='VOID':continue
        p=sf(r.get('projection')); a=sf(r.get('actual')); line=sf(r.get('line'))
        if p is None or a is None or line is None:continue
        x=metric_summary(r.get('teamrankings_metrics_raw'))
        if not x:continue
        base.append({'date':str(r.get('date'))[:10],'game_id':str(r.get('game_id')),'player':r.get('player'),'stat':r.get('stat'),'line':line,'baseline_projection':p,'actual':a,'residual':a-p,'x':x})
    base.sort(key=lambda r:(r['date'],r['game_id'],str(r['player']),str(r['stat'])))
    dates=sorted({r['date'] for r in base}); rows=[]
    for i,d in enumerate(dates):
        train=[r for r in base if r['date']<d]
        test=[r for r in base if r['date']==d]
        if len(train)<180:continue
        bystat=defaultdict(list)
        for r in train:bystat[r['stat']].append(r)
        models={s:fit_ridge(v) for s,v in bystat.items() if len(v)>=25}
        pooled=fit_ridge(train)
        for r in test:
            m=models.get(r['stat'],pooled)
            adj=pred(m,r['x'])
            q=dict(r); q['teamrankings_residual_adjustment']=round(adj,4); q['challenger_projection']=round(r['baseline_projection']+adj,4); rows.append(q)
    by_stat={}
    for stat in sorted({r['stat'] for r in rows}):
        rr=[r for r in rows if r['stat']==stat]
        by_stat[stat]={'n':len(rr),'baseline_mae':mae(rr,'baseline_projection'),'challenger_mae':mae(rr,'challenger_projection'),'baseline_hit_rate':hit(rr,'baseline_projection'),'challenger_hit_rate':hit(rr,'challenger_projection')}
        if by_stat[stat]['baseline_mae'] is not None and by_stat[stat]['challenger_mae'] is not None:
            by_stat[stat]['mae_improvement']=by_stat[stat]['baseline_mae']-by_stat[stat]['challenger_mae']
    payload={'version':'V5','module':'TEAMRANKINGS_CHRONOLOGICAL_CHALLENGER','status':'READY_RESEARCH_CHALLENGER','research_only':True,'production_ready':False,'lookahead_safe':True,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'method':'walk-forward residual ridge; each test date trained only on earlier dates; TeamRankings raw arrays summarized without assigning unaudited column semantics','source_graded_rows':len(src.get('graded_rows',[])),'eligible_rows':len(base),'evaluated_rows':len(rows),'evaluated_dates':len({r['date'] for r in rows}),'overall':{'baseline_mae':mae(rows,'baseline_projection'),'challenger_mae':mae(rows,'challenger_projection'),'baseline_hit_rate':hit(rows,'baseline_projection'),'challenger_hit_rate':hit(rows,'challenger_projection')},'by_stat':by_stat,'rows':rows}
    if payload['overall']['baseline_mae'] is not None and payload['overall']['challenger_mae'] is not None:
        payload['overall']['mae_improvement']=payload['overall']['baseline_mae']-payload['overall']['challenger_mae']
    OUT.write_text(json.dumps(payload,indent=2)+'\n')
    WARE.mkdir(parents=True,exist_ok=True); (WARE/'wnba_v5_teamrankings_challenger.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps({'evaluated_rows':payload['evaluated_rows'],'evaluated_dates':payload['evaluated_dates'],'overall':payload['overall']},indent=2))
if __name__=='__main__':main()
