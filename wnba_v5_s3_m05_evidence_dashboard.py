"""WNBA V5 Operations Sprint 3 M05 - evidence accumulation dashboard.

Combines forward grading (M03), explicit CLV evidence (M04), canonical forward
performance diagnostics, and M12 state into one promotion-control payload.
This module never promotes V5; it only reports progress toward the locked
production gates.

IMPORTANT: promotion evidence is counted at the independent market level using
one earliest immutable prediction per ranking_key. Repeated refresh snapshots
remain useful operational diagnostics but MUST NOT inflate forward sample size
or quality metrics.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

DASH=Path('data/dashboard')
M03=DASH/'wnba_v5_s3_m03_forward_grade.json'
M04=DASH/'wnba_v5_s3_m04_report.json'
M12_METRICS=DASH/'wnba_v5_forward_metrics.json'
M12_STATE=DASH/'wnba_v5_learning_state.json'
FORWARD_DIAG=DASH/'wnba_v5_forward_diagnostics.json'
RECAL=DASH/'wnba_v5_probability_recalibration.json'
M13=DASH/'wnba_v5_production_status.json'
OUT=DASH/'wnba_v5_evidence_dashboard.json'
METER=DASH/'wnba_v5_promotion_meter.json'
HIST=DASH/'wnba_v5_evidence_history.csv'
REPORT=DASH/'wnba_v5_s3_m05_report.json'
MIN_FORWARD=300
MIN_CLV=60.0

def load(path,default):
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def num(v,default=0):
    try:return float(v)
    except Exception:return default

def pct(n,d):
    return round((100.0*n/d),2) if d else 0.0

def append_history(row):
    HIST.parent.mkdir(parents=True,exist_ok=True)
    existing=[]
    if HIST.exists():
        try:existing=list(csv.DictReader(HIST.open(encoding='utf-8-sig',newline='')))
        except Exception:existing=[]
    fields=[]
    for old in existing:
        for key in old.keys():
            if key and key not in fields: fields.append(key)
    for key in row.keys():
        if key not in fields: fields.append(key)
    existing.append(dict(row))
    existing=existing[-1000:]
    with HIST.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields,extrasaction='ignore');w.writeheader()
        for item in existing:
            w.writerow({k:item.get(k,'') for k in fields})

def main():
    now=datetime.now(timezone.utc).isoformat()
    m03=load(M03,{})
    m04=load(M04,{})
    metrics=load(M12_METRICS,{})
    state=load(M12_STATE,{})
    diag=load(FORWARD_DIAG,{})
    recal=load(RECAL,{})
    m13=load(M13,{})

    # Snapshot diagnostics must come from the same immutable ledger view that
    # M12 and Forward Diagnostics just rebuilt. M03 can lag by one refresh, so
    # it is retained as an independent grading product but is not authoritative
    # for the current snapshot ledger count.
    snapshot_forward=int(diag.get('ledger_rows',metrics.get('forward_predictions',0)) or 0)
    snapshot_graded=int(metrics.get('binary_graded_predictions',m03.get('certified_rows',0)) or 0)
    snapshot_pending=int(metrics.get('pending_predictions',m03.get('pending_rows',0)) or 0)

    canonical=diag.get('canonical_earliest_prediction_per_market',{}) if isinstance(diag,dict) else {}
    canonical_overall=canonical.get('overall',{}) if isinstance(canonical,dict) else {}
    canonical_total=int(diag.get('unique_ranking_keys',0) or 0) if isinstance(diag,dict) else 0
    canonical_graded=int(canonical_overall.get('n',0) or 0)
    canonical_pending=max(0,canonical_total-canonical_graded)
    canonical_evidence_ready=canonical_total>0 and canonical_graded>0
    graded=canonical_graded if canonical_evidence_ready else 0
    forward=canonical_total if canonical_evidence_ready else 0
    pending=canonical_pending if canonical_evidence_ready else 0
    explicit=int(m04.get('explicit_close_predictions',0) or 0)
    clv_cov=num(m04.get('explicit_clv_coverage_pct'),0.0)
    v5_brier=canonical_overall.get('v5_brier') if canonical_evidence_ready else None
    market_brier=canonical_overall.get('market_brier') if canonical_evidence_ready else None
    roi=canonical_overall.get('positive_edge_roi') if canonical_evidence_ready else None
    if roi is None and canonical_evidence_ready: roi=canonical_overall.get('model_roi_at_0_5')
    ece=metrics.get('v5_ece_5bin'); accuracy=metrics.get('v5_accuracy')
    brier_gate=(v5_brier is not None and market_brier is not None and num(v5_brier,999)<num(market_brier,-999))
    sample_gate=canonical_evidence_ready and graded>=MIN_FORWARD
    clv_gate=clv_cov>=MIN_CLV
    roi_gate=(roi is not None and num(roi,-999)>0)
    archive_gate=True; pipeline_gate=True
    if isinstance(m13,dict) and m13:
        archive_gate=bool(m13.get('archive_healthy',m13.get('archive_health',True)) not in {False,'FAIL','UNHEALTHY'})
        pipeline_gate=bool(m13.get('pipeline_healthy',m13.get('pipeline_health',True)) not in {False,'FAIL','UNHEALTHY'})
    gates={'canonical_forward_sample_gate':sample_gate,'explicit_clv_gate':clv_gate,'beats_market_brier_gate':brier_gate,'positive_roi_gate':roi_gate,'archive_health_gate':archive_gate,'pipeline_health_gate':pipeline_gate}
    all_pass=all(gates.values())
    state_name='PRODUCTION_READY' if all_pass else ('CANDIDATE' if sample_gate and clv_gate else 'SHADOW')
    progress={'canonical_graded_forward_markets':graded,'minimum_canonical_graded_forward_markets':MIN_FORWARD,'canonical_forward_progress_pct':round(min(100.0,pct(graded,MIN_FORWARD)),2),'canonical_forward_remaining':max(0,MIN_FORWARD-graded),'canonical_forward_markets_total':forward,'canonical_pending_markets':pending,'snapshot_ledger_rows_diagnostic_only':snapshot_forward,'snapshot_graded_rows_diagnostic_only':snapshot_graded,'snapshot_pending_rows_diagnostic_only':snapshot_pending,'average_snapshots_per_ranking_key':(diag.get('snapshot_multiplicity',{}) or {}).get('average_snapshots_per_ranking_key') if isinstance(diag,dict) else None,'explicit_close_predictions':explicit,'explicit_clv_coverage_pct':round(clv_cov,2),'minimum_explicit_clv_coverage_pct':MIN_CLV,'explicit_clv_progress_pct':round(min(100.0,(clv_cov/MIN_CLV*100.0 if MIN_CLV else 0.0)),2),'explicit_clv_shortfall_pct':round(max(0.0,MIN_CLV-clv_cov),2)}
    performance={'evidence_unit':'earliest_immutable_prediction_per_ranking_key','canonical_v5_brier':v5_brier,'canonical_market_brier':market_brier,'v5_beats_market_brier':brier_gate,'canonical_positive_edge_roi':canonical_overall.get('positive_edge_roi') if canonical_evidence_ready else None,'canonical_model_roi_at_0_5':canonical_overall.get('model_roi_at_0_5') if canonical_evidence_ready else None,'positive_roi':roi_gate,'snapshot_v5_ece_5bin_diagnostic_only':ece,'snapshot_v5_accuracy_diagnostic_only':accuracy,'shadow_recalibration_global_alpha':recal.get('global_alpha') if isinstance(recal,dict) else None,'shadow_recalibration_status':recal.get('status') if isinstance(recal,dict) else None}
    blockers=[]
    if not canonical_evidence_ready:blockers.append('Canonical independent forward diagnostics are unavailable')
    elif not sample_gate:blockers.append(f'Need {max(0,MIN_FORWARD-graded)} more canonical independent graded forward markets')
    if not clv_gate:blockers.append(f'Explicit CLV coverage needs {round(max(0.0,MIN_CLV-clv_cov),2)} more percentage points')
    if not brier_gate:blockers.append('V5 has not yet demonstrated lower canonical forward Brier than market')
    if not roi_gate:blockers.append('Positive canonical forward ROI not yet demonstrated')
    if not archive_gate:blockers.append('Archive health gate failed')
    if not pipeline_gate:blockers.append('Pipeline health gate failed')
    historical_champion=state.get('research_champion','KNN')
    forward_champion_status='UNRESOLVED' if not all_pass else historical_champion
    dashboard={'version':'V5','sprint':'OPERATIONS_SPRINT_3','module':'S3-M05','stage':'EVIDENCE_ACCUMULATION_DASHBOARD','generated_at_utc':now,'status':'READY','promotion_state':state_name,'production_ready':all_pass,'historical_research_champion':historical_champion,'authoritative_forward_champion':forward_champion_status,'progress':progress,'performance':performance,'gates':gates,'blockers':blockers,'recommendation':'PROMOTE_V5' if all_pass else 'CONTINUE_SHADOW_AND_ACCUMULATE_CANONICAL_FORWARD_EVIDENCE','policy':'M05 is reporting-only. Promotion uses one earliest immutable prediction per ranking_key; repeated refresh snapshots never count as independent evidence.','next_module':'S3-M06 Autonomous Evidence Cycle'}
    meter={'version':'V5','promotion_state':state_name,'production_ready':all_pass,'generated_at_utc':now,'forward':{'current':graded,'required':MIN_FORWARD,'remaining':max(0,MIN_FORWARD-graded),'progress_pct':progress['canonical_forward_progress_pct'],'evidence_unit':'canonical_independent_market'},'explicit_clv':{'current_pct':round(clv_cov,2),'required_pct':MIN_CLV,'shortfall_pct':progress['explicit_clv_shortfall_pct'],'progress_pct':progress['explicit_clv_progress_pct']},'quality':performance,'gates':gates,'blockers':blockers}
    histrow={'generated_at_utc':now,'promotion_state':state_name,'canonical_forward_markets_total':forward,'canonical_graded_markets':graded,'canonical_pending_markets':pending,'snapshot_ledger_rows':snapshot_forward,'snapshot_graded_rows':snapshot_graded,'explicit_close_predictions':explicit,'explicit_clv_coverage_pct':round(clv_cov,2),'v5_brier':v5_brier,'market_brier':market_brier,'roi':roi,'production_ready':all_pass}
    append_history(histrow)
    OUT.write_text(json.dumps(dashboard,indent=2,allow_nan=False)+'\n',encoding='utf-8'); METER.write_text(json.dumps(meter,indent=2,allow_nan=False)+'\n',encoding='utf-8'); REPORT.write_text(json.dumps(dashboard,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dashboard,indent=2,allow_nan=False))

if __name__=='__main__':main()
