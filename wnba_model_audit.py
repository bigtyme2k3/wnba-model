from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('.')
DASH = ROOT / 'data' / 'dashboard'
WARE = ROOT / 'data' / 'warehouse'
OUTS = [DASH / 'wnba_model_audit.json', WARE / 'wnba_model_audit.json']

CRITICAL_FILES = {
    'master': DASH / 'wnba_master.json',
    'daily_edges': DASH / 'wnba_daily_edges.json',
    'alt_markets': DASH / 'wnba_alt_market_warehouse.json',
    'alt_streaks': DASH / 'wnba_alt_streaks.json',
    'player_logs': WARE / 'wnba_player_game_logs.json',
    'betting_intelligence': DASH / 'wnba_betting_intelligence.json',
    'player_prop_intelligence': DASH / 'wnba_player_prop_intelligence.json',
    'warehouse_v2': WARE / 'wnba_odds_warehouse_v2.sqlite',
}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def list_rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def dup_count(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> int:
    seen: set[tuple[str, ...]] = set()
    dup = 0
    for row in rows:
        key = tuple(str(row.get(f) or '').strip().lower() for f in fields)
        if not any(key):
            continue
        if key in seen:
            dup += 1
        else:
            seen.add(key)
    return dup


def sqlite_health(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {'exists': path.exists(), 'tables': {}, 'integrity': None}
    if not path.exists():
        return result
    try:
        con = sqlite3.connect(path)
        result['integrity'] = con.execute('PRAGMA integrity_check').fetchone()[0]
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            try:
                result['tables'][table] = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            except Exception:
                result['tables'][table] = None
        con.close()
    except Exception as exc:
        result['error'] = str(exc)
    return result


def main() -> None:
    master = load(CRITICAL_FILES['master'], {})
    props = list_rows(master, 'props')
    games = list_rows(master, 'games')
    alt = load(CRITICAL_FILES['alt_markets'], {})
    alt_rows = list_rows(alt, 'rows', 'markets')
    streaks = load(CRITICAL_FILES['alt_streaks'], {})
    streak_rows = list_rows(streaks, 'rows')
    logs = load(CRITICAL_FILES['player_logs'], {})
    log_rows = list_rows(logs, 'records', 'rows')
    edges = load(CRITICAL_FILES['daily_edges'], {})
    edge_rows = list_rows(edges, 'top_edges')

    files = {}
    for name, path in CRITICAL_FILES.items():
        files[name] = {
            'path': str(path),
            'exists': path.exists(),
            'size_bytes': path.stat().st_size if path.exists() else 0,
            'modified_utc': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if path.exists() else None,
        }

    duplicates = {
        'games': dup_count(games, ('game_id', 'game_date', 'home_team', 'away_team')),
        'props': dup_count(props, ('player', 'stat', 'line', 'game', 'book')),
        'alt_markets': dup_count(alt_rows, ('player', 'stat', 'line', 'threshold', 'side', 'book', 'sportsbook')),
        'alt_streaks': dup_count(streak_rows, ('player', 'stat', 'alt_line', 'side', 'best_book')),
        'player_logs': dup_count(log_rows, ('player', 'game_date', 'game_id')),
        'daily_edges': dup_count(edge_rows, ('player', 'market', 'line', 'side', 'sportsbook')),
    }

    counts = {
        'games': len(games),
        'today_games': sum(g.get('bucket') == 'today' for g in games),
        'props': len(props),
        'alt_markets': len(alt_rows),
        'alt_streaks': len(streak_rows),
        'player_logs': len(log_rows),
        'daily_edges': len(edge_rows),
    }

    checks = {
        'critical_files_present': all(v['exists'] for v in files.values()),
        'warehouse_integrity_ok': False,
        'no_duplicate_games': duplicates['games'] == 0,
        'no_duplicate_player_logs': duplicates['player_logs'] == 0,
        'alt_pipeline_populated': counts['alt_markets'] > 0 and counts['alt_streaks'] > 0,
        'player_history_populated': counts['player_logs'] > 0,
        'daily_edges_ready': counts['today_games'] > 0 and counts['props'] + counts['alt_markets'] > 0,
    }

    db = sqlite_health(CRITICAL_FILES['warehouse_v2'])
    checks['warehouse_integrity_ok'] = db.get('integrity') == 'ok'

    warnings = []
    if counts['today_games'] == 0:
        warnings.append('No active regular-season slate; preserve last valid live report during All-Star break.')
    for name, value in duplicates.items():
        if value:
            warnings.append(f'{name}: {value} duplicate rows detected.')
    if not checks['critical_files_present']:
        warnings.append('One or more critical data products are missing.')

    status = 'healthy' if all(v for k, v in checks.items() if k != 'daily_edges_ready') and not warnings else 'attention'
    report = {
        'phase': 'all-star-model-audit',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': status,
        'counts': counts,
        'duplicates': duplicates,
        'checks': checks,
        'files': files,
        'warehouse': db,
        'warnings': warnings,
        'next_actions': [
            'Resolve duplicate and missing-data findings before calibration.',
            'Freeze live-edge overwrite when no active regular-season slate exists.',
            'Run historical confidence calibration after audit findings are cleared.',
        ],
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open('w', encoding='utf-8'), indent=2, allow_nan=False)
    print(json.dumps({'status': status, 'counts': counts, 'duplicates': duplicates, 'warnings': warnings}, indent=2))


if __name__ == '__main__':
    main()
