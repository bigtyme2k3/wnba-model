"""V5-M10 live adaptive decision engine.

Consumes the M09 research policy, current opportunity rankings, market movement,
and the explicit M11 live V5 inference bridge. Generic V4 probabilities are never
relabeled as V5.
"""
from __future__ import annotations
import csv,json,math
from datetime import datetime,timezone
from pathlib import Path

POLICY=Path('data/dashboard/wnba_v5_decision_engine.json')
RANK=Path('data/warehouse/wnba_opportunity_rankings.json')
MOVE=Path('data/dashboard/market_movement.json')
INFER=Path('data/dashboard/wnba_v5_live_inference.json')
OUT_DEC=Path('data/dashboard/wnba_v5_live_decisions.json')
OUT_ALERT=Path('data/dashboard/wnba_v5_alerts.json')
OUT_REFRESH=Path('data/dashboard/wnba_v5_market_refresh.json')
OUT_PORT=Path('data/dashboard/wnba_v5_live_portfolio.json')
OUT_EV=Path('data/dashboard/wnba_v5_live_ev.csv')
OUT_LINES=Path('data/dashboard/wnba_v5_line_changes.csv')
OUT_BUY=Path('data/dashboard/wnba_v5_buy_signals.json')
REPORT=Path('data/dashboard/wnba_v5_m10_report.json')

def f(v,d=None):
    try:
        x=float(v);return x if math.isfinite(x) else d
    except Exception:return d

def norm(v):return ' '.join(str(v or '').strip().lower().split())
def implied(o):
    o=f(o)
    if o is None or o==0:return None
    return abs(o)/(abs(o)+100) if o<0 else 100/(o+100)
def mult(o):
    o=f(o)
    if o is None or o==0:return None
    return 100/abs(o) if o<0 else o/100
def ev(p,o):
    b=mult(o)
    return None if b is None else p*b-(1-p)
def read_json(path,default):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def p5(r):
    for k in ('v5_probability','knn_probability'):
        x=f(r.get(k))
        if x is not None and 0<=x<=1:return x,k
    return None,None

def odds(r):
    for k in ('best_odds','american_odds','odds','price'):
        x=f(r.get(k))
        if x is not None:return x
    return None

def ranking_key(r):
    if r.get('ranking_key'):return str(r.get('ranking_key'))
    return '|'.join(norm(x) for x in (r.get('date'),r.get('player'),r.get('game'),r.get('market') or r.get('stat'),r.get('side') or r.get('signal')))

def movement_key(r):
    return '|'.join(norm(x) for x in (r.get('date'),r.get('player'),r.get('game'),r.get('market') or r.get('stat'),r.get('side') or r.get('signal')))

