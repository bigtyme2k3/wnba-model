from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
from pathlib import Path

DASH = Path('data/dashboard')
M03 = DASH / 'wnba_s19_m03_dashboard_consumer.json'
OUT = DASH / 'wnba_s19_m04_decision_contract.json'
AUDIT = DASH / 'wnba_s19_m04_decision_contract_audit.json'


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def row_date(row, target):
    return str(row.get('target_date') or row.get('date') or target)[:10]


def build(target: str):
    src = load(M03, {})
    if src.get('status') != 'READY' or str(src.get('target_date') or '')[:10] != target:
        raise SystemExit(f'M03 not READY/current for {target}')

    games = src.get('games') or []
    props = src.get('player_props') or []
    best = src.get('best_bets') or []
    portfolio = src.get('portfolio') or []
    results = src.get('results') or {}

    if not games or not props:
        raise SystemExit('M04 refuses an empty canonical game/prop contract')
    for name, rows in [('player_props', props), ('best_bets', best), ('portfolio', portfolio)]:
        off = [r for r in rows if row_date(r, target) != target]
        if off:
            raise SystemExit(f'M04 found {len(off)} off-date rows in {name}')

    unavailable = [r for r in props if str(r.get('injury_status') or '').upper() in {'OUT','DOUBTFUL'} and r.get('eligible')]
    if unavailable:
        raise SystemExit('M04 found actionable unavailable player props')

    generated = datetime.now(timezone.utc).isoformat()
    payload = {
        'generated_at_utc': generated,
        'target_date': target,
        'schema_version': 'sprint19-m04-dashboard-decision-contract-v1',
        'status': 'READY',
        'upstream_schema_version': src.get('schema_version'),
        'source_policy': {
            'canonical_source': 'wnba_s19_m03_dashboard_consumer.json',
            'legacy_fallback': False,
            'current_slate_only': True,
            'injury_guard_required': True,
        },
        'games': games,
        'player_props': props,
        'best_bets': best,
        'portfolio': portfolio,
        'results': results,
        'summary': {
            'games': len(games),
            'player_props': len(props),
            'actionable_player_props': sum(bool(r.get('eligible')) for r in props),
            'injury_adjusted_player_props': sum(bool(r.get('injury_adjusted')) for r in props),
            'best_bets': len(best),
            'portfolio': len(portfolio),
            'results_status': results.get('status'),
            'actionable_unavailable_props': 0,
        },
    }
    OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    audit = {
        'generated_at_utc': generated,
        'target_date': target,
        'status': 'READY',
        'module': 'SPRINT19-M04',
        'upstream_status': src.get('status'),
        'upstream_schema_version': src.get('schema_version'),
        'games': len(games),
        'player_props': len(props),
        'best_bets': len(best),
        'portfolio': len(portfolio),
        'results_status': results.get('status'),
        'all_rows_current_slate': True,
        'actionable_unavailable_props': 0,
        'legacy_fallback_enabled': False,
        'single_dashboard_contract': True,
    }
    AUDIT.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print('SPRINT19_M04_DECISION_CONTRACT_READY', json.dumps(audit))
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    args = ap.parse_args()
    build(args.date)


if __name__ == '__main__':
    main()
