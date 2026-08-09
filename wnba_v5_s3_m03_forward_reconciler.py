"""WNBA V5 Operations Sprint 3 M03 — Forward Outcome Reconciler.

Runs the immutable M12 grader, then publishes reconciliation-specific artifacts
for pending and newly certified forward predictions. No issued probability,
line, price, or timestamp is ever rewritten by this module.
"""
from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path('data/history/wnba_v5_forward_predictions.jsonl')
M12_REPORT = Path('data/dashboard/wnba_v5_m12_report.json')
OUT_REPORT = Path('data/dashboard/wnba_v5_s3_m03_forward_grade.json')
OUT_PENDING = Path('data/dashboard/wnba_v5_pending_predictions.json')
OUT_CERTIFIED = Path('data/dashboard/wnba_v5_certified_results.csv')

IMMUTABLE_FIELDS = [
    'prediction_id','ranking_key','prediction_generated_at_utc','date','player','game','stat','side',
    'line','odds','book','model','v5_probability','knn_probability','market_probability',
    'probability_edge','confidence_score','uncertainty_score'
]


def read_ledger():
    rows=[]
    if not LEDGER.exists():
        return rows
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def freeze_signature(row):
    return {k: row.get(k) for k in IMMUTABLE_FIELDS}


def main():
    before = read_ledger()
    before_sig = {r.get('prediction_id'): freeze_signature(r) for r in before if r.get('prediction_id')}

    subprocess.run(['python','wnba_v5_m12_postgame_learning.py'], check=True)

    after = read_ledger()
    for r in after:
        pid=r.get('prediction_id')
        if pid in before_sig and freeze_signature(r) != before_sig[pid]:
            raise SystemExit(f'S3_M03_BLOCKED: immutable prediction fields changed for {pid}')

    m12=json.loads(M12_REPORT.read_text(encoding='utf-8')) if M12_REPORT.exists() else {}
    pending=[r for r in after if r.get('outcome') in (None,'','PENDING')]
    certified=[r for r in after if r.get('outcome') in {'WIN','LOSS','PUSH'}]
    newly=[r for r in certified if r.get('graded_at_utc') and not any(
        b.get('prediction_id')==r.get('prediction_id') and b.get('outcome') in {'WIN','LOSS','PUSH'} for b in before
    )]

    now=datetime.now(timezone.utc).isoformat()
    report={
        'version':'V5',
        'sprint':'OPERATIONS_SPRINT_3',
        'module':'S3-M03',
        'stage':'FORWARD_OUTCOME_RECONCILER',
        'status':'READY' if after else 'WAITING_FOR_FORWARD_PREDICTIONS',
        'generated_at_utc':now,
        'ledger_rows':len(after),
        'certified_rows':len(certified),
        'pending_rows':len(pending),
        'newly_graded':len(newly),
        'm12_status':m12.get('status'),
        'immutable_prediction_fields_preserved':True,
        'grading_source':'V5 certified historical feature store via M12 exact date/player/stat reconciliation',
        'policy':'Only later certified actuals may resolve forward predictions; issued probabilities and market terms remain immutable.',
        'next_module':'S3-M04 Explicit CLV Engine'
    }

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    OUT_PENDING.write_text(json.dumps({'report':report,'pending':pending},indent=2)+'\n',encoding='utf-8')

    fields=[
        'prediction_id','ranking_key','prediction_generated_at_utc','date','player','game','stat','side',
        'line','odds','book','model','v5_probability','market_probability','probability_edge',
        'actual','outcome','target_win','graded_at_utc'
    ]
    with OUT_CERTIFIED.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
        for r in certified:
            w.writerow({k:r.get(k) for k in fields})

    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
