"""WNBA V5 Operations Sprint 3 M05 - evidence accumulation dashboard.

Combines forward grading (M03), explicit CLV evidence (M04), and M12 forward
metrics into one promotion-control payload. This module never promotes V5; it
only reports progress toward the locked production gates.
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
    fields=list(row.keys())
    existing=[]
    if HIST.exists():
        try:existing=list(csv.DictReader(HIST.open(encoding='utf-8-sig',newline='')))
        except Exception:existing=[]
    existing.append({k:row.get(k) for k in fields})
    # Keep a bounded operational history while retaining enough trend depth.
    existing=existing[-1000:]
    with HIST.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(existing)

def main():
    now=datetime.now(timezone.utc).isoformat()
    m03=load(M03,{})
    m04=load(M04,{})
    metrics=load(M12_METRICS,{})
    state=load(M12_STATE,{})
    m13=load(M13,{})

    forward=int(m03.get('ledger_rows',metrics.get('forward_predictions',0)) or 0)
    graded=int(m03.get('certified_rows',metrics.get('binary_graded_predictions',0)) or 0)
    pending=int(m03.get('pending_rows',metrics.get('pending_predictions',0)) or 0)
    explicit=int(m04.get('explicit_close_predictions',0) or 0)
    clv_cov=num(m04.get('explicit_clv_coverage_pct'),0.0)
    v5_brier=metrics.get('v5_brier')
    market_brier=metrics.get('market_brier')
    roi=metrics.get('positive_edge_roi') if metrics.get('positive_edge_roi') is not None else metrics.get('model_roi_at_0_5')
    ece=metrics.get('v5_ece_5bin')
    accuracy=metrics.get('v5_accuracy')

    brier_gate=(v5_brier is not None and market_brier is not None and num(v5_brier,999)<num(market_brier,-999))
    sample_gate=graded>=MIN_FORWARD
    clv_gate=clv_cov>=MIN_CLV
    roi_gate=(roi is not None and num(roi,-999)>0)
    archive_gate=True
    pipeline_gate=True
    # Respect explicit M13 blockers if a production status exists.
    if isinstance(m13,dict) and m13:
        archive_gate=bool(m13.get('archive_healthy',m13.get('archive_health',True)) not in {False,'FAIL','UNHEALTHY'})
        pipeline_gate=bool(m13.get('pipeline_healthy',m13.get('pipeline_health',True)) not in {False,'FAIL','UNHEALTHY'})

    gates={
        'forward_sample_gate':sample_gate,
        'explicit_clv_gate':clv_gate,
        'beats_market_brier_gate':brier_gate,
        'positive_roi_gate':roi_gate,
        'archive_health_gate':archive_gate,
        'pipeline_health_gate':pipeline_gate,
    }
    all_pass=all(gates.values())
    state_name='PRODUCTION_READY' if all_pass else ('CANDIDATE' if sample_gate and clv_gate else 'SHADOW')

    progress={
        'graded_forward_predictions':graded,
        'minimum_graded_forward_predictions':MIN_FORWARD,
        'graded_forward_progress_pct':round(min(100.0,pct(graded,MIN_FORWARD)),2),
        'graded_forward_remaining':max(0,MIN_FORWARD-graded),
        'forward_predictions_total':forward,
        'pending_predictions':pending,
        'explicit_close_predictions':explicit,
        'explicit_clv_coverage_pct':round(clv_cov,2),
        'minimum_explicit_clv_coverage_pct':MIN_CLV,
        'explicit_clv_progress_pct':round(min(100.0,(clv_cov/MIN_CLV*100.0 if MIN_CLV else 0.0)),2),
        'explicit_clv_shortfall_pct':round(max(0.0,MIN_CLV-clv_cov),2),
    }
    performance={
        'v5_brier':v5_brier,
        'market_brier':market_brier,
        'v5_beats_market_brier':brier_gate,
        'v5_ece_5bin':ece,
        'v5_accuracy':accuracy,
        'roi':roi,
        'positive_roi':roi_gate,
    }
    blockers=[]
    if not sample_gate:blockers.append(f'Need {max(0,MIN_FORWARD-graded)} more graded forward predictions')
    if not clv_gate:blockers.append(f'Explicit CLV coverage needs {round(max(0.0,MIN_CLV-clv_cov),2)} more percentage points')
    if not brier_gate:blockers.append('V5 has not yet demonstrated lower forward Brier than market')
    if not roi_gate:blockers.append('Positive forward ROI not yet demonstrated')
    if not archive_gate:blockers.append('Archive health gate failed')
    if not pipeline_gate:blockers.append('Pipeline health gate failed')

    dashboard={
        'version':'V5','sprint':'OPERATIONS_SPRINT_3','module':'S3-M05','stage':'EVIDENCE_ACCUMULATION_DASHBOARD',
        'generated_at_utc':now,'status':'READY','promotion_state':state_name,'production_ready':all_pass,
        'research_champion':state.get('research_champion','KNN'),'progress':progress,'performance':performance,
        'gates':gates,'blockers':blockers,
        'recommendation':'PROMOTE_V5' if all_pass else 'CONTINUE_SHADOW_AND_ACCUMULATE_FORWARD_EVIDENCE',
        'policy':'M05 is reporting-only. Promotion remains locked to the established forward-sample, explicit-CLV, Brier, ROI, archive, and pipeline gates.',
        'next_module':'S3-M06 Autonomous Evidence Cycle'
    }
    meter={
        'version':'V5','promotion_state':state_name,'production_ready':all_pass,'generated_at_utc':now,
        'forward':{'current':graded,'required':MIN_FORWARD,'remaining':max(0,MIN_FORWARD-graded),'progress_pct':progress['graded_forward_progress_pct']},
        'explicit_clv':{'current_pct':round(clv_cov,2),'required_pct':MIN_CLV,'shortfall_pct':progress['explicit_clv_shortfall_pct'],'progress_pct':progress['explicit_clv_progress_pct']},
        'quality':performance,'gates':gates,'blockers':blockers
    }
    histrow={
        'generated_at_utc':now,'promotion_state':state_name,'forward_predictions_total':forward,'graded_predictions':graded,
        'pending_predictions':pending,'explicit_close_predictions':explicit,'explicit_clv_coverage_pct':round(clv_cov,2),
        'v5_brier':v5_brier,'market_brier':market_brier,'v5_ece_5bin':ece,'v5_accuracy':accuracy,'roi':roi,'production_ready':all_pass
    }
    append_history(histrow)
    OUT.write_text(json.dumps(dashboard,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    METER.write_text(json.dumps(meter,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    REPORT.write_text(json.dumps(dashboard,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dashboard,indent=2,allow_nan=False))

if __name__=='__main__':main()
