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
MODEL_VERSION = 'sprint19_player_props_v5_m02_action_v2'
ALLOWED_BOOKS = {'draftkings', 'fanduel', 'fanatics'}


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def read_csv(path: Path):
    if not path.exists():
        return []
    try:
        with path.open(encoding='utf-8', newline='') as fobj:
            return list(csv.DictReader(fobj))
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
    opp = str(first(row, 'opp_team', 'opp') or '').strip()
    if ' @ ' in opp:
        return opp
    return game or opp


def decision_key(row):
    return (
        norm(row.get('player')),
        norm(exact_game(row)),
        str(first(row, 'stat', 'market', 'prop_type') or '').upper(),
        str(first(row, 'signal', 'side', 'recommendation') or '').upper(),
    )


def explicit_supported_bet(row):
    action = str(first(row, 'final_action', 'action') or '').upper()
    book = norm(first(row, 'sportsbook', 'best_book', 'book')).replace(' ', '')
    return action == 'BET' and row.get('research_only') is not True and book in ALLOWED_BOOKS


def validate_prepared_prop_source(target: str, game_names: set[str]) -> int:
    path = RAW / f'props_raw_{target}.csv'
    rows = read_csv(path)
    if not rows:
        raise SystemExit(f'Prepared sportsbook prop source missing or empty: {path}')
    exact = [r for r in rows if exact_game(r) in game_names and str(r.get('game_date') or target)[:10] == target]
    if not exact:
        raise SystemExit('Prepared sportsbook prop source contains zero exact current-slate rows')
    if len(exact) != len(rows):
        raise SystemExit(f'Prepared sportsbook prop source still contains off-slate rows: {len(rows)-len(exact)}')
    print(json.dumps({'status':'SPORTSBOOK_PROP_INPUT_READY','target_date':target,'rows':len(exact),'games':sorted(game_names),'path':str(path)}))
    return len(exact)


