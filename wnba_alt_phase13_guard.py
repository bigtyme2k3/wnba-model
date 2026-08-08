"""Phase 13 archive protection and regression guard.

Locks the current canonical ALT archive quality floor and fails CI on regressions.
This does not mutate historical archive rows. It emits a dashboard health payload
and an immutable baseline snapshot for future comparison.
"""
from __future__ import annotations
import csv, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

FINAL=Path('data/dashboard/wnba_alt_phase12_final.json')
CERT=Path('data/dashboard/wnba_alt_archive_certification.json')
CANON=Path('data/history/wnba_alt_streak_history_v3.jsonl')
UNRES=Path('data/dashboard/wnba_alt_archive_unresolved_v3.csv')
BASELINE=Path('data/warehouse/wnba_alt_phase13_baseline.json')
HEALTH=Path('data/dashboard/wnba_alt_archive_health.json')

MIN_COVERAGE=95.38
MIN_CERTIFIED=970
MAX_UNRESOLVED=47
EXPECTED_ROWS=1017


def load_json(p:Path):
    return json.loads(p.read_text(encoding='utf-8'))

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    final=load_json(FINAL)
    cert=load_json(CERT)
    canonical_rows=sum(1 for line in CANON.read_text(encoding='utf-8').splitlines() if line.strip())
    unresolved_rows=sum(1 for _ in csv.DictReader(UNRES.open(encoding='utf-8'))) if UNRES.exists() else 0

    checks={
        'canonical_rows_locked': canonical_rows==EXPECTED_ROWS,
        'certified_floor': int(final.get('certified_rows') or 0)>=MIN_CERTIFIED,
        'coverage_floor': float(final.get('coverage_pct') or 0)>=MIN_COVERAGE,
        'unresolved_ceiling': int(final.get('unresolved_rows') or 0)<=MAX_UNRESOLVED,
        'unresolved_file_reconciles': unresolved_rows==int(final.get('unresolved_rows') or 0),
        'blocking_outcome_discrepancies_zero': int(final.get('blocking_outcome_discrepancies') or 0)==0,
        'warehouse_cardinality_failures_zero': int((final.get('unresolved_classification_counts') or {}).get('WAREHOUSE_RECORD_CARDINALITY_FAILURE') or 0)==0,
        'archive_accounting': int(final.get('certified_rows') or 0)+int(final.get('unresolved_rows') or 0)==EXPECTED_ROWS,
    }
    passed=all(checks.values())
    generated=datetime.now(timezone.utc).isoformat()
    baseline={
        'schema':'alt-phase13-baseline-v1',
        'created_at_utc':generated,
        'canonical_rows':EXPECTED_ROWS,
        'minimum_certified_rows':MIN_CERTIFIED,
        'minimum_coverage_pct':MIN_COVERAGE,
        'maximum_unresolved_rows':MAX_UNRESOLVED,
        'maximum_blocking_outcome_discrepancies':0,
        'maximum_warehouse_cardinality_failures':0,
        'canonical_archive_sha256':sha256(CANON),
        'append_only_required':True,
        'note':'Coverage/certified count may improve; any regression below this floor fails Phase 13.'
    }
    if not BASELINE.exists():
        BASELINE.parent.mkdir(parents=True,exist_ok=True)
        BASELINE.write_text(json.dumps(baseline,indent=2)+'\n',encoding='utf-8')
    else:
        baseline=load_json(BASELINE)

    health={
        'generated_at_utc':generated,
        'phase':'13',
        'status':'HEALTHY_LOCKED' if passed else 'REGRESSION_BLOCKED',
        'archive_status':final.get('status'),
        'canonical_rows':canonical_rows,
        'certified_rows':final.get('certified_rows'),
        'primary_certified_observations':final.get('primary_certified_observations'),
        'redundant_exact_observations':final.get('redundant_exact_observations'),
        'unresolved_rows':final.get('unresolved_rows'),
        'coverage_pct':final.get('coverage_pct'),
        'blocking_outcome_discrepancies':final.get('blocking_outcome_discrepancies'),
        'unresolved_classification_counts':final.get('unresolved_classification_counts',{}),
        'checks':checks,
        'baseline':baseline,
        'production_ready':bool(final.get('production_ready')),
        'certification_status':cert.get('status'),
    }
    HEALTH.parent.mkdir(parents=True,exist_ok=True)
    HEALTH.write_text(json.dumps(health,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(health,indent=2))
    if not passed:
        failed=[k for k,v in checks.items() if not v]
        raise SystemExit('PHASE13_ARCHIVE_REGRESSION: '+', '.join(failed))

if __name__=='__main__': main()
