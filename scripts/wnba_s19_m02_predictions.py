from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DASH = Path('data/dashboard')
RAW = Path('data/raw')
MASTER = DASH / 'wnba_master.json'
GAMES = DASH / 'wnba_sprint2_phase2.json'
INJURY = DASH / 'wnba_injury_intelligence.json'
BUY = DASH / 'wnba_v5_buy_signals.json'
PORTFOLIO = DASH / 'wnba_v5_live_portfolio.json'
PROP_PRED = RAW / 'player_points_today.csv'
OUT = DASH / 'wnba_s19_m02_predictions.json'
AUDIT = DASH / 'wnba_s19_m02_prediction_audit.json'


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def read_csv(path: Path):
    if not path.exists():
        return []
    try:
        with path.open(encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def f(value, default=None):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def first(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ''):
            return value
    return None


def norm(value):
    return ' '.join(str(value or '').strip().lower().replace('’', "'").split())


def boolish(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None or value == '':
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y'}


def confidence_pct(row):
    p = f(first(row, 'model_prob', 'probability'))
    if p is not None:
        return round((p * 100.0) if p <= 1.0 else p, 1)
    label = str(first(row, 'conf', 'confidence') or '').upper()
    return {'HIGH': 80.0, 'MED': 65.0, 'MEDIUM': 65.0, 'LOW': 50.0}.get(label)


def current_rows(payload, target):
    rows = payload.get('rows') or payload.get('signals') or payload.get('buy_signals') or payload.get('bets') or payload.get('portfolio') or payload.get('allocations') or []
    top_target = str(payload.get('target_date') or payload.get('date') or '')[:10]
    if top_target and top_target != target:
        return []
    out = []
    for row in rows:
        row_target = str(row.get('target_date') or row.get('date') or target)[:10]
        if row_target == target:
            out.append(dict(row))
    return out


def exact_game(row):
    game = str(first(row, 'game', 'matchup', 'event') or '').strip()
    if ' @ ' in game:
        return game
    away = str(first(row, 'away_team', 'away') or '').strip()
    home = str(first(row, 'home_team', 'home') or '').strip()
    if away and home:
        return f'{away} @ {home}'
    return game


def canonical_prop_rows(master, game_names):
    rows = master.get('props') or master.get('player_props') or []
    out = []
    for src in rows:
        row = dict(src)
        game = exact_game(row)
        if game not in game_names:
            continue
        away, home = ('', '')
        if ' @ ' in game:
            away, home = [x.strip() for x in game.split(' @ ', 1)]
        stat = str(first(row, 'stat', 'market', 'prop_type', 'stat_raw') or '').strip()
        line = first(row, 'line', 'market_line', 'consensus_line', 'best_line')
        over_price = first(row, 'over_price', 'best_over_price', 'price_over')
        under_price = first(row, 'under_price', 'best_under_price', 'price_under')
        yes_price = first(row, 'yes_price', 'best_yes_price')
        no_price = first(row, 'no_price', 'best_no_price')
        if line in (None, '') and yes_price in (None, ''):
            continue
        out.append({
            'player': first(row, 'player', 'player_name'),
            'team': first(row, 'team', 'player_team'),
            'opp_team': first(row, 'opp_team', 'opponent', 'opp'),
            'position': first(row, 'position', 'pos'),
            'stat': stat,
            'stat_raw': stat,
            'line': line,
            'over_price': over_price if over_price not in (None, '') else -110,
            'under_price': under_price if under_price not in (None, '') else -110,
            'yes_price': yes_price,
            'no_price': no_price,
            'best_over_book': first(row, 'best_over_book', 'book_over', 'sportsbook'),
            'best_under_book': first(row, 'best_under_book', 'book_under', 'sportsbook'),
            'home_team': first(row, 'home_team', 'home') or home,
            'away_team': first(row, 'away_team', 'away') or away,
            'game': game,
        })
    return out


def write_canonical_prop_input(target, master, game_names):
    rows = canonical_prop_rows(master, game_names)
    if not rows:
        raise SystemExit('Canonical master contains zero exact current-slate prop rows')
    path = RAW / f'props_raw_{target}.csv'
    fields = ['player','team','opp_team','position','stat','stat_raw','line','over_price','under_price','yes_price','no_price','best_over_book','best_under_book','home_team','away_team','game']
    with path.open('w', encoding='utf-8', newline='') as fobj:
        writer = csv.DictWriter(fobj, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'status':'CANONICAL_PROP_INPUT_READY','target_date':target,'rows':len(rows),'games':sorted(game_names),'path':str(path)}))
    return len(rows)


