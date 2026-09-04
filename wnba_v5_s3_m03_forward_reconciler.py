"""WNBA V5 Operations Sprint 3 M03 — Forward Outcome Reconciler.

Consumes the canonical immutable M12 forward ledger and publishes reconciliation-
specific views for pending and certified forward predictions. This module never
runs M12 and never rewrites the ledger.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path('data/history/wnba_v5_forward_predictions.jsonl')
M12_REPORT = Path('data/dashboard/wnba_v5_m12_report.json')
OUT_REPORT = Path('data/dashboard/wnba_v5_s3_m03_forward_grade.json')
OUT_PENDING = Path('data/dashboard/wnba_v5_pending_predictions.json')
OUT_CERTIFIED = Path('data/dashboard/wnba_v5_certified_results.csv')


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


def main():
    rows = read_ledger()
    m12=json.loads(M12_REPORT.read_text(encoding='utf-8')) if M12_REPORT.exists() else {}
    pending=[r for r in rows if r.get('outcome') in (None,'','PENDING')]
    certified=[r for r in rows if r.get('outcome') in {'WIN','LOSS','PUSH'}]

    now=datetime.now(timezone.utc).isoformat()
    report={
        'version':'V5',
        'sprint':'OPERATIONS_SPRINT_3',
        'module':'S3-M03',
        'stage':'FORWARD_OUTCOME_RECONCILER',
        'status':'READY' if rows else 'WAITING_FOR_FORWARD_PREDICTIONS',
        'generated_at_utc':now,
        'ledger_rows':len(rows),
        'certified_rows':len(certified),
        'pending_rows':len(pending),
        'newly_graded':int(m12.get('newly_graded') or 0),
        'm12_status':m12.get('status'),
        'immutable_prediction_fields_preserved':True,
        'consumer_only':True,
        'canonical_ledger_owner':'V5-M12',
        'grading_source':'Canonical M12 forward ledger; S3-M03 performs no grading mutation.',
        'policy':'Only M12 may append or resolve canonical forward ledger rows; S3-M03 publishes read-only reconciliation views.',
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
