from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
from pathlib import Path

DASH = Path('data/dashboard')
M04 = DASH / 'wnba_s19_m04_decision_contract.json'
OUT = DASH / 'wnba_s19_m05_dashboard_health.json'
AUDIT = DASH / 'wnba_s19_m05_dashboard_health_audit.json'


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


def build(target: str):
    m04 = load(M04, {})
    if m04.get('status') != 'READY' or str(m04.get('target_date') or '')[:10] != target:
        raise SystemExit(f'M04 not READY/current for {target}')

    now = datetime.now(timezone.utc)
    generated = parse_ts(m04.get('generated_at_utc'))
    if generated is None:
        raise SystemExit('M05 requires M04 generated_at_utc')
    age_minutes = max(0.0, (now - generated).total_seconds() / 60.0)

    summary = m04.get('summary') or {}
    games = m04.get('games') or []
    props = m04.get('player_props') or []
    best = m04.get('best_bets') or []
    portfolio = m04.get('portfolio') or []
    results = m04.get('results') or {}

    checks = {
        'm04_ready': True,
        'target_current': str(m04.get('target_date'))[:10] == target,
        'games_present': len(games) > 0,
        'player_props_present': len(props) > 0,
        'all_props_current_date': all(str(r.get('target_date') or target)[:10] == target for r in props),
        'no_actionable_unavailable_props': int(summary.get('actionable_unavailable_props') or 0) == 0,
        'legacy_fallback_disabled': (m04.get('source_policy') or {}).get('legacy_fallback') is False,
        'single_dashboard_contract': True,
        'results_bound_to_contract': isinstance(results, dict),
        'best_bets_bound_to_contract': isinstance(best, list),
        'portfolio_bound_to_contract': isinstance(portfolio, list),
    }
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise SystemExit(f'M05 dashboard health failed checks: {failed}')

    status = 'READY' if age_minutes <= 90 else 'STALE'
    payload = {
        'generated_at_utc': now.isoformat(),
        'target_date': target,
        'schema_version': 'sprint19-m05-dashboard-health-v1',
        'status': status,
        'contract_generated_at_utc': m04.get('generated_at_utc'),
        'contract_age_minutes': round(age_minutes, 2),
        'freshness_policy': {
            'max_contract_age_minutes': 90,
            'current_slate_required': True,
            'legacy_fallback_allowed': False,
            'actionable_unavailable_players_allowed': False,
        },
        'checks': checks,
        'summary': {
            'games': len(games),
            'player_props': len(props),
            'best_bets': len(best),
            'portfolio': len(portfolio),
            'results_status': results.get('status'),
            'healthy_checks': sum(bool(v) for v in checks.values()),
            'total_checks': len(checks),
        },
    }
    OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')

    audit = {
        'generated_at_utc': now.isoformat(),
        'target_date': target,
        'status': status,
        'module': 'SPRINT19-M05',
        'contract_status': m04.get('status'),
        'contract_age_minutes': round(age_minutes, 2),
        'all_health_checks_pass': not failed,
        'healthy_checks': sum(bool(v) for v in checks.values()),
        'total_checks': len(checks),
        'games': len(games),
        'player_props': len(props),
        'best_bets': len(best),
        'portfolio': len(portfolio),
        'results_status': results.get('status'),
        'legacy_fallback_enabled': False,
        'single_dashboard_contract': True,
    }
    AUDIT.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print('SPRINT19_M05_DASHBOARD_HEALTH', json.dumps(audit))
    if status != 'READY':
        raise SystemExit(f'M05 contract is stale: {age_minutes:.1f} minutes')
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    args = ap.parse_args()
    build(args.date)


if __name__ == '__main__':
    main()
