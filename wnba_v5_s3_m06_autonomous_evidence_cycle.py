"""WNBA V5 Operations Sprint 3 M06 - autonomous evidence cycle.

Coordinates the evidence stack without duplicating live odds polling. The dedicated
M02 watcher owns explicit pre-tip API capture; M06 consumes its latest immutable
outputs, then refreshes freshness/inference, grading, CLV, and promotion evidence.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DASH=Path('data/dashboard')
M01=DASH/'wnba_v5_s3_m01_freshness.json'
M02=DASH/'wnba_v5_s3_m02_report.json'
M03=DASH/'wnba_v5_s3_m03_forward_grade.json'
M04=DASH/'wnba_v5_s3_m04_report.json'
M05=DASH/'wnba_v5_s3_m05_report.json'
M11=DASH/'wnba_v5_m11_report.json'
OUT=DASH/'wnba_v5_s3_m06_autonomous_cycle.json'
STATUS=DASH/'wnba_v5_sprint3_status.json'


def load(path, default=None):
    default={} if default is None else default
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default


def run(script):
    subprocess.run(['python',script],check=True)


def main():
    now=datetime.now(timezone.utc).isoformat()

    # Freshness and inference are refreshed first. M11 safely returns a blocked
    # state rather than scoring when M01 rejects a stale slate.
    run('wnba_v5_s3_m01_freshness_guard.py')
    run('wnba_v5_m11_live_inference.py')

    # Do NOT call M02 here. Its dedicated pre-tip watcher is the only component
    # that spends Odds API credits for explicit closes. M06 consumes its latest
    # append-safe evidence, avoiding duplicate requests.
    run('wnba_v5_s3_m03_forward_reconciler.py')
    run('wnba_v5_s3_m04_explicit_clv.py')
    run('wnba_v5_s3_m05_evidence_dashboard.py')

    m01=load(M01);m02=load(M02);m03=load(M03);m04=load(M04);m05=load(M05);m11=load(M11)

    required={
        'M01':bool(m01), 'M02':bool(m02), 'M03':bool(m03),
        'M04':bool(m04), 'M05':bool(m05), 'M11':bool(m11)
    }
    modules_ready=all(required.values())
    promotion_state=m05.get('promotion_state','SHADOW')
    production_ready=bool(m05.get('production_ready',False))
    stale_blocked=m01.get('status') in {'STALE_BLOCKED','BLOCKED_NO_RANKINGS'}

    cycle={
        'version':'V5','sprint':'OPERATIONS_SPRINT_3','module':'S3-M06',
        'stage':'AUTONOMOUS_EVIDENCE_CYCLE','generated_at_utc':now,
        'status':'READY' if modules_ready else 'WAITING_FOR_REQUIRED_MODULE_OUTPUTS',
        'module_outputs_present':required,
        'freshness_status':m01.get('status'),
        'live_inference_status':m11.get('status'),
        'closing_capture_status':m02.get('status'),
        'forward_reconciler_status':m03.get('status'),
        'explicit_clv_status':m04.get('status'),
        'evidence_dashboard_status':m05.get('status'),
        'promotion_state':promotion_state,
        'production_ready':production_ready,
        'api_policy':{
            'm06_api_calls':0,
            'closing_capture_owner':'S3-M02 dedicated pre-tip watcher',
            'reason':'M06 never duplicates live odds polling; it consumes the latest M02 explicit-close evidence.'
        },
        'safety':{
            'stale_slate_blocked':stale_blocked,
            'stale_rows_scored':0 if stale_blocked else None,
            'inferred_closes_allowed':False,
            'issued_predictions_mutable':False,
        },
        'progress':m05.get('progress',{}),
        'gates':m05.get('gates',{}),
        'blockers':m05.get('blockers',[]),
        'next_focus':'ACCUMULATE_FORWARD_EVIDENCE_AND_EXPLICIT_CLV' if not production_ready else 'V5_PROMOTION_REVIEW',
        'policy':'Sprint 3 automates trustworthy evidence accumulation while keeping odds polling centralized in M02 and promotion locked to established gates.'
    }
    sprint_status={
        'version':'V5','sprint':'OPERATIONS_SPRINT_3','status':'COMPLETE' if modules_ready else 'INCOMPLETE',
        'generated_at_utc':now,
        'modules':{
            'M01':'READY' if required['M01'] else 'MISSING',
            'M02':'READY' if required['M02'] else 'MISSING',
            'M03':'READY' if required['M03'] else 'MISSING',
            'M04':'READY' if required['M04'] else 'MISSING',
            'M05':'READY' if required['M05'] else 'MISSING',
            'M06':'READY' if modules_ready else 'WAITING',
        },
        'promotion_state':promotion_state,'production_ready':production_ready,
        'next_focus':cycle['next_focus']
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(cycle,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    STATUS.write_text(json.dumps(sprint_status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(cycle,indent=2,allow_nan=False))

if __name__=='__main__':main()
