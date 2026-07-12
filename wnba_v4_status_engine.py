from __future__ import annotations
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
CONFIG=Path('config/v4_modules.json');DASH=Path('data/dashboard');OUT=DASH/'wnba_v4_status.json'
def load(path,d):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else d
    except Exception:return d
def rows(path):
    p=Path(path)
    if not p.exists():return 0
    try:
        if p.suffix=='.json':
            x=load(p,{})
            if isinstance(x,list):return len(x)
            if isinstance(x,dict):
                for k in ('markets','props','games','players','events','matchups','projections','decisions','best_bets','rows','top_decisions','recommended_card','allocation','records','reasoning','features','buckets'):
                    if isinstance(x.get(k),list):return len(x[k])
                return 1 if x else 0
        if p.suffix=='.csv':return max(0,sum(1 for _ in p.open())-1)
        return 1
    except Exception:return 0
def zero_ok(path):
    if not path or not Path(path).exists():return False
    d=load(Path(path),{});s=d.get('summary',{}) if isinstance(d,dict) else {}
    if path.endswith('wnba_portfolio_optimizer_v2.json'):return s.get('card_size')==0
    if path.endswith('wnba_risk_allocation.json'):return s.get('card_size')==0
    if path.endswith('wnba_play_by_play_layer.json'):return d.get('status')=='ok'
    if path.endswith('wnba_results_grading.json'):return d.get('status') in {'ok','waiting_for_actuals'}
    return d.get('status')=='ok'
OUTPUTS={'config/source_registry.json':'config/source_registry.json','wnba_master_source_builder.py':'data/dashboard/wnba_master.json','odds_source_manager.py':'data/raw/odds_source_status.json','wnba_sportsbook_consensus.py':'data/dashboard/wnba_sportsbook_consensus.json','wnba_player_intelligence.py':'data/raw/wnba_players_live.json','wnba_stats_fallback_from_boxscores.py':'data/raw/wnba_stats_fallback_status.json','wnba_play_by_play_layer.py':'data/dashboard/wnba_play_by_play_layer.json','wnba_matchup_intelligence.py':'data/dashboard/wnba_matchup_intelligence.json','wnba_projection_ai.py':'data/dashboard/wnba_projection_ai.json','player_points.py':'data/dashboard/wnba_master.json','wnba_game_market_model.py':'data/dashboard/wnba_game_market_model.json','wnba_decision_engine_final.py':'data/dashboard/wnba_decision_engine_final.json','wnba_portfolio_optimizer_v2.py':'data/dashboard/wnba_portfolio_optimizer_v2.json','wnba_risk_allocation.py':'data/dashboard/wnba_risk_allocation.json','wnba_closing_line_tracker.py':'data/dashboard/wnba_clv_summary.json','wnba_results_grader.py':'data/dashboard/wnba_results_grading.json','wnba_self_learning.py':'data/dashboard/wnba_self_learning.json','wnba_reasoning_layer.py':'data/dashboard/wnba_reasoning_layer.json','patch_dashboard_navigation_v2.py':'docs/index.html','wnba_model_calibration.py':'data/dashboard/wnba_model_calibration.json','wnba_feature_importance.py':'data/dashboard/wnba_feature_importance.json','wnba_hyperparameter_optimizer.py':'data/dashboard/wnba_hyperparameter_optimizer.json','wnba_daily_retraining.py':'data/dashboard/wnba_daily_retraining.json','wnba_ensemble_learning.py':'data/dashboard/wnba_ensemble_learning.json'}
def runtime(m):
    owner=m.get('owner_file','');exists=Path(owner).exists();out=OUTPUTS.get(owner,'');n=rows(out) if out else 0;state='active' if exists and (n>0 or zero_ok(out)) else 'wired' if exists and m.get('status')!='planned' else 'scaffolded' if exists else 'missing';return {'owner_exists':exists,'output':out,'rows':n,'runtime_status':state,'valid_zero_output':zero_ok(out)}
