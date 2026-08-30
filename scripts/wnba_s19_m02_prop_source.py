from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# This script runs as `python scripts/...`, which makes `scripts/` the first
# import location. Add the repository root explicitly so existing root-level
# collectors such as scrape_odds_props.py can be reused instead of duplicated.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scrape_odds_props as odds_props

RAW = ROOT / 'data/raw'
DASH = ROOT / 'data/dashboard'
GAMES = DASH / 'wnba_sprint2_phase2.json'
CANONICAL_PROPS = DASH / 'wnba_player_props.json'
AUDIT = DASH / 'wnba_s19_m02_prop_source_audit.json'


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def game_key(row) -> str:
    game = str(row.get('game') or row.get('matchup') or '').strip()
    if ' @ ' in game:
        return game
    away = str(row.get('away_team') or row.get('away') or '').strip()
    home = str(row.get('home_team') or row.get('home') or '').strip()
    if away and home:
        return f'{away} @ {home}'
    opp = str(row.get('opp_team') or row.get('opp') or '').strip()
    if ' @ ' in opp:
        return opp
    return game or opp


def exact_rows(frame: pd.DataFrame, game_names: set[str], target: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=odds_props.RAW_COLUMNS)
    work = frame.copy()
    if 'game_date' in work.columns:
        work = work[work['game_date'].astype(str).str[:10] == target].copy()
    keys = work.apply(lambda r: game_key(r), axis=1)
    work = work[keys.isin(game_names)].copy()
    if work.empty:
        return pd.DataFrame(columns=odds_props.RAW_COLUMNS)
    return work


def read_existing(target: str, game_names: set[str]) -> tuple[pd.DataFrame, str | None]:
    for path in (RAW / f'props_raw_{target}.csv', RAW / 'props_today.csv'):
        if not path.exists():
            continue
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        exact = exact_rows(frame, game_names, target)
        # Old caches contain a consensus across an unknown/all-book universe.
        # They cannot safely feed the new three-book model contract.
        if 'sportsbooks' not in exact.columns:
            continue
        allowed = odds_props.PLAYER_PROP_BOOKS
        valid_books = exact['sportsbooks'].fillna('').astype(str).map(
            lambda value: bool(value) and set(value.split(',')).issubset(allowed)
        )
        exact = exact[valid_books].copy()
        if not exact.empty:
            return exact, str(path.relative_to(ROOT))
    return pd.DataFrame(columns=odds_props.RAW_COLUMNS), None


def read_canonical_props(target: str, game_names: set[str]) -> tuple[pd.DataFrame, str | None]:
    """Convert the persisted canonical standard prop artifact into M02 raw rows.

    This is an API-free fallback for days when the paid Odds API quota is
    exhausted but a valid same-day canonical prop snapshot has already been
    persisted. Only the three production sportsbooks are retained.
    """
    payload = load_json(CANONICAL_PROPS, {})
    if str(payload.get('target_date') or '')[:10] != target:
        return pd.DataFrame(columns=odds_props.RAW_COLUMNS), None
    rows = []
    allowed = odds_props.PLAYER_PROP_BOOKS
    stat_to_raw = {v: k for k, v in odds_props.PROP_MARKETS.items()}
    for r in payload.get('rows') or []:
        if str(r.get('target_date') or '')[:10] != target:
            continue
        game = str(r.get('game') or '').strip()
        if game not in game_names:
            continue
        books = []
        over_prices = []
        under_prices = []
        for b in r.get('books') or []:
            book = str(b.get('book') or '').strip().lower()
            if book not in allowed:
                continue
            books.append(book)
            side = str(b.get('side') or '').upper()
            price = b.get('price')
            if side == 'OVER' and price is not None:
                over_prices.append(float(price))
            elif side == 'UNDER' and price is not None:
                under_prices.append(float(price))
        books = sorted(set(books))
        if not books:
            continue
        away = str(r.get('away_team') or '').strip()
        home = str(r.get('home_team') or '').strip()
        stat = str(r.get('stat') or '').strip().lower()
        rows.append({
            'game_date': target,
            'event_id': r.get('event_id'),
            'player': r.get('player'),
            'team': r.get('team'),
            'position': r.get('position') or '',
            'opp_team': game,
            'is_home': bool(r.get('team') and str(r.get('team')).strip() == home),
            'stat_raw': stat_to_raw.get(stat, stat),
            'stat': stat,
            'line': r.get('line'),
            'over_price': sum(over_prices)/len(over_prices) if over_prices else None,
            'under_price': sum(under_prices)/len(under_prices) if under_prices else None,
            'yes_price': None,
            'no_price': None,
            'num_books': len(books),
            'sportsbooks': ','.join(books),
            'odds_type': 'sportsbook',
            'game_time': r.get('commence_time'),
            'home_team': home,
            'away_team': away,
            'source': 'canonical-player-props-cache',
            'scraped_at': payload.get('generated_at_utc'),
        })
    if not rows:
        return pd.DataFrame(columns=odds_props.RAW_COLUMNS), None
    frame = pd.DataFrame(rows, columns=odds_props.RAW_COLUMNS)
    return exact_rows(frame, game_names, target), str(CANONICAL_PROPS.relative_to(ROOT))


