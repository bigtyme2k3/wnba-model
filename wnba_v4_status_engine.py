from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
CONFIG=Path('config/v4_modules.json');DASH=Path('data/dashboard');OUT=DASH/'wnba_v4_status.json'
def load_json(path,default):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default
def file_rows(path):
    p=Path(path)
    if not p.exists():return 0
    try:
        if p.suffix=='.json':
            d=load_json(p,{})
            if isinstance(d,list):return len(d)
            if isinstance(d,dict):
                for k in ('markets','props','games','players','events','matchups','projections','decisions','best_bets','rows','top_decisions','recommended_card','allocation','records','reasoning'):
                    if isinstance(d.get(k),list):return len(d[k])
                return 1 if d else 0
        if p.suffix=='.csv':return max(0,sum(1 for _ in p.open(encoding='utf-8'))-1)
        return 1
    except Exception:return 0
def valid_zero_output(path):
    if not path or not Path(path).exists():return False
    d=load_json(Path(path),{});s=d.get('summary',{}) if isinstance(d,dict) else {}
    if path.endswith('wnba_portfolio_optimizer_v2.json'):return s.get('qualified_candidates')==0 and s.get('card_size')==0 and d.get('recommended_card')==[]
    if path.endswith('wnba_risk_allocation.json'):return s.get('card_size')==0 and d.get('allocation')==[]
    if path.endswith('wnba_play_by_play_layer.json'):return s.get('games')==0 and d.get('status')=='ok'
    if path.endswith('wnba_clv_summary.json'):return d.get('status')=='ok' and s.get('graded_clv',0)==0
    if path.endswith('wnba_results_grading.json'):return d.get('status') in {'ok','waiting_for_actuals'}
    if path.endswith('wnba_reasoning_layer.json'):return d.get('status')=='ok'
    return False
def infer_runtime_status(m):
    owner=m.get('owner_file','');exists=Path(owner).exists() if owner else False
    outputs={'wnba_sportsbook_consensus.py':'data/dashboard/wnba_sportsbook_consensus.json','wnba_player_intelligence.py':'data/raw/wnba_players_live.json','wnba_play_by_play_layer.py':'data/dashboard/wnba_play_by_play_layer.json','wnba_matchup_intelligence.py':'data/dashboard/wnba_matchup_intelligence.json','wnba_projection_ai.py':'data/dashboard/wnba_projection_ai.json','wnba_game_market_model.py':'data/dashboard/wnba_game_market_model.json','player_points.py':'data/dashboard/wnba_master.json','wnba_decision_engine_final.py':'data/dashboard/wnba_decision_engine_final.json','wnba_portfolio_optimizer_v2.py':'data/dashboard/wnba_portfolio_optimizer_v2.json','wnba_risk_allocation.py':'data/dashboard/wnba_risk_allocation.json','wnba_closing_line_tracker.py':'data/dashboard/wnba_clv_summary.json','wnba_results_grader.py':'data/dashboard/wnba_results_grading.json','wnba_self_learning.py':'data/dashboard/wnba_self_learning.json','wnba_reasoning_layer.py':'data/dashboard/wnba_reasoning_layer.json','patch_dashboard_navigation_v2.py':'docs/index.html','wnba_master_source_builder.py':'data/dashboard/wnba_master.json','odds_source_manager.py':'data/raw/odds_source_status.json','wnba_stats_fallback_from_boxscores.py':'data/raw/wnba_stats_fallback_status.json','config/source_registry.json':'config/source_registry.json'}
    output=outputs.get(owner,'');count=file_rows(output) if output else 0;planned=m.get('status')=='planned';runtime='active' if exists and (count>0 or valid_zero_output(output)) else 'wired' if exists and not planned else 'scaffolded' if exists else 'missing'
    return {'owner_exists':exists,'output':output,'rows':count,'runtime_status':runtime,'valid_zero_output':valid_zero_output(output)}
def output_qa_modules(code):
    mp={'DATE_MISMATCH':{'M02','M20'},'BAD_PROBABILITY':{'M09','M10','M11','M12','M13'},'BAD_SCORE':{'M08','M09','M10','M11','M12','M13','M19'},'IMPLIED_PROBABILITY_MISMATCH':{'M03','M04','M13'},'UNSUPPORTED_BOOK':{'M03','M04'},'UNSUPPORTED_MARKET':{'M10','M13'},'INELIGIBLE_BET':{'M13','M14','M15'},'BET_WITH_FAILURES':{'M13','M14','M15'},'ELIGIBLE_NOT_BET':{'M13','M14'},'BET_EV_OUT_OF_RANGE':{'M13'},'BET_PROBABILITY_TOO_LOW':{'M09','M13'},'BET_HISTORY_TOO_LOW':{'M05','M10','M13'},'BET_BOOK_COUNT_TOO_LOW':{'M03','M04','M13'},'DECISION_COUNT_MISMATCH':{'M13','M20'},'BET_COUNT_MISMATCH':{'M13','M14','M20'},'DUPLICATE_DECISION':{'M13'},'PORTFOLIO_CAP_EXCEEDED':{'M14','M15'},'PORTFOLIO_PLAYER_DUPLICATION':{'M14','M15'},'PORTFOLIO_GAME_CONCENTRATION':{'M14','M15'},'STAKE_EXCEEDS_BANKROLL':{'M15'},'PORTFOLIO_SILENT_FAILURE':{'M14'},'PORTFOLIO_WITHOUT_QUALIFIED_BETS':{'M13','M14'}}
    return mp.get(code,set())