def main():
    now=datetime.now(timezone.utc).isoformat()
    policy=read_json(POLICY,{})
    payload=read_json(RANK,{'all_ranked':[]})
    rows=payload.get('all_ranked',[]) if isinstance(payload,dict) else []
    if not rows and isinstance(payload,dict):rows=payload.get('top_opportunities',[]) or []
    movement=read_json(MOVE,{}); markets=movement.get('markets',[]) if isinstance(movement,dict) else []
    midx={movement_key(x):x for x in markets if isinstance(x,dict)}

    inference=read_json(INFER,{})
    inferred=inference.get('scored',[]) if isinstance(inference,dict) else []
    iidx={str(x.get('ranking_key')):x for x in inferred if x.get('ranking_key')}

    min_ev=f(policy.get('minimum_ev'),0.02);max_bet=f(policy.get('max_bet_units'),0.5);max_daily=f(policy.get('max_daily_units'),5.0)
    decisions=[];alerts=[]
    for raw in rows:
        r=dict(raw)
        inf=iidx.get(ranking_key(r))
        if inf:
            r['v5_probability']=inf.get('v5_probability')
            r['knn_probability']=inf.get('knn_probability')
            r['v5_confidence_score']=inf.get('confidence_score')
            r['v5_uncertainty_score']=inf.get('uncertainty_score')
            r['v5_probability_band']=inf.get('probability_band')
        p,psrc=p5(r);o=odds(r);mp=implied(o);e=ev(p,o) if p is not None else None;m=midx.get(movement_key(r),{})
        move=f(m.get('total_directional_line_move'),0.0);steam=bool(m.get('steam_detected'));reverse=bool(m.get('reverse_line_movement'))
        state='UNSCORED'
        if p is not None and o is not None:
            if e is None or e<=0:state='REMOVE'
            elif e<min_ev:state='WATCH'
            elif reverse:state='HOLD'
            elif steam and move>0:state='BUY_BEFORE_MOVE'
            elif e>=min_ev:state='BUY_NOW'
        edge=None if p is None or mp is None else p-mp
        d={'ranking_key':ranking_key(r),'date':r.get('date'),'player':r.get('player'),'game':r.get('game'),'market':r.get('market') or r.get('stat'),'side':r.get('side') or r.get('signal'),'line':f(r.get('best_line',r.get('line'))),'odds':o,'best_book':r.get('best_book'),'v5_probability':p,'probability_source':psrc,'v5_confidence_score':r.get('v5_confidence_score'),'v5_uncertainty_score':r.get('v5_uncertainty_score'),'v5_probability_band':r.get('v5_probability_band'),'market_probability':mp,'edge':edge,'expected_value':e,'movement':move,'steam':steam,'reverse_move':reverse,'decision_state':state,'research_only':True}
        decisions.append(d)
        if state in {'BUY_NOW','BUY_BEFORE_MOVE'}:alerts.append({'type':state,'player':d['player'],'market':d['market'],'side':d['side'],'ev':e,'message':'Research-only V5 shadow signal'})
        elif reverse and p is not None:alerts.append({'type':'REVERSE_MOVE','player':d['player'],'market':d['market'],'side':d['side'],'message':'Market moved against V5 direction'})
    actionable=[x for x in decisions if x['decision_state'] in {'BUY_NOW','BUY_BEFORE_MOVE'}]
    actionable.sort(key=lambda x:(f(x.get('expected_value'),-9),f(x.get('edge'),-9)),reverse=True)
    portfolio=[];used=0.0
    for x in actionable:
        stake=min(max_bet,0.5)
        if used+stake>max_daily:break
        y=dict(x);y['recommended_units']=stake;portfolio.append(y);used+=stake
    scored=sum(x['v5_probability'] is not None for x in decisions)
    status='READY_SHADOW' if scored else ('WAITING_FOR_M09' if not policy else 'STANDBY_NO_LIVE_V5_SCORES')
    report={'version':'V5','module':'V5-M10','stage':'LIVE_ADAPTIVE_DECISION_ENGINE','status':status,'generated_at_utc':now,'ranked_rows':len(rows),'m11_inference_rows':len(inferred),'v5_scored_rows':scored,'actionable_rows':len(actionable),'portfolio_rows':len(portfolio),'portfolio_units':round(used,3),'alerts':len(alerts),'research_only':True,'production_ready':False,'safety_note':'Only explicit M11 v5_probability/knn_probability can activate V5 decisions. Generic V4 probabilities are never relabeled as V5.','next_module':'V5-M12 Post-Game Learning + Forward Validation'}
    OUT_DEC.parent.mkdir(parents=True,exist_ok=True)
    OUT_DEC.write_text(json.dumps({'decisions':decisions,'report':report},indent=2)+'\n',encoding='utf-8')
    OUT_ALERT.write_text(json.dumps({'generated_at_utc':now,'alerts':alerts},indent=2)+'\n',encoding='utf-8')
    OUT_REFRESH.write_text(json.dumps({'generated_at_utc':now,'ranked_rows':len(rows),'movement_rows':len(markets),'m11_inference_rows':len(inferred),'v5_scored_rows':scored,'status':status},indent=2)+'\n',encoding='utf-8')
    OUT_PORT.write_text(json.dumps({'generated_at_utc':now,'research_only':True,'portfolio':portfolio,'total_units':round(used,3)},indent=2)+'\n',encoding='utf-8')
    OUT_BUY.write_text(json.dumps({'generated_at_utc':now,'signals':[x for x in decisions if x['decision_state'] in {'BUY_NOW','BUY_BEFORE_MOVE'}]},indent=2)+'\n',encoding='utf-8')
    fields=['date','player','game','market','side','line','odds','v5_probability','market_probability','edge','expected_value','movement','steam','reverse_move','decision_state']
    with OUT_EV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows([{k:x.get(k) for k in fields} for x in decisions])
    lfields=['date','player','game','market','side','line','movement','steam','reverse_move']
    with OUT_LINES.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=lfields);w.writeheader();w.writerows([{k:x.get(k) for k in lfields} for x in decisions])
    REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
