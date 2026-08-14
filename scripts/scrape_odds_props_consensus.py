from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scrape_odds_props as base


def american_to_prob(price):
    try:
        p = float(price)
    except Exception:
        return None
    if not math.isfinite(p) or (-100 < p < 100):
        return None
    return 100.0 / (p + 100.0) if p > 0 else (-p) / ((-p) + 100.0)


def prob_to_american(prob):
    try:
        p = float(prob)
    except Exception:
        return None
    if not 0 < p < 1:
        return None
    return round(100.0 * (1.0 - p) / p, 2) if p < 0.5 else round(-100.0 * p / (1.0 - p), 2)


def consensus_price(values):
    probs = [american_to_prob(v) for v in values]
    probs = [p for p in probs if p is not None]
    if not probs:
        return None
    return prob_to_american(sum(probs) / len(probs))


def parse_event_props(event_data: dict, target: str) -> list[dict]:
    if not event_data:
        return []
    event_id = event_data.get('id', '')
    home = event_data.get('home_team', '')
    away = event_data.get('away_team', '')
    game_time = event_data.get('commence_time', '')
    scraped_at = base.datetime.now(base.timezone.utc).isoformat()
    grouped = defaultdict(lambda: {'over_prices': [], 'under_prices': [], 'lines': [], 'books': set()})
    for book in event_data.get('bookmakers', []) or []:
        book_key = str(book.get('key') or '').lower()
        if book_key not in base.PLAYER_PROP_BOOKS:
            continue
        for market in book.get('markets', []) or []:
            mkey = market.get('key')
            stat = base.PROP_MARKETS.get(mkey)
            if not stat:
                continue
            for outcome in market.get('outcomes', []) or []:
                player = outcome.get('description') or outcome.get('name') or ''
                side = str(outcome.get('name', '')).lower()
                point = outcome.get('point')
                price = outcome.get('price')
                if not player or price is None or point is None:
                    continue
                try:
                    point_key = float(point)
                except Exception:
                    continue
                key = (player, mkey, stat, point_key)
                grouped[key]['lines'].append(point_key)
                grouped[key]['books'].add(book_key)
                if side == 'over':
                    grouped[key]['over_prices'].append(price)
                elif side == 'under':
                    grouped[key]['under_prices'].append(price)
    rows = []
    for (player, mkey, stat, point), info in grouped.items():
        rows.append({
            'game_date': target,
            'event_id': event_id,
            'player': player,
            'team': '',
            'position': '',
            'opp_team': f'{away} @ {home}',
            'is_home': '',
            'stat_raw': mkey,
            'stat': stat,
            'line': point,
            'over_price': consensus_price(info['over_prices']),
            'under_price': consensus_price(info['under_prices']),
            'yes_price': None,
            'no_price': None,
            'num_books': len(info['books']),
            'sportsbooks': ','.join(sorted(info['books'])),
            'odds_type': 'sportsbook_consensus_probability_space',
            'game_time': game_time,
            'home_team': home,
            'away_team': away,
            'source': 'the-odds-api',
            'scraped_at': scraped_at,
        })
    return rows


base.parse_event_props = parse_event_props

if __name__ == '__main__':
    base.main()
