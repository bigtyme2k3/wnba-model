"""M25 ensemble intelligence combining production model signals."""
from __future__ import annotations
import argparse,json,math,os
from datetime import date,datetime,timezone

def load(path,default):
    try:return json.load(open(path,encoding='utf-8')) if os.path.exists(path) else default
    except Exception:return default

def num(v,d=0):
    try:
        n=float(v);return n if math.isfinite(n) else d
    except Exception:return d
def clamp(x,a,b):return max(a,min(b,x))
def build(target):
    decisions=load('data/dashboard/wnba_decision_engine_final.json',{}).get('top_decisions',[])
    calibration=load('data/dashboard/wnba_model_calibration.json',{});features=load('data/dashboard/wnba_feature_importance.json',{});optimizer=load('data/dashboard/wnba_hyperparameter_optimizer.json',{});learning=load('data/dashboard/wnba_self_learning.json',{})
    offset=clamp(num(calibration.get('summary',{}).get('calibration_offset')), -.05,.05); weights=optimizer.get('production_weights',[.35,.25,.25,.15]); learned=learning.get('engine_weights',{}); rows=[]
    for r in decisions:
        edge=clamp(num(r.get('edge_pct'))/15,0,1);ev=clamp(num(r.get('ev_pct'))/15,0,1);prob=clamp(num(r.get('simulation_probability'),.5)+offset,0.02,.98);market=clamp(.5+num(r.get('market_move'))/10,0,1)
        components={'edge':edge,'ev':ev,'simulation':prob,'market':market};score=sum(weights[i]*components[k] for i,k in enumerate(('edge','ev','simulation','market')))*100
        injury=str(r.get('injury_status') or 'ACTIVE').upper();risk=20+(15 if injury in {'QUESTIONABLE','UNKNOWN'} else 35 if injury in {'OUT','DOUBTFUL'} else 0)+(10 if num(r.get('book_count'))<2 else 0);confidence=clamp(prob*100-risk*.15,0,100)
        action='BET' if score>=78 and confidence>=60 and not r.get('guardrail_failures') else 'LEAN' if score>=68 else 'WATCH' if score>=55 else 'PASS'
        rows.append({**r,'ensemble_score':round(score,1),'calibrated_confidence':round(confidence,1),'risk_score':round(clamp(risk,0,100),1),'ensemble_action':action,'expected_roi':round(max(-1,min(1,num(r.get('ev_pct'))/100))*.9,4),'ensemble_components':{k:round(v,4) for k,v in components.items()},'production_weights':weights,'learning_weights_available':bool(learned)})
    rows.sort(key=lambda x:x['ensemble_score'],reverse=True)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'rows':len(rows),'bets':sum(x['ensemble_action']=='BET' for x in rows),'leans':sum(x['ensemble_action']=='LEAN' for x in rows),'watch':sum(x['ensemble_action']=='WATCH' for x in rows),'passes':sum(x['ensemble_action']=='PASS' for x in rows)},'top_decisions':rows,'top_3_game_picks':rows[:3]}
    os.makedirs('data/warehouse',exist_ok=True);os.makedirs('data/dashboard',exist_ok=True)
    for p in ('data/warehouse/wnba_ensemble_learning.json','data/dashboard/wnba_ensemble_learning.json'):json.dump(report,open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
    return report
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Ensemble:',build(a.date)['summary'])
if __name__=='__main__':main()
