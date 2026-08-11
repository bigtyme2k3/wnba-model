from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wnba_game_predictions_ledger as ledger

RAW = ROOT / 'data/raw'


def score_files() -> list[Path]:
    """Use every persisted final-score source, newest/date-specific files included."""
    candidates = [RAW / 'scores.csv', RAW / 'scores_historical.csv']
    candidates.extend(sorted(RAW.glob('scores_????-??-??.csv')))
    seen = set()
    out = []
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if path.exists() and key not in seen:
            seen.add(key)
            out.append(path)
    return out


def parse_date(value: str):
    try:
        return datetime.strptime(str(value or '')[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def score_index():
    exact = {}
    by_matchup = {}
    files_used = []
    for path in score_files():
        used = 0
        try:
            handle = path.open(encoding='utf-8-sig', newline='')
        except Exception:
            continue
        with handle:
            for row in csv.DictReader(handle):
                if str(row.get('is_final')).lower() not in {'true', '1'} and 'FINAL' not in str(row.get('status') or '').upper():
                    continue
                game_date = str(row.get('game_date') or '')[:10]
                away = ledger.norm(row.get('away_team'))
                home = ledger.norm(row.get('home_team'))
                if not game_date or not away or not home:
                    continue
                row = dict(row)
                row['_score_source'] = str(path.relative_to(ROOT))
                exact[(game_date, away, home)] = row
                by_matchup.setdefault((away, home), []).append(row)
                used += 1
        if used:
            files_used.append({'path': str(path.relative_to(ROOT)), 'final_rows': used})
    return exact, by_matchup, files_used


def find_actual(exact, by_matchup, target_date: str, away: str, home: str):
    actual = exact.get((target_date, away, home))
    if actual:
        return actual, 'exact_date'

    # Some evening WNBA games are persisted by upstream score feeds on the next
    # UTC calendar date even though the betting slate is the prior local date.
    # Only allow a one-day fallback for the exact same away/home matchup.
    target = parse_date(target_date)
    if target is None:
        return None, None
    candidates = []
    for row in by_matchup.get((away, home), []):
        actual_date = parse_date(row.get('game_date'))
        if actual_date is None:
            continue
        delta = abs((actual_date - target).days)
        if delta <= 1:
            candidates.append((delta, actual_date, row))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0], item[1]))
    best_delta = candidates[0][0]
    best = [item for item in candidates if item[0] == best_delta]
    if len(best) != 1:
        return None, None
    return best[0][2], 'adjacent_date' if best_delta else 'exact_date'


def main():
    rows = ledger.read_ledger()
    exact, by_matchup, files_used = score_index()
    graded = 0
    unresolved = 0
    adjacent_matches = 0
    source_counts = {}

    for row in rows:
        if row.get('graded'):
            continue
        target_date = str(row.get('target_date') or '')[:10]
        away = ledger.norm(row.get('away_team'))
        home = ledger.norm(row.get('home_team'))
        actual, match_mode = find_actual(exact, by_matchup, target_date, away, home)
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
        source = actual.get('_score_source') or 'score_file'
        source_counts[source] = source_counts.get(source, 0) + 1
        if match_mode == 'adjacent_date':
            adjacent_matches += 1
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
            'actual_source': source,
            'actual_game_date': str(actual.get('game_date') or '')[:10],
            'actual_match_mode': match_mode,
        })
        graded += 1

    ledger.write_ledger(rows)
    report = ledger.build_report(rows, datetime.now(timezone.utc).date().isoformat(), {
        'historical_backfill_graded': graded,
        'historical_backfill_unresolved': unresolved,
        'historical_backfill_adjacent_date_matches': adjacent_matches,
        'historical_score_files_used': files_used,
        'historical_grade_source_counts': source_counts,
    })
    print(json.dumps({
        'status': 'PASS',
        'archived_games': len(rows),
        'graded_games': sum(bool(r.get('graded')) for r in rows),
        'graded_this_backfill': graded,
        'unresolved_pending': unresolved,
        'adjacent_date_matches': adjacent_matches,
        'score_files_used': len(files_used),
        'grade_source_counts': source_counts,
        'spread_record': report.get('summary', {}).get('spread_record'),
        'total_record': report.get('summary', {}).get('total_record'),
    }))


if __name__ == '__main__':
    main()
