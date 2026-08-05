from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('data/dashboard')
MASTER = ROOT / 'wnba_master.json'
EDGES = ROOT / 'wnba_daily_edges.json'
EDGES_ALT = ROOT / 'wnba_daily_edge_engine.json'
PLAYER = ROOT / 'wnba_player_prop_intelligence.json'
GAME = ROOT / 'wnba_game_prop_intelligence.json'
OUT = ROOT / 'wnba_best_bets.json'


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {}


def collect_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ('best_bets', 'bets', 'plays', 'recommendations', 'edges', 'candidates'):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def numeric(record: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = record.get(key)
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
    allowed_games = {
        str(g.get('game') or g.get('matchup') or '').strip()
        for g in master.get('games', [])
        if isinstance(g, dict) and str(g.get('bucket', '')).lower() == 'today'
    }

    sources = [load_json(EDGES), load_json(EDGES_ALT), load_json(PLAYER), load_json(GAME)]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        for item in collect_candidates(source):
            game = str(item.get('game') or item.get('matchup') or '').strip()
            if game and allowed_games and game not in allowed_games:
                continue
            edge = numeric(item, ('edge', 'edge_pct', 'expected_value', 'ev', 'model_edge'))
            confidence = numeric(item, ('confidence', 'confidence_pct', 'probability', 'win_probability'))
            status = str(item.get('status') or item.get('recommendation') or '').lower()
            qualifies = (edge is not None and edge > 0) or status in {'bet', 'play', 'recommended', 'qualified'}
            if not qualifies:
                continue
            identity = '|'.join(str(item.get(k) or '') for k in ('game', 'player', 'market', 'selection', 'line'))
            if identity in seen:
                continue
            seen.add(identity)
            selected.append({
                **item,
                'game': game or item.get('game'),
                'edge': edge,
                'confidence': confidence,
                'target_date': target,
                'qualification': 'positive_edge_or_explicit_recommendation',
            })

    selected.sort(key=lambda x: (x.get('edge') is not None, x.get('edge') or -999), reverse=True)
    payload = {
        'schema_version': 1,
        'target_date': target,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': 'ready' if selected else 'no_qualified_bets',
        'bet_count': len(selected),
        'best_bets': selected,
        'message': None if selected else 'No current-slate bets met the positive-edge qualification rules.',
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps({'target_date': target, 'bet_count': len(selected), 'output': str(OUT)}, indent=2))


if __name__ == '__main__':
    main()
