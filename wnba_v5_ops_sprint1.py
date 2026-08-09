"""WNBA V5 Operations Sprint 1.

Builds the operational shadow layer on top of M10-M12 without changing production
behavior. It publishes: shadow monitor, daily report, weekly research audit,
promotion dashboard, and a sprint status artifact. Missing optional V4 forward
comparison data is reported explicitly rather than fabricated.
"""
from __future__ import annotations
import csv, json, math
from datetime import datetime, timezone
from pathlib import Path

DASH=Path('data/dashboard')
M05=DASH/'wnba_v5_m05_report.json'
M06=DASH/'wnba_v5_m06_report.json'
M10=DASH/'wnba_v5_m10_report.json'
M11=DASH/'wnba_v5_m11_report.json'
M12=DASH/'wnba_v5_m12_report.json'
HEALTH=DASH/'wnba_alt_archive_health.json'
FWD=DASH/'wnba_v5_forward_validation.csv'

OUT_MON=DASH/'wnba_v5_shadow_monitor.json'
OUT_DAILY=DASH/'wnba_v5_daily_shadow_report.json'
OUT_WEEKLY=DASH/'wnba_v5_weekly_research_audit.json'
OUT_PROMO=DASH/'wnba_v5_promotion_dashboard.json'
OUT_STATUS=DASH/'wnba_v5_ops_sprint1_status.json'


def load(path, default=None):
    try:
        return json.load(path.open(encoding='utf-8')) if path.exists() else ({} if default is None else default)
    except Exception:
        return {} if default is None else default

