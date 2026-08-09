from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('data/dashboard')
MASTER = ROOT / 'wnba_master.json'
V5_BUY = ROOT / 'wnba_v5_buy_signals.json'
OUT = ROOT / 'wnba_best_bets.json'


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', dest='target_date')
    args = parser.parse_args()

    master = load_json(MASTER)
    source = load_json(V5_BUY)
    target = args.target_date or str(source.get('injury_target_date') or master.get('target_date') or '')
    signals = [x for x in source.get('signals', []) if isinstance(x, dict)]

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in signals:
        item_date = str(item.get('date') or target)
        if target and item_date and item_date != target:
            continue
        state = str(item.get('decision_state') or item.get('type') or '').upper()
        if state not in {'BUY_NOW', 'BUY_BEFORE_MOVE'}:
            continue
        injury_status = str(item.get('injury_status') or 'ACTIVE').upper()
        if injury_status in {'OUT', 'DOUBTFUL'}:
            continue
        identity = str(item.get('ranking_key') or '|'.join(str(item.get(k) or '') for k in ('date','player','game','market','side','line')))
        if identity in seen:
            continue
        seen.add(identity)
        selected.append({
            **item,
            'target_date': target,
            'status': 'BET',
            'recommendation': state,
            'qualification': 'v5_live_buy_signal',
            'source': 'wnba_v5_buy_signals.json',
        })

    selected.sort(key=lambda x: (float(x.get('expected_value') or -999), float(x.get('edge') or -999)), reverse=True)
    payload = {
        'schema_version': 2,
        'target_date': target,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_generated_at_utc': source.get('generated_at_utc'),
        'source': 'data/dashboard/wnba_v5_buy_signals.json',
        'research_only': bool(source.get('research_only', True)),
        'status': 'ready' if selected else 'no_qualified_bets',
        'bet_count': len(selected),
        'best_bets': selected,
        'message': None if selected else 'No current V5 live buy signals qualified for the active slate.',
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps({'target_date': target, 'bet_count': len(selected), 'source': str(V5_BUY), 'output': str(OUT)}, indent=2))


if __name__ == '__main__':
    main()
