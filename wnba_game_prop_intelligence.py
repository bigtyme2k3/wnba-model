from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('data/dashboard')
MASTER = ROOT / 'wnba_master.json'
OUT = ROOT / 'wnba_game_prop_intelligence.json'
OUT_ALIAS = ROOT / 'wnba_game_props.json'


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {}


def first_number(source: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = source.get(key)
        try:
            if value not in (None, '', '-'):
                return float(value)
        except (TypeError, ValueError):
            pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', dest='target_date')
    args = parser.parse_args()

    master = load_json(MASTER)
    target = args.target_date or str(master.get('target_date') or '')
    games = [g for g in master.get('games', []) if isinstance(g, dict)]
    today = [g for g in games if str(g.get('bucket', '')).lower() == 'today']

    rows: list[dict[str, Any]] = []
    for game in today:
        matchup = str(game.get('game') or game.get('matchup') or '').strip()
        if not matchup:
            continue
        market = game.get('market') if isinstance(game.get('market'), dict) else {}
        odds = game.get('odds') if isinstance(game.get('odds'), dict) else {}
        combined = {**game, **market, **odds}
        spread = first_number(combined, ('spread', 'book_spread', 'consensus_spread', 'home_spread'))
        total = first_number(combined, ('total', 'book_total', 'consensus_total', 'over_under'))
        moneyline = combined.get('moneyline') or combined.get('moneylines') or {}
        rows.append({
            'game': matchup,
            'game_id': game.get('game_id') or game.get('id'),
            'target_date': target,
            'status': game.get('status') or 'scheduled',
            'spread': spread,
            'total': total,
            'moneyline': moneyline,
            'recommendation_status': 'available' if spread is not None or total is not None or moneyline else 'market_pending',
            'source': 'wnba_master.json',
        })

    payload = {
        'schema_version': 1,
        'target_date': target,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'game_count': len(rows),
        'games': rows,
        'status': 'ready' if rows else 'no_current_games',
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    OUT.write_text(text, encoding='utf-8')
    OUT_ALIAS.write_text(text, encoding='utf-8')
    print(json.dumps({'target_date': target, 'game_count': len(rows), 'outputs': [str(OUT), str(OUT_ALIAS)]}, indent=2))


if __name__ == '__main__':
    main()
