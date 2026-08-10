from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wnba_game_predictions_ledger as ledger

SCORES = ROOT / 'data/raw/scores_historical.csv'


def score_index():
    out = {}
    if not SCORES.exists():
        return out
    with SCORES.open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            if str(row.get('is_final')).lower() not in {'true', '1'} and 'FINAL' not in str(row.get('status') or '').upper():
                continue
            date = str(row.get('game_date') or '')[:10]
            away = ledger.norm(row.get('away_team'))
            home = ledger.norm(row.get('home_team'))
            if date and away and home:
                out[(date, away, home)] = row
    return out


def main():
    rows = ledger.read_ledger()
    scores = score_index()
    graded = 0
    unresolved = 0
    for row in rows:
        if row.get('graded'):
            continue
        date = str(row.get('target_date') or '')[:10]
        away = ledger.norm(row.get('away_team'))
        home = ledger.norm(row.get('home_team'))
        actual = scores.get((date, away, home))
        if not actual:
            unresolved += 1
            continue
        a = ledger.num(actual.get('away_score'))
        h = ledger.num(actual.get('home_score'))
        if a is None or h is None:
            unresolved += 1
            continue
        pm = ledger.num(row.get('projected_margin'))
        pt = ledger.num(row.get('projected_total'))
        row.update({
            'actual_away_score': a,
            'actual_home_score': h,
            'actual_margin': round(h-a, 2),
            'actual_total': round(h+a, 2),
            'margin_error': round(abs(pm-(h-a)), 2) if pm is not None else None,
            'total_error': round(abs(pt-(h+a)), 2) if pt is not None else None,
            'spread_result': ledger.grade_spread(row, a, h),
            'total_result': ledger.grade_total(row, a, h),
            'graded': True,
            'status': 'GRADED',
            'graded_at_utc': datetime.now(timezone.utc).isoformat(),
            'actual_source': 'scores_historical.csv',
        })
        graded += 1
    ledger.write_ledger(rows)
    report = ledger.build_report(rows, datetime.now(timezone.utc).date().isoformat(), {
        'historical_backfill_graded': graded,
        'historical_backfill_unresolved': unresolved,
    })
    print(json.dumps({
        'status': 'PASS',
        'archived_games': len(rows),
        'graded_games': sum(bool(r.get('graded')) for r in rows),
        'graded_this_backfill': graded,
        'unresolved_pending': unresolved,
        'spread_record': report.get('summary', {}).get('spread_record'),
        'total_record': report.get('summary', {}).get('total_record'),
    }))


if __name__ == '__main__':
    main()
