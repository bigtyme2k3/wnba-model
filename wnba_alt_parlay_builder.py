from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('data/dashboard')
MARKETS = ROOT / 'wnba_alt_market_warehouse.json'
OUT = ROOT / 'wnba_alt_parlays.json'


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def dec_odds(american: Any) -> float | None:
    x = num(american)
    if x is None or x == 0:
        return None
    return 1 + 100 / -x if x < 0 else 1 + x / 100


def american_from_decimal(decimal: float) -> int:
    if decimal <= 1:
        return 0
    return round((decimal - 1) * 100) if decimal >= 2 else round(-100 / (decimal - 1))


def leg_score(r: dict[str, Any]) -> float:
    hp = num(r.get('historical_probability')) or 0.0
    l10 = num((r.get('l10') or {}).get('rate')) or hp
    l5 = num((r.get('l5') or {}).get('rate')) or hp
    ev = num(r.get('expected_value_per_unit')) or 0.0
    price = num(r.get('odds')) or -9999
    # Favor repeatable hit-rate evidence, then modest positive EV. Penalize
    # extreme juice and lottery prices because this product is for parlays.
    price_penalty = 0.0
    if price < -500:
        price_penalty = min(0.18, (-500 - price) / 5000)
    elif price > 180:
        price_penalty = min(0.18, (price - 180) / 2500)
    return 0.42 * hp + 0.28 * l10 + 0.20 * l5 + 0.10 * max(-0.25, min(0.35, ev)) - price_penalty


def eligible(r: dict[str, Any]) -> bool:
    if str(r.get('market_type') or '').lower() != 'alternate':
        return False
    if str(r.get('side') or '').upper() not in {'OVER', 'UNDER'}:
        return False
    if str(r.get('sportsbook') or '').lower() not in {'fanduel', 'draftkings', 'fanatics'}:
        return False
    hp = num(r.get('historical_probability'))
    odds = num(r.get('odds'))
    decisions = int((r.get('l10') or {}).get('decisions') or 0)
    return hp is not None and hp >= 0.58 and odds is not None and -1200 <= odds <= 500 and decisions >= 5