def aggregate(items):
    e=Counter();w=Counter()
    for x in items:(e if x.get('level')=='error' else w)[f"{x.get('code')}: {x.get('message')}"]+=1
    render=lambda c:[f'{t} ×{n}' if n>1 else t for t,n in c.items()]
    return render(e),render(w)
def acceptance_for(mid,down,foundation,feedback):
    if mid in {'M07','M08','M09'}:v=foundation.get('modules',{}).get(mid)
    elif mid in {'M16','M17','M18','M19'}:v=feedback.get('modules',{}).get(mid)
    else:v=down.get('modules',{}).get('M11/M12' if mid in {'M11','M12'} else mid)
    return v if isinstance(v,dict) else None
def main():
    manifest=load_json(CONFIG,{'modules':[]});repo=load_json(DASH/'wnba_v4_qa.json',{});outqa=load_json(DASH/'wnba_v4_output_qa.json',{});down=load_json(DASH/'wnba_v4_acceptance.json',{});foundation=load_json(DASH/'wnba_v4_foundation_acceptance.json',{});feedback=load_json(DASH/'wnba_v4_feedback_acceptance.json',{})
    byid={m.get('id'):m for m in repo.get('modules',[]) if isinstance(m,dict)};findings=outqa.get('findings',[]) if isinstance(outqa,dict) else [];modules=[];required={'M07','M08','M09','M11','M12','M13','M14','M15','M16','M17','M18','M19'}
    for m in manifest.get('modules',[]):
        runtime=infer_runtime_status(m);ri=byid.get(m.get('id'),{});block,warn=aggregate([x for x in findings if m.get('id') in output_qa_modules(str(x.get('code')))]);acc=acceptance_for(m.get('id'),down,foundation,feedback)
        if not runtime['owner_exists']:block.append('Owner file missing')
        if ri.get('syntax_ok') is False:block.append('Owner file has a Python syntax error')
        if m.get('id') in required and not acc:block.append('Production acceptance report missing')
        elif m.get('id') in required and not acc.get('passed'):block.append('Production acceptance tests failed')
        score=max(0,int(ri.get('qa_score',100))-min(60,25*len(block))-min(25,5*len(warn)));grade='red' if block or score<60 else 'yellow' if warn or score<90 else 'green';ready=m.get('status') in {'active','validated'} and runtime['runtime_status']=='active' and grade=='green';effective='blocked' if grade=='red' else 'validated' if ready else 'attention' if grade=='yellow' else runtime['runtime_status']
        modules.append({**m,**runtime,'qa_score':score,'qa_grade':grade,'effective_status':effective,'production_ready':ready,'acceptance':acc,'blockers':block,'warnings':warn})
    mc={k:sum(m.get('status')==k for m in modules) for k in ('planned','partial','active','validated')};rc={k:sum(m.get('runtime_status')==k for m in modules) for k in ('active','wired','scaffolded','missing')};qc={k:sum(m.get('qa_grade')==k for m in modules) for k in ('green','yellow','red')};ready=sum(m['production_ready'] for m in modules);overall='red' if qc['red'] else 'yellow' if qc['yellow'] else 'green'
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'version':manifest.get('version','4.0'),'mission':manifest.get('mission',''),'qa':{'overall_status':overall,'repository_qa_status':repo.get('status','unknown'),'output_qa_status':outqa.get('status','unknown'),'acceptance_status':down.get('status','missing'),'foundation_acceptance_status':foundation.get('status','missing'),'feedback_acceptance_status':feedback.get('status','missing'),'output_summary':outqa.get('summary',{}),'acceptance_summary':down.get('summary',{}),'foundation_acceptance_summary':foundation.get('summary',{}),'feedback_acceptance_summary':feedback.get('summary',{})},'summary':{'modules':len(modules),'completion_pct':round(ready/max(len(modules),1)*100,1),'production_ready':ready,'manifest_status_counts':mc,'runtime_status_counts':rc,'qa_status_counts':qc,'release_blockers':sum(len(m['blockers']) for m in modules),'warnings':sum(len(m['warnings']) for m in modules)},'modules':modules,'release_blockers':[{'id':m['id'],'module':m['name'],'items':m['blockers']} for m in modules if m['blockers']],'next_build_order':[m for m in modules if not m['production_ready']][:8]}
    DASH.mkdir(parents=True,exist_ok=True);json.dump(result,OUT.open('w',encoding='utf-8'),indent=2,allow_nan=False);print('WNBA V4 status:',result['summary'])
if __name__=='__main__':main()
