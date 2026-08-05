from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

AUDIT = Path('docs/audit/repository_file_audit.csv')
OUT_JSON = Path('docs/audit/phase_b_classification.json')
OUT_CSV = Path('docs/audit/phase_b_classification.csv')
OUT_MD = Path('docs/audit/PHASE_B_CLASSIFICATION_COMPLETE.md')

PROTECTED_PREFIXES = (
    'data/history/',
    'data/warehouse/',
    'data/master/',
    'docs/audit/',
)
CORE_PREFIXES = (
    '.github/workflows/',
    'scripts/',
    'config/',
)
TRASH_HINTS = (
    'tmp', 'temp', 'copy', 'backup', 'old', 'unused', 'deprecated',
)
LEGACY_HINTS = (
    'sprint', 'phase', '_v2', '_v3', '_v4', '_v5', 'patch_', 'repair_', 'archive_',
)


def truthy(value: str) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y'}


def classify(row: dict[str, str]) -> tuple[str, str, str]:
    path = row.get('path', '').strip()
    initial = row.get('classification', '').strip().upper()
    reason = row.get('reason', '').strip()
    duplicate_of = row.get('duplicate_of', '').strip()
    workflow_refs = row.get('workflow_references', '').strip()
    python_refs = row.get('python_references', '').strip()
    referenced = bool(workflow_refs or python_refs)

    if path.startswith(PROTECTED_PREFIXES):
        return 'PROTECTED', 'KEEP', 'Historical, canonical, warehouse, or audit evidence; never auto-delete.'

    if initial == 'KEEP' or referenced:
        return 'CORE', 'KEEP', 'Referenced by an active workflow/import or already classified as production infrastructure.'

    if initial == 'DOC':
        return 'DOCUMENTATION', 'KEEP', 'Documentation retained unless later identified as superseded.'

    if initial == 'ARCHIVE' or '/workflows-archive/' in path:
        return 'LEGACY_REFERENCE', 'ARCHIVE', 'Already separated from production; retain as historical reference for now.'

    if initial == 'GENERATED':
        return 'GENERATED_OUTPUT', 'POLICY', 'Generated artifact; keep current outputs and define explicit history/retention policy.'

    if initial == 'REVIEW_DUPLICATE' or duplicate_of:
        return 'EXACT_DUPLICATE', 'DELETE_CANDIDATE', f'Byte-identical duplicate of {duplicate_of or "another tracked file"}; safe only after path ownership check.'

    low = path.lower()
    if any(token in low for token in TRASH_HINTS):
        return 'LIKELY_TRASH', 'DELETE_CANDIDATE', 'Unreferenced file with temporary/backup/deprecated naming.'

    if any(token in low for token in LEGACY_HINTS):
        return 'SUPERSEDED_OR_EXPERIMENTAL', 'ARCHIVE_CANDIDATE', 'Unreferenced versioned, sprint, phase, patch, repair, or archive-style implementation.'

    if path.endswith(('.py', '.yml', '.yaml', '.json', '.csv', '.jsonl')):
        return 'UNOWNED', 'REVIEW_OWNER', reason or 'No active workflow/import ownership found.'

    return 'UNCLASSIFIED', 'REVIEW_OWNER', reason or 'Manual ownership review required.'


def main() -> None:
    if not AUDIT.exists():
        raise SystemExit(f'Missing Phase A audit: {AUDIT}')

    with AUDIT.open(newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))

    output: list[dict[str, str]] = []
    counts = Counter()
    actions = Counter()
    for row in rows:
        bucket, action, rationale = classify(row)
        record = dict(row)
        record.update({'phase_b_bucket': bucket, 'recommended_action': action, 'phase_b_rationale': rationale})
        output.append(record)
        counts[bucket] += 1
        actions[action] += 1

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({'summary': {'buckets': counts, 'actions': actions}, 'files': output}, indent=2), encoding='utf-8')

    fields = list(output[0].keys()) if output else ['path', 'phase_b_bucket', 'recommended_action', 'phase_b_rationale']
    with OUT_CSV.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)

    delete_candidates = [r for r in output if r['recommended_action'] == 'DELETE_CANDIDATE']
    archive_candidates = [r for r in output if r['recommended_action'] == 'ARCHIVE_CANDIDATE']
    owner_review = [r for r in output if r['recommended_action'] == 'REVIEW_OWNER']

    lines = [
        '# Phase B Classification Complete',
        '',
        'Phase B is a non-destructive classification pass over the Phase A inventory.',
        '',
        '## Classification totals',
        '',
    ]
    for key, value in sorted(counts.items()):
        lines.append(f'- **{key}:** {value}')
    lines += ['', '## Recommended actions', '']
    for key, value in sorted(actions.items()):
        lines.append(f'- **{key}:** {value}')
    lines += [
        '',
        '## Safety rules',
        '',
        '- No files were deleted or moved in Phase B.',
        '- `data/history/`, `data/warehouse/`, `data/master/`, and prior audit evidence are protected.',
        '- Exact duplicates remain candidates until ownership and path expectations are confirmed.',
        '- Generated files require a retention policy rather than blanket deletion.',
        '',
        '## Highest-priority delete candidates',
        '',
    ]
    for r in delete_candidates[:50]:
        lines.append(f"- `{r['path']}` — {r['phase_b_rationale']}")
    lines += ['', '## Highest-priority archive candidates', '']
    for r in archive_candidates[:75]:
        lines.append(f"- `{r['path']}` — {r['phase_b_rationale']}")
    lines += ['', '## Ownership review queue', '']
    for r in owner_review[:75]:
        lines.append(f"- `{r['path']}` — {r['phase_b_rationale']}")
    lines += [
        '',
        '## Phase C entry criteria',
        '',
        'Phase C may begin after reviewing the delete and archive queues and approving controlled cleanup batches.',
    ]
    OUT_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(json.dumps({'buckets': counts, 'actions': actions}, indent=2, default=dict))


if __name__ == '__main__':
    main()