def candidate_pool(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Keep only the strongest threshold per player/stat/side/book to prevent
    # one player's ladder from flooding parlay construction.
    best: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for r in rows:
        if not eligible(r):
            continue
        key = (
            str(r.get('player') or '').lower(),
            str(r.get('stat') or '').upper(),
            str(r.get('side') or '').upper(),
            str(r.get('sportsbook') or '').lower(),
        )
        x = dict(r)
        x['_leg_score'] = round(leg_score(x), 6)
        prev = best.get(key)
        if prev is None or x['_leg_score'] > prev['_leg_score']:
            best[key] = x
    return sorted(best.values(), key=lambda x: x['_leg_score'], reverse=True)


def choose_legs(pool: list[dict[str, Any]], tier: str, offset: int = 0, leg_count: int = 3) -> list[dict[str, Any]]:
    if tier == 'SAFE':
        preferred = [r for r in pool if (num(r.get('historical_probability')) or 0) >= 0.72 and -900 <= (num(r.get('odds')) or -9999) <= -120]
    elif tier == 'BALANCED':
        preferred = [r for r in pool if (num(r.get('historical_probability')) or 0) >= 0.64 and -450 <= (num(r.get('odds')) or -9999) <= 130]
    else:
        preferred = [r for r in pool if (num(r.get('historical_probability')) or 0) >= 0.60 and -260 <= (num(r.get('odds')) or -9999) <= 220]
    if len(preferred) < leg_count:
        preferred = pool

    chosen: list[dict[str, Any]] = []
    used_players: set[str] = set()
    used_market_family: set[tuple[str, str]] = set()
    n = len(preferred)
    for i in range(n):
        r = preferred[(i + offset) % n]
        player = str(r.get('player') or '').lower()
        fam = (player, str(r.get('stat') or '').upper())
        if player in used_players or fam in used_market_family:
            continue
        chosen.append(r)
        used_players.add(player)
        used_market_family.add(fam)
        if len(chosen) >= leg_count:
            break
    return chosen


def parlay_record(kind: str, tier: str, label: str, legs: list[dict[str, Any]], games: list[str]) -> dict[str, Any] | None:
    if len(legs) < 2:
        return None
    dec = 1.0
    hist = 1.0
    for r in legs:
        d = dec_odds(r.get('odds'))
        hp = num(r.get('historical_probability'))
        if d is None or hp is None:
            return None
        dec *= d
        hist *= hp
    return {
        'parlay_id': '|'.join([kind, tier, label] + [str(r.get('market_id') or '') for r in legs]),
        'kind': kind,
        'tier': tier,
        'label': label,
        'games': games,
        'leg_count': len(legs),
        'estimated_independent_price': american_from_decimal(dec),
        'estimated_independent_hit_probability': round(hist, 4),
        'note': 'Estimated price/probability assumes independent legs; sportsbook parlay pricing and same-game correlation may differ.',
        'legs': [{
            'game': r.get('game'),
            'player': r.get('player'),
            'stat': r.get('stat'),
            'side': r.get('side'),
            'threshold': r.get('threshold'),
            'display_threshold': r.get('display_threshold'),
            'odds': r.get('odds'),
            'sportsbook': r.get('sportsbook'),
            'historical_probability': r.get('historical_probability'),
            'l5_rate': (r.get('l5') or {}).get('rate'),
            'l10_rate': (r.get('l10') or {}).get('rate'),
            'expected_value_per_unit': r.get('expected_value_per_unit'),
            'market_id': r.get('market_id'),
        } for r in legs],
    }


def build(target: str | None = None) -> dict[str, Any]:
    src = load(MARKETS)
    target = target or str(src.get('target_date') or '')
    rows = [r for r in src.get('rows', []) if isinstance(r, dict) and (not target or str(r.get('target_date') or target) == target)]
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        game = str(r.get('game') or '').strip()
        if game:
            by_game[game].append(r)

    parlays: list[dict[str, Any]] = []
    per_game_counts: dict[str, int] = {}
    for game, game_rows in by_game.items():
        pool = candidate_pool(game_rows)
        built = 0
        for idx, tier in enumerate(('SAFE', 'BALANCED', 'UPSIDE')):
            legs = choose_legs(pool, tier, offset=idx, leg_count=3)
            rec = parlay_record('SAME_GAME_ALT', tier, f'{game} #{idx+1}', legs, [game])
            if rec:
                parlays.append(rec)
                built += 1
        per_game_counts[game] = built

    games = sorted(by_game)
    if len(games) >= 2:
        game_pools = {g: candidate_pool(by_game[g]) for g in games}
        # Build three cross-game cards. On a 3-game slate each card naturally
        # uses one leg from each game; on larger slates cap at four games.
        for idx, tier in enumerate(('SAFE', 'BALANCED', 'UPSIDE')):
            legs: list[dict[str, Any]] = []
            used_players: set[str] = set()
            selected_games: list[str] = []
            for g in games[:4]:
                options = choose_legs(game_pools[g], tier, offset=idx, leg_count=4)
                pick = next((r for r in options if str(r.get('player') or '').lower() not in used_players), None)
                if pick:
                    legs.append(pick)
                    used_players.add(str(pick.get('player') or '').lower())
                    selected_games.append(g)
            rec = parlay_record('CROSS_GAME_ALT', tier, f'Mixed Slate #{idx+1}', legs, selected_games)
            if rec:
                parlays.append(rec)

    payload = {
        'schema_version': 1,
        'target_date': target,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'source': str(MARKETS),
        'status': 'ready' if parlays else 'no_qualified_parlays',
        'framework': {
            'same_game_target_per_game': 3,
            'minimum_same_game_target_per_game': 2,
            'cross_game_cards_target': 3,
            'legs_per_same_game_card': 3,
            'cross_game_rule': 'Prefer one leg per game; cap at four games per card.',
            'player_duplication_rule': 'No duplicate player within a parlay.',
            'pricing_rule': 'Exact sportsbook ALT lines only; no line averaging.',
            'tiers': ['SAFE', 'BALANCED', 'UPSIDE'],
            'research_note': 'Parlay probabilities are heuristic until prospective parlay grading accumulates.',
        },
        'summary': {
            'games': len(games),
            'same_game_parlays': sum(p.get('kind') == 'SAME_GAME_ALT' for p in parlays),
            'cross_game_parlays': sum(p.get('kind') == 'CROSS_GAME_ALT' for p in parlays),
            'total_parlays': len(parlays),
            'per_game_counts': per_game_counts,
        },
        'parlays': parlays,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload['summary'], indent=2))
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', dest='target_date')
    args = ap.parse_args()
    build(args.target_date)


if __name__ == '__main__':
    main()
