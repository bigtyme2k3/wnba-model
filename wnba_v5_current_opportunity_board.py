"""Build the V5 live opportunity board from the canonical current player-prop slate.

This bridge intentionally uses only current-date market identity/price data. It does
not reuse legacy V4 probabilities, expected value, or stale Sprint 20 rankings.
M11 reconstructs its own V5 live features from certified historical outcomes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path('data/dashboard/wnba_player_props.json')
OUTS = [
    Path('data/warehouse/wnba_opportunity_rankings.json'),
    Path('data/dashboard/wnba_opportunity_rankings.json'),
]


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except Exception:
        return {}


def num(value):
    try:
        return float(value)
    except Exception:
        return None


def norm(value):
    return ' '.join(str(value or '').strip().lower().replace('’', "'").split())


def best_price(rows: list[dict]) -> dict | None:
    valid = [r for r in rows if num(r.get('price')) is not None]
    if not valid:
        return None
    # For American odds, the numerically larger price is always the better return
    # for the bettor: +120 > +110 and -105 > -120.
    return max(valid, key=lambda r: float(r['price']))


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = load(SOURCE)
    target = str(payload.get('target_date') or '')[:10]
    source_rows = payload.get('rows') if isinstance(payload.get('rows'), list) else []
    ranked: list[dict] = []

    for row in source_rows:
        if not isinstance(row, dict):
            continue
        player = str(row.get('player') or '').strip()
        stat = str(row.get('stat') or row.get('market') or '').upper().strip()
        game = str(row.get('game') or '').strip()
        line = num(row.get('line'))
        books = row.get('books') if isinstance(row.get('books'), list) else []
        if not target or not player or not stat or not game or line is None:
            continue
        for side in ('OVER', 'UNDER'):
            side_rows = [b for b in books if isinstance(b, dict) and str(b.get('side') or '').upper() == side]
            best = best_price(side_rows)
            if best is None:
                continue
            price = num(best.get('price'))
            book = str(best.get('book') or '').strip()
            key = '|'.join(norm(v) for v in (target, player, game, stat, side))
            ranked.append({
                'ranking_key': key,
                'date': target,
                'target_date': target,
                'generated_at_utc': now,
                'event_id': row.get('event_id'),
                'commence_time': row.get('commence_time'),
                'player': player,
                'team': row.get('team'),
                'game': game,
                'market': stat,
                'stat': stat,
                'side': side,
                'best_book': book,
                'best_line': line,
                'best_odds': price,
                'book_count': len(side_rows),
                'source': 'canonical_current_player_props',
                'research_only': True,
                'legacy_probability_reused': False,
            })

    ranked.sort(key=lambda r: (str(r.get('game')), str(r.get('player')), str(r.get('market')), str(r.get('side'))))
    for i, row in enumerate(ranked, 1):
        row['rank'] = i

    report = {
        'generated_at_utc': now,
        'target_date': target or None,
        'status': 'READY' if ranked else 'EMPTY',
        'source': str(SOURCE),
        'source_target_date': target or None,
        'summary': {
            'ranked_opportunities': len(ranked),
            'over_rows': sum(r['side'] == 'OVER' for r in ranked),
            'under_rows': sum(r['side'] == 'UNDER' for r in ranked),
            'players': len({norm(r['player']) for r in ranked}),
            'games': len({norm(r['game']) for r in ranked}),
        },
        'policy': {
            'current_market_identity_only': True,
            'legacy_v4_probability_reused': False,
            'legacy_sprint20_ev_reused': False,
            'm11_reconstructs_v5_features': True,
        },
        'top_opportunities': ranked[:50],
        'all_ranked': ranked,
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'target_date': report['target_date'], **report['summary']}))


if __name__ == '__main__':
    main()
