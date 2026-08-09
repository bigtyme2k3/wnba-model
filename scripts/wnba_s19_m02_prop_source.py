from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import scrape_odds_props as odds_props

RAW = Path('data/raw')
DASH = Path('data/dashboard')
GAMES = DASH / 'wnba_sprint2_phase2.json'
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
        if not exact.empty:
            return exact, str(path)
    return pd.DataFrame(columns=odds_props.RAW_COLUMNS), None


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
        api_called = True
        frame, matched_events = fetch_live(target, game_names)
        source = 'the-odds-api-live-events'

    if frame.empty:
        raise SystemExit('No exact current-slate sportsbook player props available after cache check and live refresh')

    # Only exact canonical games are allowed to become player_points input.
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
        'rows': int(len(frame)),
        'all_rows_exact_current_slate': all(g in game_names for g in rendered_games),
        'policy': 'Reuse exact current-slate sportsbook cache when available; otherwise make one live standard-market refresh. Alternate markets are not requested here.',
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
