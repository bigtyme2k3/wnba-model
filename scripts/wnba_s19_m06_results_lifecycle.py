from __future__ import annotations

import argparse, json, math, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

DASH=Path('data/dashboard')
HISTORY=Path('data/history/wnba_model_history.jsonl')
M04=DASH/'wnba_s19_m04_decision_contract.json'
M05=DASH/'wnba_s19_m05_dashboard_health.json'
OUT=DASH/'wnba_s19_m06_results_lifecycle.json'
AUDIT=DASH/'wnba_s19_m06_results_lifecycle_audit.json'
CURRENT_MODEL_VERSION='sprint19_player_props_v5_m02'


def load(path, default):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:return default


def sf(v):
    try:
        n=float(v); return n if math.isfinite(n) else None
    except Exception:return None


def read_history():
    rows=[]
    if HISTORY.exists():
        for line in HISTORY.read_text(encoding='utf-8').splitlines():
            try:
                r=json.loads(line)
                if isinstance(r,dict):rows.append(r)
            except Exception:pass
    return rows


def choose_market(row):
    rec=str(row.get('recommendation') or 'PASS').upper()
    if rec=='OVER': return row.get('best_over_book'), sf(row.get('best_over_price'))
    if rec=='UNDER': return row.get('best_under_book'), sf(row.get('best_under_price'))
    return None,None


def history_key(target,row):
    return '|'.join(str(x or '') for x in (target,row.get('player'),row.get('game'),row.get('stat'),row.get('line'),row.get('recommendation')))


def model_version(row):
    stamped=str(row.get('model_version') or '').strip()
    if stamped:return stamped
    source=str(row.get('prediction_source') or '')
    return CURRENT_MODEL_VERSION if source.startswith('exact_current_slate_sportsbook_props_plus_player_points_v5') else 'legacy_unversioned'


def recommendation_scope(row):
    signal=str(row.get('signal') or row.get('recommendation') or '').upper()
    return 'RECOMMENDED' if bool(row.get('eligible_for_bet')) and signal in {'OVER','UNDER'} else 'RESEARCH_ONLY'


def result_summary(rows):
    wins=sum(r.get('outcome')=='WIN' for r in rows);losses=sum(r.get('outcome')=='LOSS' for r in rows)
    pushes=sum(r.get('outcome')=='PUSH' for r in rows);voids=sum(r.get('outcome')=='VOID' for r in rows)
    pending=sum(r.get('outcome') not in {'WIN','LOSS','PUSH','VOID'} for r in rows);decisions=wins+losses
    return {'rows':len(rows),'wins':wins,'losses':losses,'pushes':pushes,'voids':voids,'pending':pending,'decisions':decisions,'hit_rate':round(wins/decisions,4) if decisions else None}


def grouped(rows,field):
    groups={}
    for row in rows:groups.setdefault(str(row.get(field) or 'UNKNOWN'),[]).append(row)
    return [{'group':key,**result_summary(value)} for key,value in sorted(groups.items())]