def build(target: str):
    master = load(MASTER, {})
    games = load(GAMES, {})
    injury = load(INJURY, {})
    buy = load(BUY, {})
    portfolio = load(PORTFOLIO, {})

    for name, payload in [('master', master), ('games', games), ('injury', injury)]:
        actual = str(payload.get('target_date') or '')[:10]
        if actual != target:
            raise SystemExit(f'{name} target mismatch: {actual} != {target}')

    injury_stamp = injury.get('generated_at_utc')
    game_stamp = games.get('generated_at_utc')
    if not injury_stamp or not game_stamp:
        raise SystemExit('Missing injury/game freshness timestamps')
    if datetime.fromisoformat(str(game_stamp).replace('Z', '+00:00')) < datetime.fromisoformat(str(injury_stamp).replace('Z', '+00:00')):
        raise SystemExit('Game projections are older than injury intelligence')

    current_games = []
    game_names = set()
    for row in games.get('games', []) or []:
        item = dict(row)
        context = item.get('injury_context') or {}
        if context.get('fresh') is not True or str(context.get('target_date') or '') != target:
            raise SystemExit(f"Stale injury context on game {item.get('game')}")
        item['prediction_source'] = 'sprint19_m01_injury_aware_game_projection'
        current_games.append(item)
        if item.get('game'):
            game_names.add(str(item['game']))
    if not game_names:
        raise SystemExit('No canonical current-slate games available')

    # Build player_points input from the already-verified canonical master instead of
    # trusting data/raw/props_today.csv, which can contain a different schedule.
    canonical_input_rows = write_canonical_prop_input(target, master, game_names)
    subprocess.run(['python', 'player_points.py', '--date', target, '--out', 'data/raw'], check=True)

    adjustments = {norm(a.get('player')): a for a in injury.get('adjustments', []) or [] if a.get('player')}
    prop_source = read_csv(PROP_PRED)
    if not prop_source:
        raise SystemExit('Fresh canonical player_points_today.csv is missing or empty')

    prop_rows = []
    off_slate = []
    missing_projection = []
    out_actionable = []

    for row in prop_source:
        game = str(row.get('game') or '').strip()
        if not game or game not in game_names:
            off_slate.append({'player': row.get('player'), 'game': game, 'stat': row.get('stat')})
            continue
        player = str(row.get('player') or '')
        stat = str(first(row, 'stat', 'market', 'prop_type') or '').upper()
        line = f(first(row, 'line', 'market_line', 'consensus_line', 'best_line'))
        projection = f(first(row, 'pred', 'projection', 'proj', 'model_projection', 'projected_value'))
        if projection is None or line is None:
            missing_projection.append({'player': player, 'stat': stat, 'line': line, 'projection': projection})
            continue

        adj = adjustments.get(norm(player))
        injury_status = str((adj or {}).get('severity') or row.get('injury_status') or 'CLEAR').upper()
        projection_pre_injury = projection
        projected_minutes = None
        minutes_delta = None
        injury_adjusted = False
        injury_detail = None
        injury_factor = None
        if adj:
            injury_detail = adj.get('detail')
            injury_factor = f(adj.get('projection_factor'), 1.0)
            projected_minutes = adj.get('projected_minutes')
            minutes_delta = adj.get('minutes_delta')
            injury_adjusted = True
            if injury_status == 'BENEFICIARY' and injury_factor is not None:
                projection = round(projection * injury_factor, 2)

        edge = round(projection - line, 2)
        raw_signal = str(row.get('signal') or '').upper()
        recommendation = raw_signal if raw_signal in {'OVER', 'UNDER', 'PASS'} else ('OVER' if edge >= 0.35 else 'UNDER' if edge <= -0.35 else 'PASS')
        eligible = boolish(row.get('is_active'), recommendation != 'PASS') and recommendation != 'PASS'
        if injury_status in {'OUT', 'DOUBTFUL'}:
            recommendation = 'PASS'; eligible = False
        elif injury_status in {'QUESTIONABLE', 'UNKNOWN'}:
            eligible = False
        if injury_status in {'OUT', 'DOUBTFUL'} and eligible:
            out_actionable.append(player)

        prop_rows.append({
            'target_date': target, 'player': player, 'team': row.get('team'), 'game': game,
            'stat': stat, 'line': line, 'model_projection': round(projection, 2),
            'projection_pre_injury': round(projection_pre_injury, 2), 'edge': edge,
            'recommendation': recommendation, 'confidence': confidence_pct(row),
            'confidence_label': row.get('conf'), 'eligible': eligible,
            'best_over_book': row.get('best_over_book') or row.get('book_over'),
            'best_over_price': row.get('over_price'),
            'best_under_book': row.get('best_under_book') or row.get('book_under'),
            'best_under_price': row.get('under_price'),
            'projected_minutes': projected_minutes, 'minutes_delta': minutes_delta,
            'injury_status': injury_status, 'injury_adjusted': injury_adjusted,
            'injury_projection_factor': injury_factor, 'injury_detail': injury_detail,
            'last5_hit': row.get('last5_hit'), 'last10_hit': row.get('last10_hit'),
            'role_score': row.get('role_score'), 'minutes_trend': row.get('minutes_trend'),
            'points_trend': row.get('points_trend'),
            'prediction_source': 'canonical_current_slate_player_points_v5_plus_current_injury_intelligence',
        })

    if out_actionable:
        raise SystemExit(f'Unavailable players remain actionable: {sorted(set(out_actionable))}')
    if not prop_rows:
        raise SystemExit(f'No exact current-slate Player Props predictions generated; off_slate={len(off_slate)} canonical_input={canonical_input_rows}')
    if off_slate:
        raise SystemExit(f'Fresh canonical prop build emitted off-slate rows: {len(off_slate)}')

    current_buy = current_rows(buy, target)
    current_portfolio = current_rows(portfolio, target)
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'target_date': target,
        'schema_version': 'sprint19-m02-unified-predictions-v4', 'status': 'READY',
        'source_policy': {
            'games': 'data/dashboard/wnba_sprint2_phase2.json',
            'player_props': 'canonical data/dashboard/wnba_master.json props -> dated props_raw input -> player_points.py + current injury intelligence',
            'best_bets': 'data/dashboard/wnba_v5_buy_signals.json only; no Phase 2 fallback',
            'portfolio': 'data/dashboard/wnba_v5_live_portfolio.json only; no Phase 2 fallback'},
        'injury_generated_at_utc': injury_stamp, 'games_generated_at_utc': game_stamp,
        'games': current_games, 'player_props': prop_rows, 'best_bets': current_buy, 'portfolio': current_portfolio,
        'summary': {'games': len(current_games), 'canonical_prop_input_rows': canonical_input_rows,
            'player_prop_predictions': len(prop_rows), 'player_props_injury_adjusted': sum(bool(r.get('injury_adjusted')) for r in prop_rows),
            'actionable_player_props': sum(bool(r.get('eligible')) for r in prop_rows), 'v5_best_bets': len(current_buy),
            'v5_portfolio_rows': len(current_portfolio), 'off_slate_prop_rows_rejected': len(off_slate),
            'missing_projection_rows_skipped': len(missing_projection)}}
    OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')

    audit = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'target_date': target,
        'module': 'SPRINT19-M02', 'status': 'READY', 'game_projection_after_injury_refresh': True,
        'games': len(current_games), 'canonical_prop_input_rows': canonical_input_rows,
        'player_prop_predictions': len(prop_rows),
        'player_props_with_model_projection': sum(r.get('model_projection') is not None for r in prop_rows),
        'player_props_injury_adjusted': sum(bool(r.get('injury_adjusted')) for r in prop_rows),
        'actionable_out_props': len(out_actionable), 'off_slate_prop_rows_rejected': len(off_slate),
        'all_rendered_props_exact_current_slate': all(r.get('game') in game_names for r in prop_rows),
        'best_bets_source': 'wnba_v5_buy_signals.json', 'best_bets_current_rows': len(current_buy),
        'phase2_best_bets_fallback_enabled': False, 'portfolio_source': 'wnba_v5_live_portfolio.json',
        'portfolio_current_rows': len(current_portfolio), 'phase2_portfolio_fallback_enabled': False,
        'missing_projection_rows_skipped': len(missing_projection)}
    AUDIT.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(audit))
    return payload


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--date', required=True); args = ap.parse_args(); build(args.date)


if __name__ == '__main__':
    main()
