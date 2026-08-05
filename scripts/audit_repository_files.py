from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('.')
ACTIVE_WORKFLOWS = Path('.github/workflows')
ARCHIVED_WORKFLOWS = Path('.github/workflows-archive')
REPORT_DIR = Path('docs/audit')

TEXT_EXTS = {'.py', '.yml', '.yaml', '.md', '.json', '.html', '.js', '.sh', '.toml', '.txt', '.csv'}
GENERATED_PREFIXES = ('data/dashboard/', 'data/warehouse/', 'data/market/', 'data/forecast/', 'data/trends/', 'data/raw/')
HIGH_VALUE_FILES = {
    'requirements.txt', 'build_dashboard_v4.py', 'wnba_current_slate.py',
    'wnba_master_source_builder.py', 'wnba_v5_live_state_sync.py',
    'scripts/atomic_generated_push.sh', 'docs/index.html',
}


def git_files() -> list[str]:
    out = subprocess.check_output(['git', 'ls-files'], text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                h.update(block)
        return h.hexdigest()
    except Exception:
        return ''


def workflow_references(files: list[str]) -> tuple[set[str], dict[str, set[str]]]:
    refs: set[str] = set()
    owners: dict[str, set[str]] = defaultdict(set)
    for wf in sorted(ACTIVE_WORKFLOWS.glob('*.y*ml')):
        text = read_text(wf)
        for file in files:
            if file in text or Path(file).name in text:
                refs.add(file)
                owners[file].add(str(wf))
        for match in re.findall(r'(?:python|bash|sh)\s+([A-Za-z0-9_./-]+\.(?:py|sh))', text):
            candidate = match.lstrip('./')
            if candidate in files:
                refs.add(candidate)
                owners[candidate].add(str(wf))
    return refs, owners


def python_dependencies(files: list[str]) -> tuple[set[str], dict[str, set[str]]]:
    py_by_module = {Path(f).stem: f for f in files if f.endswith('.py') and '/' not in f}
    refs: set[str] = set()
    owners: dict[str, set[str]] = defaultdict(set)
    for file in [f for f in files if f.endswith('.py')]:
        text = read_text(Path(file))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module.split('.')[0])
        for module in modules:
            target = py_by_module.get(module)
            if target:
                refs.add(target)
                owners[target].add(file)
        for target in files:
            if target.endswith('.py') and target != file and Path(target).name in text:
                refs.add(target)
                owners[target].add(file)
    return refs, owners


def classify(file: str, wf_refs: set[str], py_refs: set[str], duplicate_hashes: dict[str, list[str]], archived_names: set[str]) -> tuple[str, str]:
    p = Path(file)
    name = p.name
    if file in HIGH_VALUE_FILES:
        return 'KEEP', 'Canonical production/build infrastructure'
    if file.startswith('.github/workflows/'):
        return 'KEEP', 'Active GitHub Actions workflow'
    if file.startswith('.github/workflows-archive/'):
        return 'ARCHIVE', 'Already isolated from production execution'
    if file in wf_refs:
        return 'KEEP', 'Referenced by an active workflow'
    if file in py_refs:
        return 'KEEP', 'Imported or invoked by tracked Python code'
    if file.startswith(GENERATED_PREFIXES):
        return 'GENERATED', 'Generated artifact; keep only if required by production or history policy'
    digest = sha256(p)
    if digest and len(duplicate_hashes.get(digest, [])) > 1:
        return 'REVIEW_DUPLICATE', 'Byte-identical duplicate exists: ' + ', '.join(x for x in duplicate_hashes[digest] if x != file)[:300]
    if name in archived_names and not file.startswith('.github/workflows-archive/'):
        return 'REVIEW', 'Filename also exists in archived workflow area'
    low = name.lower()
    if low.startswith(('patch_', 'repair_', 'tmp_', 'test_', 'qa_')):
        return 'REVIEW', 'Likely temporary patch/repair/QA utility; merge logic into canonical pipeline or archive'
    if re.search(r'(v\d+|phase\d+|sprint\d+|legacy|old|backup|copy)', low):
        return 'REVIEW', 'Versioned/legacy naming suggests overlap or superseded implementation'
    if p.suffix == '.py':
        return 'REVIEW', 'Unreferenced Python script; confirm manual use before archive/delete'
    if p.suffix in {'.md', '.txt'}:
        return 'DOC', 'Documentation or operational note'
    return 'REVIEW', 'No active workflow/import reference found'


def main() -> None:
    files = git_files()
    wf_refs, wf_owners = workflow_references(files)
    py_refs, py_owners = python_dependencies(files)

    hashes: dict[str, list[str]] = defaultdict(list)
    for file in files:
        digest = sha256(Path(file))
        if digest:
            hashes[digest].append(file)

    archived_names = {p.name for p in ARCHIVED_WORKFLOWS.glob('*')} if ARCHIVED_WORKFLOWS.exists() else set()
    rows = []
    counts = defaultdict(int)
    for file in files:
        category, reason = classify(file, wf_refs, py_refs, hashes, archived_names)
        counts[category] += 1
        path = Path(file)
        rows.append({
            'file': file,
            'category': category,
            'reason': reason,
            'size_bytes': path.stat().st_size if path.exists() else 0,
            'active_workflow_owners': '; '.join(sorted(wf_owners.get(file, set()))),
            'python_owners': '; '.join(sorted(py_owners.get(file, set()))),
            'sha256': sha256(path),
        })

    rows.sort(key=lambda r: (r['category'], r['file']))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()

    with (REPORT_DIR / 'repository_file_audit.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    payload = {'generated_at_utc': stamp, 'summary': dict(sorted(counts.items())), 'files': rows}
    (REPORT_DIR / 'repository_file_audit.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')

    priority = [r for r in rows if r['category'] in {'REVIEW', 'REVIEW_DUPLICATE'}]
    md = [
        '# WNBA Repository File Audit', '',
        f'Generated: `{stamp}`', '',
        '## Summary', '',
    ]
    for key, value in sorted(counts.items()):
        md.append(f'- **{key}:** {value}')
    md += ['', '## Cleanup interpretation', '',
           '- **KEEP:** active production dependency or canonical infrastructure.',
           '- **GENERATED:** output data. Retention should be governed by a clear current/history policy.',
           '- **ARCHIVE:** intentionally non-production.',
           '- **REVIEW / REVIEW_DUPLICATE:** strongest cleanup candidates. Do not delete until ownership and history needs are confirmed.',
           '', '## Highest-priority review candidates', '']
    for row in priority[:150]:
        md.append(f"- `{row['file']}` — {row['reason']}")
    md += ['', '## Recommended cleanup order', '',
           '1. Resolve byte-identical duplicates.',
           '2. Merge active patch/repair logic into canonical builders.',
           '3. Archive unreferenced versioned scripts and old sprint/phase workflows.',
           '4. Define retention for generated current-state versus historical data.',
           '5. Delete only after one full daily refresh, hourly refresh, grading, and deployment test passes without the candidate files.', '']
    (REPORT_DIR / 'REPOSITORY_FILE_AUDIT.md').write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps(payload['summary'], indent=2))
    print(f'Audited {len(rows)} tracked files')


if __name__ == '__main__':
    main()
