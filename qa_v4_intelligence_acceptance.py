"""Deterministic production acceptance tests for M21-M25."""
from __future__ import annotations
import json,os,tempfile
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import wnba_model_calibration as calibration
import wnba_feature_importance as importance
import wnba_hyperparameter_optimizer as optimizer
import wnba_daily_retraining as retraining
import wnba_ensemble_learning as ensemble
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'data/dashboard/wnba_v4_intelligence_acceptance.json';REPORT=ROOT/'docs/V4_INTELLIGENCE_ACCEPTANCE_REPORT.md'
@contextmanager
def cwd():
    old=os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:yield
        finally:os.chdir(old)
def check(module,name,fn):
    try:fn();return {'module':module,'test':name,'passed':True,'detail':''}
    except Exception as e:return {'module':module,'test':name,'passed':False,'detail':str(e)}
def write_hist(rows):
    os.makedirs('data/history',exist_ok=True)
    with open('data/history/wnba_model_history.jsonl','w') as f:
        for r in rows:f.write(json.dumps(r)+'\n')
def tests():
    out=[]
    def m21():
        with cwd():
            write_hist([{'outcome':'WIN' if i%2==0 else 'LOSS','simulation_probability':.6+i%3*.05} for i in range(60)])
            r=calibration.build('2099-01-01');assert r['summary']['samples']==60;assert 0<=r['summary']['brier_score']<=1;assert 0<=r['summary']['ece']<=1
    out.append(check('M21','bounded calibration metrics',m21))
    def m22():
        with cwd():
            write_hist([{'outcome':'WIN' if i>29 else 'LOSS','edge_pct':i,'ev_pct':i/2,'market_move':i%4,'simulation_probability':.55+i/1000} for i in range(60)])
            r=importance.build('2099-01-01');assert len(r['features'])>=5;assert all(0<=x['importance']<=1 for x in r['features']);assert len(r['top_features'])<=5
    out.append(check('M22','importance ranking and drift schema',m22))
    def m23():
        with cwd():
            write_hist([{'outcome':'WIN' if i%3 else 'LOSS','edge_pct':5+i%10,'ev_pct':3+i%8,'market_move':i%5,'simulation_probability':.55+i%10/100} for i in range(90)])
            r=optimizer.build('2099-01-01');assert abs(sum(r['production_weights'])-1)<.02;assert r['policy']['rollback_safe'];assert r['summary']['samples']==90
    out.append(check('M23','champion challenger safety',m23))
    def m24():
        with cwd():
            os.makedirs('data/dashboard',exist_ok=True)
            json.dump({'status':'waiting_for_actuals'},open('data/dashboard/wnba_results_grading.json','w'));json.dump({'status':'ok'},open('data/dashboard/wnba_clv_summary.json','w'));json.dump({'status':'ok','safety':{'rollback_on_validation_drop':True}},open('data/dashboard/wnba_self_learning.json','w'));json.dump({'status':'ok','summary':{'samples':0}},open('data/dashboard/wnba_model_calibration.json','w'));json.dump({'status':'ok','summary':{'graded_samples':0}},open('data/dashboard/wnba_feature_importance.json','w'));json.dump({'status':'ok','policy':{'rollback_safe':True},'summary':{'promoted':False}},open('data/dashboard/wnba_hyperparameter_optimizer.json','w'))
            r=retraining.build('2099-01-01');assert r['status']=='ok';assert r['decision']=='HOLD';assert not r['summary']['production_update_applied']
    out.append(check('M24','safe hold without enough data',m24))
    def m25():
        with cwd():
            os.makedirs('data/dashboard',exist_ok=True)
            json.dump({'top_decisions':[{'player':'P','game':'A @ B','stat':'PTS','signal':'OVER','line':10,'edge_pct':10,'ev_pct':8,'simulation_probability':.65,'market_move':1,'injury_status':'ACTIVE','book_count':3,'guardrail_failures':[]}]},open('data/dashboard/wnba_decision_engine_final.json','w'));json.dump({'summary':{'calibration_offset':0}},open('data/dashboard/wnba_model_calibration.json','w'));json.dump({'production_weights':[.35,.25,.25,.15]},open('data/dashboard/wnba_hyperparameter_optimizer.json','w'));json.dump({'engine_weights':{'Projection EV':.2}},open('data/dashboard/wnba_self_learning.json','w'))
            row=ensemble.build('2099-01-01')['top_decisions'][0];assert 0<=row['ensemble_score']<=100;assert 0<=row['calibrated_confidence']<=100;assert row['ensemble_action'] in {'BET','LEAN','WATCH','PASS'}
    out.append(check('M25','bounded ensemble decision contract',m25))
    return out
def main():
    items=tests();failed=[x for x in items if not x['passed']];mods={}
    for x in items:mods.setdefault(x['module'],[]).append(x)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'green' if not failed else 'red','summary':{'tests':len(items),'passed':len(items)-len(failed),'failed':len(failed)},'modules':{k:{'passed':all(x['passed'] for x in v),'tests':v} for k,v in mods.items()},'tests':items}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,indent=2)+'\n');REPORT.parent.mkdir(parents=True,exist_ok=True);REPORT.write_text('# V4 M21–M25 Intelligence Acceptance\n\n'+'\n'.join(f"- {'PASS' if x['passed'] else 'FAIL'} — {x['module']} — {x['test']} {x['detail']}" for x in items)+'\n')
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