def write_empty_state(target: str, injury_stamp: str, game_stamp: str):
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        'generated_at_utc': now,
        'target_date': target,
        'schema_version': 'sprint19-m02-unified-predictions-v5',
        'status': 'READY',
        'empty_slate': True,
        'source_policy': {
            'games': 'data/dashboard/wnba_sprint2_phase2.json',
            'player_props': 'confirmed empty slate; no sportsbook prop request and no player_points execution',
            'best_bets': 'empty on confirmed empty slate',
            'portfolio': 'empty on confirmed empty slate',
        },
        'injury_generated_at_utc': injury_stamp,
        'games_generated_at_utc': game_stamp,
        'games': [],
        'player_props': [],
        'best_bets': [],
        'portfolio': [],
        'summary': {
            'games': 0,
            'sportsbook_prop_input_rows': 0,
            'player_prop_predictions': 0,
            'player_props_injury_adjusted': 0,
            'candidate_player_props': 0,
            'bet_player_props': 0,
            'v5_best_bets': 0,
            'v5_portfolio_rows': 0,
            'research_buy_signals_excluded': 0,
            'off_slate_prop_rows_rejected': 0,
            'missing_projection_rows_skipped': 0,
            'negative_projection_rows_clamped': 0,
        },
    }
    OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    audit = {
        'generated_at_utc': now,
        'target_date': target,
        'module': 'SPRINT19-M02',
        'status': 'READY',
        'empty_slate': True,
        'game_projection_after_injury_refresh': True,
        'games': 0,
        'sportsbook_prop_input_rows': 0,
        'player_prop_predictions': 0,
        'player_props_with_model_projection': 0,
        'player_props_injury_adjusted': 0,
        'actionable_out_props': 0,
        'off_slate_prop_rows_rejected': 0,
        'all_rendered_props_exact_current_slate': True,
        'best_bets_source': 'confirmed_empty_slate',
        'best_bets_current_rows': 0,
        'research_buy_signals_excluded': 0,
        'phase2_best_bets_fallback_enabled': False,
        'portfolio_source': 'confirmed_empty_slate',
        'portfolio_current_rows': 0,
        'phase2_portfolio_fallback_enabled': False,
        'missing_projection_rows_skipped': 0,
        'negative_projection_rows_clamped': 0,
    }
    AUDIT.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(audit))
    return payload


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
        return write_empty_state(target, injury_stamp, game_stamp)

    sportsbook_input_rows = validate_prepared_prop_source(target, game_names)
    subprocess.run(['python', 'player_points.py', '--date', target, '--out', 'data/raw'], check=True)

    adjustments = {norm(a.get('player')): a for a in injury.get('adjustments', []) or [] if a.get('player')}
    prop_source = read_csv(PROP_PRED)
    if not prop_source:
        raise SystemExit('Fresh player_points_today.csv is missing or empty')

    prop_rows = []
    off_slate = []
    missing_projection = []
    out_actionable = []
    negative_projection_rows_clamped = 0

    for row in prop_source:
        game = exact_game(row)
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

        # Counting-stat props cannot have physically negative projections. Some
        # low-volume rows can be pushed below zero by trend/role adjustments in
        # player_points.py; clamp them here before edge, pick, and downstream
        # contract generation so every consumer receives a valid count forecast.
        if projection < 0 or projection_pre_injury < 0:
            negative_projection_rows_clamped += 1
        projection = max(0.0, projection)
        projection_pre_injury = max(0.0, projection_pre_injury)

        edge = round(projection - line, 2)
        raw_signal = str(row.get('signal') or '').upper()
        recommendation = raw_signal if raw_signal in {'OVER', 'UNDER', 'PASS'} else ('OVER' if edge >= 0.35 else 'UNDER' if edge <= -0.35 else 'PASS')
        if f(first(row, 'pred', 'projection', 'proj', 'model_projection', 'projected_value')) is not None and f(first(row, 'pred', 'projection', 'proj', 'model_projection', 'projected_value')) < 0:
            recommendation = 'OVER' if edge >= 0.35 else 'UNDER' if edge <= -0.35 else 'PASS'
        eligible = boolish(row.get('is_active'), recommendation != 'PASS') and recommendation != 'PASS'
        if injury_status in {'OUT', 'DOUBTFUL'}:
            recommendation = 'PASS'
            eligible = False
        elif injury_status in {'QUESTIONABLE', 'UNKNOWN'}:
            eligible = False
        if injury_status in {'OUT', 'DOUBTFUL'} and eligible:
            out_actionable.append(player)

        prop_rows.append({
            'target_date': target,
            'player': player,
            'team': row.get('team'),
            'game': game,
            'stat': stat,
            'line': line,
            'model_projection': round(projection, 2),
            'projection_pre_injury': round(projection_pre_injury, 2),
            'edge': edge,
            'recommendation': recommendation,
            'confidence': confidence_pct(row),
            'confidence_label': row.get('conf'),
            'eligible': eligible,
            'best_over_book': row.get('best_over_book') or row.get('book_over'),
            'best_over_price': row.get('over_price'),
            'best_under_book': row.get('best_under_book') or row.get('book_under'),
            'best_under_price': row.get('under_price'),
            'projected_minutes': projected_minutes,
            'minutes_delta': minutes_delta,
            'injury_status': injury_status,
            'injury_adjusted': injury_adjusted,
            'injury_projection_factor': injury_factor,
            'injury_detail': injury_detail,
            'last5_hit': row.get('last5_hit'),
            'last10_hit': row.get('last10_hit'),
            'role_score': row.get('role_score'),
            'minutes_trend': row.get('minutes_trend'),
            'points_trend': row.get('points_trend'),
            'prediction_source': 'exact_current_slate_sportsbook_props_plus_player_points_v5_plus_current_injury_intelligence',
        })

    if out_actionable:
        raise SystemExit(f'Unavailable players remain actionable: {sorted(set(out_actionable))}')
    if not prop_rows:
        raise SystemExit(f'No exact current-slate Player Props predictions generated; off_slate={len(off_slate)} sportsbook_input={sportsbook_input_rows}')
    if off_slate:
        raise SystemExit(f'Fresh sportsbook prop build emitted off-slate rows: {len(off_slate)}')

    current_buy = current_rows(buy, target)
    current_portfolio = current_rows(portfolio, target)
    approved_buy = [row for row in current_buy if explicit_supported_bet(row)]
    approved_portfolio = [row for row in current_portfolio if explicit_supported_bet(row)]
    finalized_bets = {decision_key(row): row for row in approved_buy if decision_key(row)[0] and decision_key(row)[2]}
    for row in prop_rows:
        finalized = finalized_bets.get(decision_key(row))
        action = 'BET' if finalized else ('WATCH' if row.get('recommendation') in {'OVER', 'UNDER'} else 'PASS')
        if finalized:
            side = str(row.get('recommendation') or '').upper()
            book = first(finalized, 'sportsbook', 'best_book', 'book')
            price = first(finalized, 'american_odds', 'odds', 'price')
            if side == 'OVER':
                row['best_over_book'], row['best_over_price'] = book, price
            elif side == 'UNDER':
                row['best_under_book'], row['best_under_price'] = book, price
        row['candidate_eligible'] = bool(row.get('eligible'))
        row['model_version'] = MODEL_VERSION
        row['action'] = action
        row['final_action'] = action
        row['eligible_for_bet'] = action == 'BET'
        if action == 'BET':
            row['sportsbook'] = first(finalized, 'sportsbook', 'best_book', 'book')
            row['american_odds'] = f(first(finalized, 'american_odds', 'odds', 'price'))
    explicit_best_bets = [dict(row) for row in prop_rows if row.get('final_action') == 'BET']
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': target,
        'schema_version': 'sprint19-m02-unified-predictions-v5',
        'status': 'READY',
        'empty_slate': False,
        'source_policy': {
            'games': 'data/dashboard/wnba_sprint2_phase2.json',
            'player_props': 'exact current-slate sportsbook props prepared by wnba_s19_m02_prop_source.py -> player_points.py -> current injury intelligence',
            'best_bets': 'data/dashboard/wnba_v5_buy_signals.json only; no Phase 2 fallback',
            'portfolio': 'data/dashboard/wnba_v5_live_portfolio.json only; no Phase 2 fallback',
        },
        'injury_generated_at_utc': injury_stamp,
        'games_generated_at_utc': game_stamp,
        'games': current_games,
        'player_props': prop_rows,
        'best_bets': explicit_best_bets,
        'portfolio': approved_portfolio,
        'summary': {
            'games': len(current_games),
            'sportsbook_prop_input_rows': sportsbook_input_rows,
            'player_prop_predictions': len(prop_rows),
            'player_props_injury_adjusted': sum(bool(r.get('injury_adjusted')) for r in prop_rows),
            'candidate_player_props': sum(bool(r.get('candidate_eligible')) for r in prop_rows),
            'bet_player_props': sum(r.get('final_action') == 'BET' for r in prop_rows),
            'v5_best_bets': len(explicit_best_bets),
            'v5_portfolio_rows': len(approved_portfolio),
            'research_buy_signals_excluded': len(current_buy) - len(approved_buy),
            'off_slate_prop_rows_rejected': len(off_slate),
            'missing_projection_rows_skipped': len(missing_projection),
            'negative_projection_rows_clamped': negative_projection_rows_clamped,
        },
    }
    OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')

    audit = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': target,
        'module': 'SPRINT19-M02',
        'status': 'READY',
        'empty_slate': False,
        'game_projection_after_injury_refresh': True,
        'games': len(current_games),
        'sportsbook_prop_input_rows': sportsbook_input_rows,
        'player_prop_predictions': len(prop_rows),
        'player_props_with_model_projection': sum(r.get('model_projection') is not None for r in prop_rows),
        'player_props_injury_adjusted': sum(bool(r.get('injury_adjusted')) for r in prop_rows),
        'actionable_out_props': len(out_actionable),
        'off_slate_prop_rows_rejected': len(off_slate),
        'all_rendered_props_exact_current_slate': all(r.get('game') in game_names for r in prop_rows),
        'best_bets_source': 'wnba_v5_buy_signals.json',
        'best_bets_current_rows': len(explicit_best_bets),
        'research_buy_signals_excluded': len(current_buy) - len(approved_buy),
        'phase2_best_bets_fallback_enabled': False,
        'portfolio_source': 'wnba_v5_live_portfolio.json',
        'portfolio_current_rows': len(approved_portfolio),
        'phase2_portfolio_fallback_enabled': False,
        'missing_projection_rows_skipped': len(missing_projection),
        'negative_projection_rows_clamped': negative_projection_rows_clamped,
    }
    AUDIT.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(audit))
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    args = ap.parse_args()
    build(args.date)


if __name__ == '__main__':
    main()
