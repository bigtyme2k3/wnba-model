"""Deterministic production acceptance tests for M16-M19."""
from __future__ import annotations
import json,os,tempfile
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
import wnba_closing_line_tracker as clv
import wnba_results_grader as grader
import wnba_self_learning as learning
import wnba_reasoning_layer as reasoning
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'data/dashboard/wnba_v4_feedback_acceptance.json'; REPORT=ROOT/'docs/V4_FEEDBACK_ACCEPTANCE_REPORT.md'
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
def tests():
    out=[]
    def clv_math():
        assert clv.line_clv(20,21,'OVER')==1
        assert clv.line_clv(20,19,'UNDER')==1
        assert abs(clv.implied(-110)-110/210)<1e-9
    out.append(check('M16','line and price CLV math',clv_math))
    def grade_math():
        assert grader.grade('OVER',21,20)=='WIN';assert grader.grade('UNDER',21,20)=='LOSS';assert grader.grade('OVER',20,20)=='PUSH';assert grader.grade('X',20,20)=='PUSH'
        assert round(grader.profit('WIN',10,-110),2)==9.09;assert grader.profit('LOSS',10,-110)==-10
    out.append(check('M17','grading and P/L math',grade_math))
    def no_duplicate():
        with cwd():
            os.makedirs('data/history',exist_ok=True);os.makedirs('data/raw',exist_ok=True)
            open('data/history/wnba_model_history.jsonl','w').write(json.dumps({'date':'2099-01-01','player':'P','stat':'PTS','signal':'OVER','line':10,'outcome':'WIN','actual':12})+'\n')
            pd.DataFrame([{'player':'P','pts':12}]).to_csv('data/raw/player_results_2099-01-01.csv',index=False)
            r=grader.build('2099-01-01');assert r['summary']['graded_this_run']==0
    out.append(check('M17','duplicate grading protection',no_duplicate))
    def safe_learning():
        with cwd():
            os.makedirs('data/history',exist_ok=True)
            open('data/history/wnba_model_history.jsonl','w').write(json.dumps({'outcome':'WIN','actual':12})+'\n')
            r=learning.build('2099-01-01');assert not r['update_applied'];assert abs(sum(r['engine_weights'].values())-1)<0.01;assert all(0.04<=v<=0.31 for v in r['engine_weights'].values())
    out.append(check('M18','minimum sample and bounded weights',safe_learning))
    def explanation():
        with cwd():
            os.makedirs('data/warehouse',exist_ok=True)
            json.dump({'top_decisions':[{'player':'P','game':'A @ B','stat':'PTS','signal':'OVER','line':10,'final_action':'LEAN','final_score':72,'edge_pct':8,'ev_pct':5,'simulation_probability':.6,'guardrail_failures':[],'selection_failures':['score below threshold'],'injury_status':'ACTIVE'}]},open('data/warehouse/wnba_decision_engine_final.json','w'))
            row=reasoning.build('2099-01-01')['reasoning'][0];assert row['action']=='LEAN';assert row['summary'];assert row['selection_failures'];assert row['strongest_positive_factors']
    out.append(check('M19','complete action explanation',explanation))
    return out
def main():
    items=tests();failed=[x for x in items if not x['passed']];mods={}
    for x in items:mods.setdefault(x['module'],[]).append(x)
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'green' if not failed else 'red','summary':{'tests':len(items),'passed':len(items)-len(failed),'failed':len(failed)},'modules':{k:{'passed':all(x['passed'] for x in v),'tests':v} for k,v in mods.items()},'tests':items}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,indent=2)+'\n');REPORT.parent.mkdir(parents=True,exist_ok=True);REPORT.write_text('# V4 M16–M19 Feedback Acceptance\n\n'+ '\n'.join(f"- {'PASS' if x['passed'] else 'FAIL'} — {x['module']} — {x['test']} {x['detail']}" for x in items)+'\n')
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