def fetch_live(target: str, game_names: set[str]) -> tuple[pd.DataFrame, int]:
    if not os.getenv('ODDS_API_KEY'):
        raise SystemExit('ODDS_API_KEY unavailable and no exact current-slate sportsbook prop cache exists')

    events = odds_props.fetch_events()
    standard_rows = []
    matched_events = 0
    for event in events:
        home = str(event.get('home_team') or '').strip()
        away = str(event.get('away_team') or '').strip()
        key = f'{away} @ {home}' if away and home else ''
        if key not in game_names:
            continue
        matched_events += 1
        event_id = event.get('id')
        if not event_id:
            continue
        data = odds_props.fetch_event_markets(event_id, list(odds_props.PROP_MARKETS), 'standard-s19-m02')
        standard_rows.extend(odds_props.parse_event_props(data, target))

    frame = pd.DataFrame(standard_rows, columns=odds_props.RAW_COLUMNS) if standard_rows else odds_props.empty_df()
    return exact_rows(frame, game_names, target), matched_events


def save(frame: pd.DataFrame, target: str):
    RAW.mkdir(parents=True, exist_ok=True)
    for path in (RAW / f'props_raw_{target}.csv', RAW / 'props_today.csv'):
        frame.to_csv(path, index=False)


def build(target: str):
    games = load_json(GAMES, {})
    if str(games.get('target_date') or '')[:10] != target:
        raise SystemExit(f"Game target mismatch: {games.get('target_date')} != {target}")

    game_names = {str(r.get('game') or '').strip() for r in (games.get('games') or []) if str(r.get('game') or '').strip()}
    if not game_names:
        raise SystemExit('No canonical current-slate games available for sportsbook prop source')

    cached, cache_path = read_existing(target, game_names)
    api_called = False
    matched_events = 0
    source = cache_path
    frame = cached

    if frame.empty:
        frame, source = read_canonical_props(target, game_names)

    if frame.empty:
        api_called = True
        frame, matched_events = fetch_live(target, game_names)
        source = 'the-odds-api-live-events'

    if frame.empty:
        raise SystemExit('No exact current-slate sportsbook player props available after cache check and live refresh')

    frame = exact_rows(frame, game_names, target)
    if frame.empty:
        raise SystemExit('Exact-slate filter removed every sportsbook prop row')
    save(frame, target)

    rendered_games = sorted({game_key(r) for _, r in frame.iterrows()})
    audit = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': target,
        'status': 'READY',
        'module': 'SPRINT19-M02-PROP-SOURCE',
        'source': source,
        'api_called': api_called,
        'matched_live_events': matched_events,
        'canonical_games': sorted(game_names),
        'prop_games': rendered_games,
        'sportsbooks': sorted(odds_props.PLAYER_PROP_BOOKS),
        'rows': int(len(frame)),
        'all_rows_exact_current_slate': all(g in game_names for g in rendered_games),
        'policy': 'Use only DraftKings, FanDuel, and Fanatics. Reuse a verified three-book raw cache or same-day canonical standard prop artifact before making any live Odds API request. Alternate markets are never requested here.',
    }
    AUDIT.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print('SPRINT19_M02_PROP_SOURCE_READY', json.dumps(audit))
    return audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    args = ap.parse_args()
    build(args.date)


if __name__ == '__main__':
    main()
