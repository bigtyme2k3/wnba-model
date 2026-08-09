from __future__ import annotations
import argparse, json, os
from datetime import date, datetime, timezone


def load(p, d):
    try:
        if os.path.exists(p):
            return json.load(open(p, encoding='utf-8'))
    except Exception:
        pass
    return d


def build(target):
    live_port = load('data/dashboard/wnba_v5_live_portfolio.json', {})
    live_decisions = load('data/dashboard/wnba_v5_live_decisions.json', {})
    injury = load('data/dashboard/wnba_injury_intelligence.json', {})

    portfolio = [x for x in live_port.get('portfolio', []) if isinstance(x, dict)]
    decisions = [x for x in live_decisions.get('decisions', []) if isinstance(x, dict)]
    report_meta = live_decisions.get('report', {}) if isinstance(live_decisions.get('report'), dict) else {}

    report = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': target,
        'source': 'wnba_v5_live_portfolio.json',
        'decision_source': 'wnba_v5_live_decisions.json',
        'injury_target_date': live_port.get('injury_target_date') or report_meta.get('injury_target_date') or injury.get('target_date'),
        'research_only': bool(live_port.get('research_only', True)),
        'summary': {
            'portfolio_rows': len(portfolio),
            'total_units': live_port.get('total_units', 0.0),
            'decision_rows': len(decisions),
            'actionable_rows': report_meta.get('actionable_rows', sum(1 for x in decisions if x.get('decision_state') in {'BUY_NOW','BUY_BEFORE_MOVE'})),
            'injury_blocked_rows': report_meta.get('injury_blocked_rows', 0),
            'injury_limited_rows': report_meta.get('injury_limited_rows', 0),
            'actionable_out_rows': report_meta.get('actionable_out_rows', 0),
        },
        'recommended_card': portfolio,
        'portfolio': portfolio,
        'decisions': decisions,
    }
    os.makedirs('data/warehouse', exist_ok=True)
    os.makedirs('data/dashboard', exist_ok=True)
    for p in ['data/warehouse/wnba_portfolio_dashboard.json', 'data/dashboard/wnba_portfolio_dashboard.json']:
        json.dump(report, open(p, 'w', encoding='utf-8'), indent=2)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=str(date.today()))
    args = ap.parse_args()
    print('Portfolio dashboard built:', build(args.date)['summary'])


if __name__ == '__main__':
    main()