def num(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None

def pct(n,d): return round(100*n/d,2) if d else 0.0

def read_forward():
    if not FWD.exists(): return []
    try:return list(csv.DictReader(FWD.open(encoding='utf-8-sig',newline='')))
    except Exception:return []

def main():
    now=datetime.now(timezone.utc).isoformat()
    m05,m06,m10,m11,m12,health=[load(p) for p in (M05,M06,M10,M11,M12,HEALTH)]
    metrics=m12.get('metrics') or {}
    gate=m12.get('promotion_gate') or {}
    fwd=read_forward()
    champion=m05.get('research_champion') or m12.get('research_champion') or 'UNKNOWN'
    forward=int(metrics.get('forward_predictions') or len(fwd) or 0)
    graded=int(metrics.get('binary_graded_predictions') or 0)
    pending=int(metrics.get('pending_predictions') or max(0,forward-graded))
    clv=num(gate.get('explicit_clv_coverage_pct'))
    if clv is None: clv=num(m06.get('explicit_clv_coverage_pct')) or 0.0
    archive_ok=health.get('status')=='HEALTHY_LOCKED'
    pipeline_ok=(m10.get('status') in {'READY_SHADOW','STANDBY_NO_LIVE_V5_SCORES'} and m11.get('status') in {'READY_SHADOW','WAITING_FOR_CURRENT_BOARD'})
    brier=num(metrics.get('v5_brier')); market_brier=num(metrics.get('market_brier'))
    roi=num(metrics.get('positive_edge_roi'))
    brier_beats_market=(brier is not None and market_brier is not None and brier < market_brier)

    blockers=[]
    if graded<300: blockers.append(f'forward graded sample {graded}/300')
    if clv<60: blockers.append(f'explicit CLV coverage {clv:.2f}%/60%')
    if not archive_ok: blockers.append('archive health not HEALTHY_LOCKED')
    if not pipeline_ok: blockers.append('live shadow pipeline not healthy')
    if not brier_beats_market: blockers.append('forward V5 Brier has not yet beaten market')
    if roi is not None and roi<=0: blockers.append('positive-edge forward ROI is not positive')
    ready=(not blockers and graded>=300 and clv>=60)
    if ready: state='PRODUCTION_READY'
    elif graded>=225 and clv>=45 and archive_ok and pipeline_ok: state='CANDIDATE'
    else: state='SHADOW'

    monitor={
      'generated_at_utc':now,'mode':'SHADOW','research_champion':champion,
      'live':{'ranked_rows':m10.get('ranked_rows'),'v5_scored_rows':m10.get('v5_scored_rows'),'actionable_rows':m10.get('actionable_rows'),'portfolio_rows':m10.get('portfolio_rows'),'status':m10.get('status')},
      'inference':{'target_date':m11.get('target_date'),'ranked_rows':m11.get('ranked_rows'),'scored_rows':m11.get('scored_rows'),'coverage_pct':m11.get('scoring_coverage_pct'),'status':m11.get('status')},
      'forward':{'predictions':forward,'graded':graded,'pending':pending,'v5_brier':brier,'market_brier':market_brier,'v5_log_loss':metrics.get('v5_log_loss'),'market_log_loss':metrics.get('market_log_loss'),'v5_ece':metrics.get('v5_ece_5bin'),'market_ece':metrics.get('market_ece_5bin'),'positive_edge_roi':roi},
      'clv':{'explicit_coverage_pct':clv,'m06_snapshot_match_coverage_pct':m06.get('snapshot_match_coverage_pct')},
      'archive':{'status':health.get('status'),'healthy':archive_ok},
      'v4_forward_comparison':{'status':'UNAVAILABLE_COMPATIBLE_LEDGER','note':'Sprint 1 will compare V4 once a same-key immutable V4 forward ledger is published; no historical V4 metric is substituted for true forward evidence.'}
    }

    daily={
      'generated_at_utc':now,'report_type':'V5_DAILY_SHADOW','promotion_state':state,'champion':champion,
      'board_date':m11.get('target_date'),'games_analyzed_proxy':None,'ranked_opportunities':m11.get('ranked_rows'),
      'v5_predictions_issued':m11.get('scored_rows'),'v5_scoring_coverage_pct':m11.get('scoring_coverage_pct'),
      'actionable_shadow_signals':m10.get('actionable_rows'),'shadow_portfolio_rows':m10.get('portfolio_rows'),
      'forward_predictions':forward,'forward_graded':graded,'pending_grades':pending,'explicit_clv_coverage_pct':clv,
      'v5_brier':brier,'market_brier':market_brier,'positive_edge_roi':roi,'archive_health':health.get('status'),
      'recommendation':'PROMOTE' if ready else 'CONTINUE_SHADOW'
    }

    weekly={
      'generated_at_utc':now,'report_type':'V5_WEEKLY_RESEARCH_AUDIT','week_utc':datetime.now(timezone.utc).strftime('%G-W%V'),
      'champion':champion,'m05_baseline_brier':next((r.get('brier') for r in (m05.get('rankings') or []) if r.get('model')==champion),None),
      'forward_v5_brier':brier,'forward_market_brier':market_brier,'forward_brier_delta_vs_market':round(market_brier-brier,6) if brier is not None and market_brier is not None else None,
      'forward_roi':roi,'explicit_clv_coverage_pct':clv,'forward_sample':graded,'archive_healthy':archive_ok,'pipeline_healthy':pipeline_ok,
      'research_recommendation':'RETAIN_CHAMPION_AND_CONTINUE_SHADOW' if not ready else 'NOMINATE_V5_FOR_PRODUCTION_REVIEW',
      'notes':['No champion promotion is automatic from this audit.','Forward evidence is authoritative; historical M05 metrics remain baseline context only.']
    }

    promo={
      'generated_at_utc':now,'version':'V5','promotion_state':state,'production_ready':ready,'research_champion':champion,
      'progress':{
        'forward_graded':{'current':graded,'required':300,'pct':min(100.0,pct(graded,300))},
        'explicit_clv_coverage':{'current_pct':clv,'required_pct':60.0,'pct':min(100.0,round(clv/60*100,2))},
        'brier_vs_market':{'v5':brier,'market':market_brier,'pass':brier_beats_market},
        'positive_edge_roi':{'value':roi,'pass':roi is not None and roi>0},
        'archive_health':{'status':health.get('status'),'pass':archive_ok},
        'pipeline_health':{'m10':m10.get('status'),'m11':m11.get('status'),'pass':pipeline_ok},
      },
      'blockers':blockers,'recommendation':'PROMOTE_V5' if ready else 'CONTINUE_SHADOW_MODE'
    }
    status={
      'version':'V5','sprint':'OPERATIONS_SPRINT_1','status':'COMPLETE' if all([M10.exists(),M11.exists(),M12.exists(),HEALTH.exists()]) else 'PARTIAL',
      'generated_at_utc':now,'deliverables':{
        'shadow_production_monitor':'READY','daily_shadow_report':'READY','continuous_learning_warehouse':'READY_M12',
        'weekly_research_audit':'READY','promotion_dashboard':'READY'
      },
      'promotion_state':state,'production_ready':ready,'next_focus':'ACCUMULATE_FORWARD_EVIDENCE_AND_EXPLICIT_CLV'
    }
    for path,obj in ((OUT_MON,monitor),(OUT_DAILY,daily),(OUT_WEEKLY,weekly),(OUT_PROMO,promo),(OUT_STATUS,status)):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(status,indent=2))

if __name__=='__main__':main()
