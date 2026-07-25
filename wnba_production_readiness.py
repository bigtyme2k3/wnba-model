from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DASH = ROOT / 'data' / 'dashboard'
WARE = ROOT / 'data' / 'warehouse'
OUTS = [DASH / 'wnba_production_readiness.json', WARE / 'wnba_production_readiness.json']

FILES = {
    'qa': DASH / 'wnba_v4_qa.json',
    'pipeline_readiness': DASH / 'wnba_pipeline_readiness.json',
    'pipeline': DASH / 'wnba_autonomous_pipeline.json',
    'final_qa': DASH / 'wnba_final_qa.json',
    'forward_validation': DASH / 'wnba_forward_validation.json',
    'daily_edges': DASH / 'wnba_daily_edges.json',
    'ensemble': DASH / 'wnba_ensemble_intelligence.json',
    'simulation': DASH / 'wnba_monte_carlo_scenarios.json',
}


def load(path: Path) -> Any:
    try:
        return json.load(path.open(encoding='utf-8')) if path.exists() else {}
    except Exception:
        return {}


def status_of(payload: Any) -> str:
    if not isinstance(payload, dict):
        return 'MISSING'
    return str(payload.get('status') or payload.get('readiness') or 'UNKNOWN').upper()


def count_rows(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    for key in ('ranked_edges','top_edges','all_simulations','simulations','predictions','rows','records','items'):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    summary = payload.get('summary') if isinstance(payload.get('summary'), dict) else {}
    for key in ('candidates_ranked','candidates_scored','candidates_simulated','frozen_predictions','records'):
        if summary.get(key) is not None:
            try: return int(summary[key])
            except Exception: pass
    return 0


def validation_db_check() -> dict[str, Any]:
    path = WARE / 'wnba_forward_validation.sqlite'
    result = {'exists': path.exists(), 'integrity': 'missing', 'records': 0, 'duplicates': 0, 'chronology_violations': 0}
    if not path.exists():
        return result
    try:
        con = sqlite3.connect(path)
        result['integrity'] = con.execute('PRAGMA integrity_check').fetchone()[0]
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        table = next((t for t in ('forward_predictions','predictions','frozen_predictions') if t in tables), None)
        if table:
            cols = {r[1] for r in con.execute(f'PRAGMA table_info({table})')}
            result['records'] = con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            id_col = next((c for c in ('prediction_id','snapshot_id','id') if c in cols), None)
            if id_col:
                result['duplicates'] = con.execute(f'SELECT COUNT(*)-COUNT(DISTINCT {id_col}) FROM {table}').fetchone()[0]
            freeze_col = next((c for c in ('frozen_at_utc','freeze_time_utc','created_at_utc') if c in cols), None)
            start_col = next((c for c in ('game_start_utc','commence_time','start_time_utc') if c in cols), None)
            if freeze_col and start_col:
                result['chronology_violations'] = con.execute(f'SELECT COUNT(*) FROM {table} WHERE {freeze_col} IS NOT NULL AND {start_col} IS NOT NULL AND {freeze_col}>={start_col}').fetchone()[0]
        con.close()
    except Exception as exc:
        result['integrity'] = f'error: {exc}'
    return result


def build() -> dict[str, Any]:
    p = {name: load(path) for name, path in FILES.items()}
    readiness = status_of(p['pipeline_readiness'])
    offday = readiness in {'WAIT','OFFDAY','NO_SLATE'}
    qa_summary = p['qa'].get('summary', {}) if isinstance(p['qa'], dict) else {}
    db = validation_db_check()

    gates = []
    def gate(name: str, passed: bool, detail: str, critical: bool = True) -> None:
        gates.append({'name': name, 'passed': bool(passed), 'detail': detail, 'critical': critical})

    gate('module_health', qa_summary.get('red_modules', 0) == 0, f"red modules={qa_summary.get('red_modules', 0)}")
    gate('json_integrity', qa_summary.get('invalid_json_files', 0) == 0, f"invalid JSON={qa_summary.get('invalid_json_files', 0)}")
    gate('forward_validation_integrity', db['integrity'] in {'ok','missing'}, f"integrity={db['integrity']}")
    gate('forward_validation_uniqueness', db['duplicates'] == 0, f"duplicates={db['duplicates']}")
    gate('forward_validation_chronology', db['chronology_violations'] == 0, f"violations={db['chronology_violations']}")
    gate('calibration_available', (DASH / 'wnba_adaptive_confidence.json').exists(), 'Sprint 8.1 calibration file')
    gate('dashboard_available', (ROOT / 'docs' / 'index.html').exists(), 'docs/index.html')

    live_counts = {name: count_rows(p[name]) for name in ('daily_edges','ensemble','simulation')}
    if offday:
        gate('live_slate_inputs', True, f'{readiness}: live outputs may be empty', critical=False)
    else:
        gate('daily_edges_available', live_counts['daily_edges'] > 0, f"daily edges={live_counts['daily_edges']}")
        gate('ensemble_coverage', live_counts['ensemble'] > 0 and live_counts['ensemble'] <= live_counts['daily_edges'], f"ensemble={live_counts['ensemble']}, edges={live_counts['daily_edges']}")
        gate('simulation_coverage', live_counts['simulation'] > 0 and live_counts['simulation'] <= live_counts['ensemble'], f"simulation={live_counts['simulation']}, ensemble={live_counts['ensemble']}")

    failed_critical = [g for g in gates if g['critical'] and not g['passed']]
    failed_advisory = [g for g in gates if not g['critical'] and not g['passed']]
    if failed_critical:
        status = 'BLOCKED'
        ready_for_live_slate = False
    elif offday:
        status = 'STANDBY'
        ready_for_live_slate = True
    else:
        status = 'READY'
        ready_for_live_slate = True

    report = {
        'sprint': 13,
        'phase': 'production-readiness',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': status,
        'ready_for_live_slate': ready_for_live_slate,
        'operating_context': {'pipeline_readiness': readiness, 'offday_or_break': offday},
        'summary': {
            'gates': len(gates),
            'passed': sum(g['passed'] for g in gates),
            'failed_critical': len(failed_critical),
            'failed_advisory': len(failed_advisory),
            'daily_edges': live_counts['daily_edges'],
            'ensemble': live_counts['ensemble'],
            'simulations': live_counts['simulation'],
            'forward_validation_records': db['records'],
        },
        'gates': gates,
        'forward_validation_database': db,
        'release_blockers': [g['detail'] for g in failed_critical],
        'message': 'READY FOR LIVE SLATE' if ready_for_live_slate else 'PRODUCTION BLOCKED',
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open('w', encoding='utf-8'), indent=2, allow_nan=False)
    print(json.dumps(report['summary'] | {'status': status, 'ready_for_live_slate': ready_for_live_slate}, indent=2))
    return report


if __name__ == '__main__':
    build()
