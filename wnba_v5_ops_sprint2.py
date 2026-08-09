"""WNBA V5 Operations Sprint 2 (M01-M08).

Operationalizes grading, continuous learning, drift monitoring, long-term reporting,
promotion gating, explainability, research-lab comparison, and an autonomous daily
cycle without changing the V4 production champion. All outputs are research/shadow
artifacts unless the existing conservative promotion gates are satisfied.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean

D=Path('data/dashboard'); H=Path('data/history')
FWD=D/'wnba_v5_forward_validation.csv'; M05=D/'wnba_v5_m05_report.json'; M06=D/'wnba_v5_m06_report.json'; M08=D/'wnba_v5_m08_report.json'; M10=D/'wnba_v5_m10_report.json'; M11=D/'wnba_v5_live_inference.json'; M12=D/'wnba_v5_m12_report.json'; HEALTH=D/'wnba_alt_archive_health.json'
OUT={
'M01':D/'wnba_v5_s2_m01_outcome_grader.json','M02':D/'wnba_v5_s2_m02_continuous_learning.json','M03':D/'wnba_v5_s2_m03_drift_monitor.json','M04':D/'wnba_v5_s2_m04_performance_dashboard.json','M05':D/'wnba_v5_s2_m05_promotion_engine.json','M06':D/'wnba_v5_s2_m06_explainability.json','M07':D/'wnba_v5_s2_m07_research_lab.json','M08':D/'wnba_v5_s2_m08_autonomous_cycle.json','STATUS':D/'wnba_v5_ops_sprint2_status.json'}

def load(p,default=None):
    try:return json.loads(p.read_text(encoding='utf-8')) if p.exists() else ({} if default is None else default)
    except Exception:return {} if default is None else default

def n(v,d=None):
    try:
        x=float(v);return x if math.isfinite(x) else d
    except Exception:return d

def rows():
    if not FWD.exists():return []
    try:return list(csv.DictReader(FWD.open(encoding='utf-8-sig',newline='')))
    except Exception:return []

def write(k,obj):
    OUT[k].parent.mkdir(parents=True,exist_ok=True);OUT[k].write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8');return obj

def ts():return datetime.now(timezone.utc).isoformat()

def unit_profit(o,win):
    o=n(o)
    if o is None or o==0:return None
    if not win:return -1.0
    return o/100 if o>0 else 100/abs(o)

def metrics(q):
    b=[r for r in q if str(r.get('outcome')) in {'WIN','LOSS'} and n(r.get('v5_probability')) is not None]
    if not b:return {'n':0,'wins':0,'hit_rate':None,'brier':None,'market_brier':None,'roi':None,'profit_units':0.0}
    ys=[1 if r['outcome']=='WIN' else 0 for r in b]; ps=[n(r.get('v5_probability')) for r in b]; ms=[n(r.get('market_probability')) for r in b]
    br=mean((p-y)**2 for p,y in zip(ps,ys)); mb=mean((p-y)**2 for p,y in zip(ms,ys) if p is not None) if all(x is not None for x in ms) else None
    bets=[unit_profit(r.get('odds'),y) for r,y,p in zip(b,ys,ps) if p>=.5];bets=[x for x in bets if x is not None]
    return {'n':len(b),'wins':sum(ys),'hit_rate':round(mean(ys),6),'brier':round(br,6),'market_brier':None if mb is None else round(mb,6),'roi':None if not bets else round(sum(bets)/len(bets),6),'profit_units':round(sum(bets),4) if bets else 0.0}

def m01():
    r=load(M12);m=r.get('metrics') or {};pending=int(m.get('pending_predictions') or 0);graded=int(m.get('binary_graded_predictions') or 0)
    return write('M01',{'version':'V5','sprint':'S2','module':'S2-M01','stage':'AUTOMATED_OUTCOME_GRADER','status':'READY' if M12.exists() else 'WAITING_FOR_M12','generated_at_utc':ts(),'forward_predictions':int(m.get('forward_predictions') or 0),'graded_predictions':graded,'pending_predictions':pending,'newly_graded_last_run':int(r.get('newly_graded') or 0),'grading_policy':r.get('learning_policy'),'immutable_probabilities':True,'next_module':'S2-M02 Continuous Learning Pipeline'})

def m02():
    m05=load(M05);r=load(M12);met=r.get('metrics') or {};graded=int(met.get('binary_graded_predictions') or 0);champ=m05.get('research_champion') or 'KNN';retrain_due=graded>=25 and graded%25<5
    return write('M02',{'version':'V5','sprint':'S2','module':'S2-M02','stage':'CONTINUOUS_LEARNING','status':'READY','generated_at_utc':ts(),'research_champion':champ,'graded_forward_rows':graded,'candidate_models':[x.get('model') for x in (m05.get('rankings') or [])],'retrain_policy':'refresh candidate comparison every 25 newly graded forward rows; never auto-promote production','retrain_due':retrain_due,'production_champion':'V4','automatic_production_promotion':False,'next_module':'S2-M03 Model Drift Detection'})

def m03():
    q=rows();g=[r for r in q if r.get('outcome') in {'WIN','LOSS'}];allm=metrics(g);recent=metrics(g[-30:]);alerts=[]
    if recent['n']>=15 and allm['brier'] is not None and recent['brier']>allm['brier']+0.05:alerts.append('BRIER_DRIFT')
    if recent['n']>=15 and recent['roi'] is not None and recent['roi']<0:alerts.append('NEGATIVE_RECENT_ROI')
    return write('M03',{'version':'V5','sprint':'S2','module':'S2-M03','stage':'MODEL_DRIFT_DETECTION','status':'READY' if recent['n']>=15 else 'WAITING_FOR_MINIMUM_DRIFT_SAMPLE','generated_at_utc':ts(),'all_forward':allm,'recent_30':recent,'alerts':alerts,'drift_detected':bool(alerts),'minimum_recent_sample':15,'next_module':'S2-M04 Long-Term Performance Dashboard'})

def m04():
    q=[r for r in rows() if r.get('outcome') in {'WIN','LOSS'}];by_day=defaultdict(list);by_month=defaultdict(list);by_stat=defaultdict(list);by_player=defaultdict(list)
    for r in q:
        d=str(r.get('date') or '')[:10];by_day[d].append(r);by_month[d[:7]].append(r);by_stat[str(r.get('stat') or 'UNKNOWN')].append(r);by_player[str(r.get('player') or 'UNKNOWN')].append(r)
    top_players=sorted(({'player':k,**metrics(v)} for k,v in by_player.items()),key=lambda x:(x['n'],x['profit_units']),reverse=True)[:20]
    return write('M04',{'version':'V5','sprint':'S2','module':'S2-M04','stage':'LONG_TERM_PERFORMANCE_DASHBOARD','status':'READY','generated_at_utc':ts(),'lifetime':metrics(q),'daily':{k:metrics(v) for k,v in sorted(by_day.items())[-31:]},'monthly':{k:metrics(v) for k,v in sorted(by_month.items())},'by_stat':{k:metrics(v) for k,v in sorted(by_stat.items())},'top_players':top_players,'next_module':'S2-M05 Promotion Engine'})

def m05():
    r=load(M12);met=r.get('metrics') or {};gate=r.get('promotion_gate') or {};health=load(HEALTH);m10=load(M10);graded=int(met.get('binary_graded_predictions') or 0);clv=n(gate.get('explicit_clv_coverage_pct'),0.0);vb=n(met.get('v5_brier'));mb=n(met.get('market_brier'));roi=n(met.get('positive_edge_roi'));checks={'forward_rows':graded>=300,'clv':clv>=60,'brier':vb is not None and mb is not None and vb<mb,'roi':roi is not None and roi>0,'archive':health.get('status')=='HEALTHY_LOCKED','pipeline':m10.get('status')=='READY_SHADOW'};ready=all(checks.values())
    state='PRODUCTION_READY' if ready else ('CANDIDATE' if graded>=225 and clv>=45 and checks['archive'] else 'SHADOW')
    return write('M05',{'version':'V5','sprint':'S2','module':'S2-M05','stage':'PROMOTION_ENGINE','status':'READY','generated_at_utc':ts(),'promotion_state':state,'production_ready':ready,'checks':checks,'forward_graded':graded,'explicit_clv_coverage_pct':clv,'v5_brier':vb,'market_brier':mb,'positive_edge_roi':roi,'production_champion':'V4' if not ready else 'V5_CANDIDATE_FOR_REVIEW','automatic_switch_disabled':True,'next_module':'S2-M06 Explainability Layer'})

def m06():
    inf=load(M11);scored=inf.get('scored',[]) if isinstance(inf,dict) else [];expl=[]
    for r in scored:
        fs=r.get('feature_snapshot') or {};reasons=[]
        edge=n(r.get('probability_edge'))
        if edge is not None:reasons.append({'signal':'model_vs_market','value':round(edge,6),'direction':'supports' if edge>0 else 'opposes'})
        reasons.append({'signal':'historical_hit_rate','value':fs.get('historical_hit_rate_at_current_line')})
        reasons.append({'signal':'recent_mean_vs_line','value':fs.get('line_minus_prior_mean')})
        reasons.append({'signal':'trend_slope','value':fs.get('rolling5_trend_slope')})
        reasons.append({'signal':'neighbor_hit_rate','value':r.get('neighbor_hit_rate')})
        expl.append({'ranking_key':r.get('ranking_key'),'player':r.get('player'),'market':r.get('market'),'side':r.get('side'),'v5_probability':r.get('v5_probability'),'confidence_score':r.get('confidence_score'),'uncertainty_score':r.get('uncertainty_score'),'reasons':reasons,'explanation_status':'RESEARCH_ONLY'})
    return write('M06',{'version':'V5','sprint':'S2','module':'S2-M06','stage':'EXPLAINABILITY','status':'READY' if scored else 'WAITING_FOR_LIVE_SCORES','generated_at_utc':ts(),'explained_predictions':len(expl),'explanations':expl,'policy':'Explanations describe model inputs; they do not claim causality.','next_module':'S2-M07 Research Laboratory'})

def m07():
    a=load(M05);b=load(M08);experiments=[]
    for r in a.get('rankings') or []:experiments.append({'family':'M05','model':r.get('model'),'brier':r.get('brier'),'log_loss':r.get('log_loss'),'roi':r.get('roi_at_0_5')})
    for r in b.get('rankings') or []:experiments.append({'family':'M08_CONTEXT','model':r.get('model'),'brier':r.get('brier'),'log_loss':r.get('log_loss'),'roi':r.get('roi')})
    experiments.sort(key=lambda x:(999 if x['brier'] is None else x['brier'],999 if x['log_loss'] is None else x['log_loss']))
    return write('M07',{'version':'V5','sprint':'S2','module':'S2-M07','stage':'RESEARCH_LABORATORY','status':'READY','generated_at_utc':ts(),'current_research_champion':a.get('research_champion') or 'KNN','evaluated_experiments':experiments,'top_experiments':experiments[:10],'future_candidate_queue':['Gradient Boosting','Random Forest','XGBoost (optional dependency)','LightGBM (optional dependency)','CatBoost (optional dependency)','Bayesian calibration','Neural network research only'],'production_isolation':True,'next_module':'S2-M08 Fully Autonomous Daily Cycle'})

def m08():
    mods={k:load(OUT[k]) for k in ['M01','M02','M03','M04','M05','M06','M07']};ready=all(v for v in mods.values());promo=mods.get('M05',{}).get('promotion_state','SHADOW');obj={'version':'V5','sprint':'S2','module':'S2-M08','stage':'AUTONOMOUS_DAILY_CYCLE','status':'READY' if ready else 'PARTIAL','generated_at_utc':ts(),'cycle':['grade certified outcomes','refresh forward metrics','refresh candidate research comparison','detect drift','publish long-term performance','evaluate promotion gate','publish explainability','refresh research lab'],'module_status':{k:v.get('status') for k,v in mods.items()},'promotion_state':promo,'production_switch_automatic':False,'research_only_until_gate':True};write('M08',obj)
    status={'version':'V5','sprint':'OPERATIONS_SPRINT_2','status':'COMPLETE' if ready else 'PARTIAL','generated_at_utc':ts(),'modules':{**{k:OUT[k].name for k in ['M01','M02','M03','M04','M05','M06','M07']},'M08':OUT['M08'].name},'promotion_state':promo,'production_ready':mods.get('M05',{}).get('production_ready',False),'next_focus':'RUN_AUTONOMOUS_CYCLE_AND_ACCUMULATE_FORWARD_EVIDENCE'};write('STATUS',status);return obj

FUN={'M01':m01,'M02':m02,'M03':m03,'M04':m04,'M05':m05,'M06':m06,'M07':m07,'M08':m08}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--module',default='all');a=ap.parse_args();target=a.module.upper()
    if target=='ALL':
        for k in ['M01','M02','M03','M04','M05','M06','M07']:FUN[k]()
        out=m08()
    elif target in FUN:out=FUN[target]()
    else:raise SystemExit('unknown module')
    print(json.dumps(out,indent=2,allow_nan=False))
if __name__=='__main__':main()