def acceptance(mid,down,foundation,feedback,intelligence):
    if mid in {'M07','M08','M09'}:v=foundation.get('modules',{}).get(mid)
    elif mid in {'M16','M17','M18','M19'}:v=feedback.get('modules',{}).get(mid)
    elif mid in {'M21','M22','M23','M24','M25'}:v=intelligence.get('modules',{}).get(mid)
    else:v=down.get('modules',{}).get('M11/M12' if mid in {'M11','M12'} else mid)
    return v if isinstance(v,dict) else None
def main():
    manifest=load(CONFIG,{'modules':[]});repo=load(DASH/'wnba_v4_qa.json',{});outqa=load(DASH/'wnba_v4_output_qa.json',{});down=load(DASH/'wnba_v4_acceptance.json',{});foundation=load(DASH/'wnba_v4_foundation_acceptance.json',{});feedback=load(DASH/'wnba_v4_feedback_acceptance.json',{});intel=load(DASH/'wnba_v4_intelligence_acceptance.json',{});byid={m.get('id'):m for m in repo.get('modules',[]) if isinstance(m,dict)};required={'M07','M08','M09','M11','M12','M13','M14','M15','M16','M17','M18','M19','M21','M22','M23','M24','M25'};mods=[]
    for m in manifest.get('modules',[]):
        rt=runtime(m);ri=byid.get(m.get('id'),{});acc=acceptance(m.get('id'),down,foundation,feedback,intel);block=[];warn=[]
        if not rt['owner_exists']:block.append('Owner file missing')
        if ri.get('syntax_ok') is False:block.append('Owner file has a Python syntax error')
        if m.get('id') in required and not acc:block.append('Production acceptance report missing')
        elif m.get('id') in required and not acc.get('passed'):block.append('Production acceptance tests failed')
        score=max(0,int(ri.get('qa_score',100))-25*len(block));grade='red' if block or score<60 else 'green';ready=m.get('status') in {'active','validated'} and rt['runtime_status']=='active' and grade=='green';mods.append({**m,**rt,'qa_score':score,'qa_grade':grade,'effective_status':'validated' if ready else 'blocked' if grade=='red' else rt['runtime_status'],'production_ready':ready,'acceptance':acc,'blockers':block,'warnings':warn})
    ready=sum(m['production_ready'] for m in mods);qc={k:sum(m['qa_grade']==k for m in mods) for k in ('green','yellow','red')};mc={k:sum(m.get('status')==k for m in mods) for k in ('planned','partial','active','validated')};rc={k:sum(m.get('runtime_status')==k for m in mods) for k in ('active','wired','scaffolded','missing')};overall='red' if qc['red'] else 'yellow' if qc['yellow'] else 'green'
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'version':manifest.get('version','4.0'),'mission':manifest.get('mission',''),'qa':{'overall_status':overall,'repository_qa_status':repo.get('status','unknown'),'output_qa_status':outqa.get('status','unknown'),'acceptance_status':down.get('status','missing'),'foundation_acceptance_status':foundation.get('status','missing'),'feedback_acceptance_status':feedback.get('status','missing'),'intelligence_acceptance_status':intel.get('status','missing'),'output_summary':outqa.get('summary',{}),'acceptance_summary':down.get('summary',{}),'foundation_acceptance_summary':foundation.get('summary',{}),'feedback_acceptance_summary':feedback.get('summary',{}),'intelligence_acceptance_summary':intel.get('summary',{})},'summary':{'modules':len(mods),'completion_pct':round(ready/max(1,len(mods))*100,1),'production_ready':ready,'manifest_status_counts':mc,'runtime_status_counts':rc,'qa_status_counts':qc,'release_blockers':sum(len(m['blockers']) for m in mods),'warnings':0},'modules':mods,'release_blockers':[{'id':m['id'],'module':m['name'],'items':m['blockers']} for m in mods if m['blockers']],'next_build_order':[m for m in mods if not m['production_ready']][:8]}
    DASH.mkdir(parents=True,exist_ok=True);json.dump(result,OUT.open('w',encoding='utf-8'),indent=2,allow_nan=False);print('WNBA V4 status:',result['summary'])
if __name__=='__main__':main()
