"""Current-date health audit for critical WNBA V5 production and learning artifacts.

The audit follows the canonical current-slate chain rather than legacy master files.
Legacy observability is reported separately and never determines production health.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASH = ROOT / 'data' / 'dashboard'
OUT = DASH / 'wnba_v5_current_data_health.json'

CRITICAL = {
    'canonical_manifest': ('data/dashboard/wnba_daily_canonical_manifest.json', ('target_date',), ('PASS',)),
    'player_props': ('data/dashboard/wnba_player_props.json', ('target_date',), None),
    'injury_intelligence': ('data/dashboard/wnba_injury_intelligence.json', ('target_date','date'), None),
    'm11_inference': ('data/dashboard/wnba_v5_m11_report.json', ('target_date','date'), ('READY_SHADOW','READY')),
    'm12_learning': ('data/dashboard/wnba_v5_m12_report.json', ('target_date','date'), ('READY_FORWARD_LEARNING','WAITING_FOR_CERTIFIED_OUTCOMES','WAITING_FOR_M11_PREDICTIONS')),
    'adaptive_challenger': ('data/dashboard/wnba_v5_adaptive_challenger_v2.json', ('target_date','date'), ('WAITING_FOR_RESOLVED_CONTEXT_ROWS','READY_CONTEXTUAL_SHADOW')),
    'results_lifecycle': ('data/dashboard/wnba_s19_m06_results_lifecycle.json', ('target_date',), ('READY',)),
    'alt_performance': ('data/dashboard/wnba_alt_performance.json', ('target_date',), ('ok','READY','GRADED')),
}

CONTEXT_FILES = {
    'matchup_adjustments': 'data/dashboard/wnba_v5_matchup_adjustments.csv',
    'lineup_adjustments': 'data/dashboard/wnba_v5_lineup_adjustments.csv',
}

TARGET_AUTHORITIES = (
    ('data/dashboard/wnba_daily_canonical_manifest.json', ('target_date',)),
    ('data/dashboard/wnba_player_props.json', ('target_date',)),
    ('data/dashboard/wnba_v5_m11_report.json', ('target_date','date')),
    ('data/dashboard/wnba_s19_m06_results_lifecycle.json', ('target_date',)),
    ('data/dashboard/wnba_alt_performance.json', ('target_date',)),
)

LEGACY_OBSERVABILITY = {
    'legacy_master': 'data/master/wnba_master.json',
    'source_health': 'data/dashboard/wnba_source_health.json',
    'warehouse_health': 'data/dashboard/wnba_warehouse_health.json',
    'results_review_center': 'data/dashboard/results_review_center.json',
}


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def parse_date(value):
    if not value:
        return None
    text = str(value)[:10]
    try:
        datetime.fromisoformat(text)
        return text
    except Exception:
        return None


def generated_date(payload):
    if not isinstance(payload, dict):
        return None
    for key in ('generated_at_utc','updated_at_utc','refreshed_at_utc','captured_at_utc'):
        value = payload.get(key)
        if value:
            return str(value)[:10]
    return None


def target_from(payload, keys):
    if not isinstance(payload, dict):
        return None
    for key in keys:
        d = parse_date(payload.get(key))
        if d:
            return d
    return generated_date(payload)


def current_target():
    """Resolve target from canonical same-day producers; legacy master is never authoritative."""
    observed = []
    detail = []
    for rel, keys in TARGET_AUTHORITIES:
        payload = load(ROOT / rel)
        d = target_from(payload, keys) if isinstance(payload, dict) else None
        if d:
            observed.append(d)
            detail.append({'path': rel, 'target_date': d})
    if observed:
        counts = Counter(observed)
        target = sorted(counts, key=lambda d: (counts[d], d), reverse=True)[0]
        return target, detail
    return datetime.now(timezone.utc).date().isoformat(), detail


def inspect_json(name, rel, date_keys, statuses, target):
    path = ROOT / rel
    row = {'name': name, 'path': rel, 'exists': path.exists(), 'status': 'red', 'findings': []}
    if not path.exists():
        row['findings'].append('missing_file')
        return row
    payload = load(path)
    if not isinstance(payload, dict):
        row['findings'].append('invalid_json')
        return row
    row['target_date'] = target_from(payload, date_keys)
    row['generated_date'] = generated_date(payload)
    row['reported_status'] = payload.get('status')
    if row['target_date'] and row['target_date'] != target:
        row['findings'].append(f"target_date_mismatch:{row['target_date']}!={target}")
    if statuses and payload.get('status') not in statuses:
        row['findings'].append(f"unexpected_status:{payload.get('status')}")
    row['status'] = 'green' if not row['findings'] else 'yellow'
    return row


def inspect_context(name, rel, target):
    path = ROOT / rel
    row = {'name': name, 'path': rel, 'exists': path.exists(), 'status': 'red', 'findings': []}
    if not path.exists() or path.stat().st_size == 0:
        row['findings'].append('missing_or_empty')
        return row
    mdate = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()
    row['modified_date'] = mdate
    if mdate != target:
        row['findings'].append(f'modified_date_mismatch:{mdate}!={target}')
        row['status'] = 'yellow'
    else:
        row['status'] = 'green'
    return row


def inspect_legacy(name, rel, target):
    path = ROOT / rel
    row = {'name': name, 'path': rel, 'exists': path.exists(), 'status': 'legacy_stale', 'findings': []}
    if not path.exists():
        row['findings'].append('missing_file')
        return row
    payload = load(path)
    d = target_from(payload, ('target_date','expected_target_date','date')) if isinstance(payload, dict) else None
    row['target_date'] = d
    if d == target:
        row['status'] = 'current'
    else:
        row['findings'].append(f'legacy_observability_stale:{d}!={target}')
    return row


def build():
    target, target_sources = current_target()
    critical = [inspect_json(name, *spec, target) for name, spec in CRITICAL.items()]
    context = [inspect_context(name, rel, target) for name, rel in CONTEXT_FILES.items()]
    legacy = [inspect_legacy(name, rel, target) for name, rel in LEGACY_OBSERVABILITY.items()]
    blocking = [r for r in critical + context if r['status'] == 'red']
    warnings = [r for r in critical + context if r['status'] == 'yellow']
    status = 'RED' if blocking else ('YELLOW' if warnings else 'GREEN')
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': target,
        'target_resolution': {
            'policy': 'mode of canonical same-day producers; latest date wins ties',
            'sources': target_sources,
        },
        'status': status,
        'summary': {
            'critical_checks': len(critical) + len(context),
            'green': sum(r['status']=='green' for r in critical + context),
            'yellow': len(warnings),
            'red': len(blocking),
            'legacy_stale_observability_files': sum(r['status']=='legacy_stale' for r in legacy),
        },
        'critical': critical,
        'prospective_context': context,
        'legacy_observability': legacy,
        'policy': 'Production health is based only on current canonical artifacts. Legacy master/observability files are reported but never allowed to define or mask current health.',
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, allow_nan=False))
    return payload


if __name__ == '__main__':
    build()
