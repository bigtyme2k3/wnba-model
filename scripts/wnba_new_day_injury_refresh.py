from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RAW = Path('data/raw')
DASH = Path('data/dashboard')
WARE = Path('data/warehouse')


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print('+', ' '.join(cmd), flush=True)
    return subprocess.run(cmd, check=check)


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def ensure_empty_current_injury_files(target: str) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    columns = ['game_date','team','player','player_id','position','status','severity','injury_type','detail','return_date','is_out','source','scraped_at']
    for path in (RAW / 'injuries_today.csv', RAW / f'injuries_{target}.csv'):
        with path.open('w', encoding='utf-8', newline='') as handle:
            csv.DictWriter(handle, fieldnames=columns).writeheader()
    now = datetime.now(timezone.utc).isoformat()
    status = {
        'status': 'no_report_yet',
        'target_date': target,
        'rows': 0,
        'out': 0,
        'questionable': 0,
        'probable': 0,
        'generated_at_utc': now,
        'completed_at_utc': now,
        'sources': [],
        'primary_source': 'no_report_yet',
        'source_url': None,
        'teams_checked': 0,
        'coverage_verified': False,
        'safety_policy': 'Predictions may render, but no BET action may be published until a verified injury source is available.',
    }
    (RAW / 'injuries_status.json').write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')


def annotate_intelligence(target: str) -> dict:
    status = load(RAW / 'injuries_status.json', {})
    verified = bool(int(status.get('rows') or 0) > 0 and status.get('primary_source') in {'official_wnba_pdf','espn_fallback'})
    if status.get('primary_source') == 'official_wnba_pdf':
        verified = True
    coverage = 'VERIFIED' if verified else 'UNVERIFIED_NO_REPORT_YET'
    for path in (DASH / 'wnba_injury_intelligence.json', WARE / 'wnba_injury_intelligence.json'):
        payload = load(path, {})
        if not payload:
            continue
        payload['target_date'] = target
        payload['source_coverage'] = coverage
        payload['injury_source_verified'] = verified
        payload['injury_source_status'] = status
        path.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return {'target_date': target, 'coverage': coverage, 'verified': verified, 'rows': int(status.get('rows') or 0), 'primary_source': status.get('primary_source')}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    args = ap.parse_args()
    target = args.date

    proc = run(['python','scrape_official_wnba_injuries.py','--date',target,'--out','data/raw'], check=False)
    status = load(RAW / 'injuries_status.json', {})
    current = str(status.get('target_date') or '')[:10] == target
    zero_rows = int(status.get('rows') or 0) == 0
    if proc.returncode != 0:
        if current and zero_rows:
            print('No verified injury rows are published yet; creating a current-date non-actionable injury state.')
            ensure_empty_current_injury_files(target)
        else:
            raise SystemExit(proc.returncode)

    run(['python','wnba_injury_intelligence.py','--date',target])
    run(['python','wnba_injury_rotation_guard.py'])
    report = annotate_intelligence(target)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