def build(target):
    m04=load(M04,{})
    m05=load(M05,{})
    if m04.get('status')!='READY' or str(m04.get('target_date') or '')[:10]!=target:
        raise SystemExit(f'M06 requires current READY M04 contract for {target}')
    if m05.get('status')!='READY' or str(m05.get('target_date') or '')[:10]!=target:
        raise SystemExit(f'M06 requires current READY M05 health for {target}')

    props=m04.get('player_props') or []
    if not props: raise SystemExit('M06 refuses to archive an empty Player Props contract')
    if any(str(r.get('target_date') or target)[:10]!=target for r in props):
        raise SystemExit('M06 found off-date Player Props')
    if any(str(r.get('injury_status') or '').upper() in {'OUT','DOUBTFUL'} and r.get('eligible') for r in props):
        raise SystemExit('M06 found actionable unavailable player')

    history=read_history(); seen={r.get('history_key') for r in history if r.get('history_key')}
    now=datetime.now(timezone.utc).isoformat(); additions=[]
    for row in props:
        key=history_key(target,row)
        if key in seen: continue
        book,odds=choose_market(row)
        rec=str(row.get('recommendation') or 'PASS').upper()
        additions.append({
            'history_key':key,'date':target,'captured_at_utc':now,
            'player':row.get('player'),'team':row.get('team'),'game':row.get('game'),'stat':row.get('stat'),
            'line':sf(row.get('line')),'pred':sf(row.get('model_projection')),'signal':rec,'edge':sf(row.get('edge')),
            'confidence':sf(row.get('confidence')),'recommendation':rec,'final_action':rec,
            'eligible_for_bet':bool(row.get('eligible')),'sportsbook':book,'american_odds':odds,
            'injury_status':row.get('injury_status'),'injury_adjusted':bool(row.get('injury_adjusted')),
            'injury_projection_factor':sf(row.get('injury_projection_factor')),
            'projected_minutes':sf(row.get('projected_minutes')),'minutes_delta':sf(row.get('minutes_delta')),
            'prediction_source':row.get('prediction_source'),'outcome':None,'actual':None,'closing_line':None,'clv':None,
            'model_version':CURRENT_MODEL_VERSION,'result_scope':'RECOMMENDED' if bool(row.get('eligible')) and rec in {'OVER','UNDER'} else 'RESEARCH_ONLY',
            'stake':0.0,'recommended_stake':0.0,
        })
        seen.add(key)

    HISTORY.parent.mkdir(parents=True,exist_ok=True)
    if additions:
        with HISTORY.open('a',encoding='utf-8') as f:
            for r in additions:f.write(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n')

    # Current-slate predictions are archived now. Existing deterministic grading settles them later
    # when completed-game actuals are available; do not manufacture same-day finals.
    edge=subprocess.run([sys.executable,'wnba_edge_database.py','--date',target],check=True,capture_output=True,text=True)
    history_after=read_history(); target_rows=[r for r in history_after if r.get('date')==target]
    keys=[r.get('history_key') for r in target_rows if r.get('history_key')]
    duplicate_keys=len(keys)-len(set(keys))
    if duplicate_keys: raise SystemExit(f'M06 history duplicate keys detected: {duplicate_keys}')

    edge_report=load(DASH/'wnba_edge_database.json',{})
    versioned=[]
    for row in history_after:
        item=dict(row);item['model_version']=model_version(item);item['result_scope']=recommendation_scope(item);versioned.append(item)
    current=[r for r in versioned if r['model_version']==CURRENT_MODEL_VERSION]
    current_recommended=[r for r in current if r['result_scope']=='RECOMMENDED']
    legacy=[r for r in versioned if r['model_version']!=CURRENT_MODEL_VERSION]
    target_current=[r for r in current if str(r.get('date') or '')[:10]==target]
    target_recommended=[r for r in target_current if r['result_scope']=='RECOMMENDED']
    recent_results=sorted([r for r in current_recommended if r.get('outcome') in {'WIN','LOSS','PUSH','VOID'}],key=lambda r:(str(r.get('date') or ''),str(r.get('graded_at_utc') or '')),reverse=True)[:100]
    current_quality={
        'negative_projections':sum((sf(r.get('pred')) or 0)<0 for r in current),
        'invalid_american_odds':sum(sf(r.get('american_odds')) is not None and -100 < sf(r.get('american_odds')) < 100 for r in current),
        'missing_sportsbook':sum(not str(r.get('sportsbook') or '').strip() for r in current),
        'zero_stake_rows':sum((sf(r.get('stake')) or 0)==0 for r in current),
    }
    payload={
        'generated_at_utc':now,'target_date':target,'schema_version':'sprint19-m06-results-lifecycle-v2','status':'READY',
        'current_model_version':CURRENT_MODEL_VERSION,
        'source_policy':{
            'prediction_source':'wnba_s19_m04_decision_contract.json',
            'health_source':'wnba_s19_m05_dashboard_health.json',
            'history_source':'data/history/wnba_model_history.jsonl',
            'grader':'wnba_results_grader.py existing deterministic grader',
            'edge_database':'wnba_edge_database.py existing Sprint 19 edge database',
            'same_day_final_results_inferred':False,
        },
        'summary':{
            'contract_player_props':len(props),'added_history_records':len(additions),'target_history_records':len(target_rows),
            'duplicate_history_keys':duplicate_keys,'target_edge_records':int(edge_report.get('target_records') or 0),
            'open_edge_records':int(edge_report.get('open_records') or 0),'settled_edge_records':int(edge_report.get('settled_records') or 0),
            'results_state':'ARCHIVED_WAITING_FOR_COMPLETED_ACTUALS',
        },
        'current_model':{
            'label':'Current model recommendations','scope':'eligible OVER/UNDER recommendations only; research candidates excluded','performance':result_summary(current_recommended),
            'target':{'date':target,'archived_candidates':len(target_current),'recommended':result_summary(target_recommended)},
            'by_stat':grouped(current_recommended,'stat'),'by_side':grouped(current_recommended,'signal'),'by_date':grouped(current_recommended,'date'),
            'recent_results':recent_results,'data_quality':current_quality,'profit_loss_status':'UNAVAILABLE — archived stakes are zero; results are model recommendations, not recorded wagers',
        },
        'legacy_reference':{'label':'Legacy models — historical reference only','included_in_current_performance':False,'performance':result_summary(legacy)},
        'research_archive':{'label':'Research and lifecycle diagnostics','all_history_rows':len(versioned),'current_research_rows':sum(r['result_scope']=='RESEARCH_ONLY' for r in current),'edge_database_total':int(edge_report.get('total_records') or 0),'edge_database_open':int(edge_report.get('open_records') or 0),'edge_database_settled':int(edge_report.get('settled_records') or 0)},
    }
    OUT.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    audit={
        'generated_at_utc':now,'target_date':target,'status':'READY','module':'SPRINT19-M06',
        'contract_player_props':len(props),'added_history_records':len(additions),'target_history_records':len(target_rows),
        'duplicate_history_keys':duplicate_keys,'target_edge_records':int(edge_report.get('target_records') or 0),
        'same_day_final_results_inferred':False,'existing_grader_reused':True,'existing_edge_database_reused':True,
        'history_persistence_required':True,'results_state':'ARCHIVED_WAITING_FOR_COMPLETED_ACTUALS',
    }
    AUDIT.write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print('SPRINT19_M06_RESULTS_LIFECYCLE',json.dumps(audit))
    return payload


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',required=True); args=ap.parse_args(); build(args.date)

if __name__=='__main__': main()
