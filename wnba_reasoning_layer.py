"""M19 explainability layer for BET, LEAN, WATCH and PASS decisions."""
from __future__ import annotations
import argparse,json,math,os
from datetime import date,datetime,timezone
from typing import Any

def load(p,d):
    try:return json.load(open(p,encoding='utf-8')) if os.path.exists(p) else d
    except Exception:return d

def sf(v,d=0.0):
    try:
        n=float(v);return n if math.isfinite(n) else d
    except Exception:return d

def factor(name,value,positive_when_high=True):
    score=sf(value); impact='positive' if (score>=0)==positive_when_high else 'negative'
    return {'factor':name,'value':round(score,3),'impact':impact}

def build(target):
    payload=load('data/warehouse/wnba_decision_engine_final.json',{}); decisions=payload.get('top_decisions',[]); rows=[]
    for r in decisions:
        positives=[]; negatives=[]
        factors=[factor('projection edge %',r.get('edge_pct')),factor('expected value %',r.get('ev_pct')),factor('simulation probability',sf(r.get('simulation_probability'))-0.5),factor('market movement',r.get('market_move')),factor('final score',sf(r.get('final_score'))-60)]
        for f in factors:(positives if f['impact']=='positive' else negatives).append(f)
        injury=str(r.get('injury_status') or 'ACTIVE').upper()
        if injury not in {'ACTIVE','PROBABLE'}:negatives.append({'factor':'injury status','value':injury,'impact':'negative'})
        guardrails=list(r.get('guardrail_failures') or []); selection=list(r.get('selection_failures') or [])
        action=str(r.get('final_action') or 'PASS').upper()
        summary=f"{action}: {r.get('player')} {r.get('stat')} {r.get('signal')} {r.get('line')}."
        if action=='BET':summary+=' Passed all guardrails and final selection requirements.'
        elif selection:summary+=' Passed initial guardrails but failed final selection: '+ '; '.join(selection)+'.'
        elif guardrails:summary+=' Failed guardrails: '+ '; '.join(guardrails)+'.'
        else:summary+=' No qualifying recommendation.'
        rows.append({'player':r.get('player'),'game':r.get('game'),'stat':r.get('stat'),'signal':r.get('signal'),'line':r.get('line'),'action':action,'summary':summary,'strongest_positive_factors':sorted(positives,key=lambda x:abs(sf(x.get('value'))),reverse=True)[:3],'strongest_negative_factors':sorted(negatives,key=lambda x:abs(sf(x.get('value'))),reverse=True)[:3],'guardrail_failures':guardrails,'selection_failures':selection,'injury_status':injury,'sportsbook':r.get('sportsbook'),'american_odds':r.get('american_odds'),'probability':r.get('simulation_probability'),'ev_pct':r.get('ev_pct'),'final_score':r.get('final_score')})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'rows':len(rows),'bets':sum(x['action']=='BET' for x in rows),'leans':sum(x['action']=='LEAN' for x in rows),'watch':sum(x['action']=='WATCH' for x in rows),'passes':sum(x['action']=='PASS' for x in rows)},'reasoning':rows}
    os.makedirs('data/warehouse',exist_ok=True);os.makedirs('data/dashboard',exist_ok=True)
    for p in ('data/warehouse/wnba_reasoning_layer.json','data/dashboard/wnba_reasoning_layer.json'):json.dump(report,open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Reasoning layer:',build(a.date)['summary'])
if __name__=='__main__':main()
