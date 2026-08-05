from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

AUDIT = Path('docs/audit/repository_file_audit.csv')
OUT_JSON = Path('docs/audit/phase_b_classification.json')
OUT_CSV = Path('docs/audit/phase_b_classification.csv')
OUT_MD = Path('docs/audit/PHASE_B_CLASSIFICATION_COMPLETE.md')

PROTECTED_PREFIXES = ('data/history/', 'data/warehouse/', 'data/master/', 'docs/audit/')
TRASH_HINTS = ('tmp', 'temp', 'copy', 'backup', 'old', 'unused', 'deprecated')
LEGACY_HINTS = ('sprint', 'phase', '_v2', '_v3', '_v4', '_v5', 'patch_', 'repair_', 'archive_')

ALIASES = {
    'file': 'path',
    'filepath': 'path',
    'file_path': 'path',
    'filename': 'path',
    'category': 'classification',
    'class': 'classification',
    'active_workflow_owners': 'workflow_references',
    'workflow_refs': 'workflow_references',
    'python_owners': 'python_references',
    'python_refs': 'python_references',
    'duplicate': 'duplicate_of',
}


def normalize_row(row: dict[str, str | None]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_key, raw_value in (row or {}).items():
        key = str(raw_key or '').strip().lower().replace(' ', '_')
        key = ALIASES.get(key, key)
        out[key] = '' if raw_value is None else str(raw_value).strip()
    return out


def classify(row: dict[str, str]) -> tuple[str, str, str]:
    path = row.get('path', '')
    initial = row.get('classification', '').upper()
    reason = row.get('reason', '')
    duplicate_of = row.get('duplicate_of', '')
    referenced = bool(row.get('workflow_references') or row.get('python_references'))

    if not path:
        return 'MALFORMED_RECORD', 'REVIEW_OWNER', 'No usable file path after schema normalization.'
    if path.startswith(PROTECTED_PREFIXES):
        return 'PROTECTED', 'KEEP', 'Historical, canonical, warehouse, or audit evidence.'
    if initial == 'KEEP' or referenced:
        return 'CORE', 'KEEP', 'Referenced by production workflow/import or already marked KEEP.'
    if initial == 'DOC':
        return 'DOCUMENTATION', 'KEEP', 'Documentation retained pending supersession review.'
    if initial == 'ARCHIVE' or '/workflows-archive/' in path:
        return 'LEGACY_REFERENCE', 'ARCHIVE', 'Already isolated from production.'
    if initial == 'GENERATED':
        return 'GENERATED_OUTPUT', 'POLICY', 'Generated artifact requiring retention policy.'
    if initial == 'REVIEW_DUPLICATE' or duplicate_of:
        return 'EXACT_DUPLICATE', 'DELETE_CANDIDATE', f'Byte-identical duplicate of {duplicate_of or "another tracked file"}.'

    low = path.lower()
    if any(token in low for token in TRASH_HINTS):
        return 'LIKELY_TRASH', 'DELETE_CANDIDATE', 'Unreferenced temporary/backup/deprecated naming.'
    if any(token in low for token in LEGACY_HINTS):
        return 'SUPERSEDED_OR_EXPERIMENTAL', 'ARCHIVE_CANDIDATE', 'Unreferenced sprint/version/patch/repair implementation.'
    if path.endswith(('.py', '.yml', '.yaml', '.json', '.csv', '.jsonl')):
        return 'UNOWNED', 'REVIEW_OWNER', reason or 'No active owner found.'
    return 'UNCLASSIFIED', 'REVIEW_OWNER', reason or 'Manual ownership review required.'


def main() -> None:
    if not AUDIT.exists():
        raise SystemExit(f'Missing Phase A audit: {AUDIT}')

    with AUDIT.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        print('Phase A headers:', reader.fieldnames)
        raw_rows = list(reader)

    rows = [normalize_row(row) for row in raw_rows]
    for sample in rows[:3]:
        if not sample.get('path') or not sample.get('classification'):
            raise SystemExit(f'Header normalization failed for sample: {sample}')

    output: list[dict[str, str]] = []
    buckets: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    for line_no, row in enumerate(rows, start=2):
        bucket, action, rationale = classify(row)
        record = dict(row)
        record.update({
            'phase_a_csv_line': str(line_no),
            'phase_b_bucket': bucket,
            'recommended_action': action,
            'phase_b_rationale': rationale,
        })
        output.append(record)
        buckets[bucket] += 1
        actions[action] += 1

    if buckets.get('MALFORMED_RECORD', 0) == len(output):
        raise SystemExit('All rows malformed; refusing false-success classification.')
    if actions.get('KEEP', 0) == 0:
        raise SystemExit('No keep set produced; refusing false-success classification.')

    payload = {'summary': {'buckets': dict(buckets), 'actions': dict(actions)}, 'files': output}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    fields = sorted({key for record in output for key in record})
    preferred = ['path', 'classification', 'reason', 'workflow_references', 'python_references', 'duplicate_of', 'phase_b_bucket', 'recommended_action', 'phase_b_rationale']
    fields = [x for x in preferred if x in fields] + [x for x in fields if x not in preferred]
    with OUT_CSV.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(output)

    lines = ['# Phase B Classification Complete', '', f'- **Input rows:** {len(raw_rows)}', f'- **Classified rows:** {len(output)}', '', '## Classification totals', '']
    lines += [f'- **{k}:** {v}' for k, v in sorted(buckets.items())]
    lines += ['', '## Recommended actions', '']
    lines += [f'- **{k}:** {v}' for k, v in sorted(actions.items())]
    lines += ['', '## Safety rules', '', '- No files were deleted or moved.', '- Historical and warehouse records remain protected.', '- Generated outputs require a retention policy.', '', '## Top cleanup candidates', '']
    candidates = [r for r in output if r['recommended_action'] in {'DELETE_CANDIDATE', 'ARCHIVE_CANDIDATE'}]
    for record in candidates[:100]:
        lines.append(f"- `{record.get('path', '[missing path]')}` — {record.get('phase_b_rationale', '')}")
    OUT_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(json.dumps(payload['summary'], indent=2))


if __name__ == '__main__':
    main()
