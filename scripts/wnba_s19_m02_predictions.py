from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

DASH = Path('data/dashboard')
MASTER = DASH / 'wnba_master.json'
GAMES = DASH / 'wnba_sprint2_phase2.json'
INJURY = DASH / 'wnba_injury_intelligence.json'
BUY = DASH / 'wnba_v5_buy_signals.json'
OUT = DASH / 'wnba_s19_m02_predictions.json'
AUDIT = DASH / 'wnba_s19_m02_prediction_audit.json'


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


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
    return ' '.join(str(value or '').strip().lower().split())


def side_from_edge(edge: float | None, threshold: float = 0.5):
    if edge is None or abs(edge) < threshold:
        return 'PASS'
    return 'OVER' if edge > 0 else 'UNDER'


def build(target: str):
    master = load(MASTER, {})
    games = load(GAMES, {})
    injury = load(INJURY, {})
    buy = load(BUY, {})

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
    for row in games.get('games', []) or []:
        item = dict(row)
        context = item.get('injury_context') or {}
        if context.get('fresh') is not True or str(context.get('target_date') or '') != target:
            raise SystemExit(f"Stale injury context on game {item.get('game')}")
        item['prediction_source'] = 'sprint19_m01_injury_aware_game_projection'
        current_games.append(item)

    players = {norm(p.get('player')): p for p in master.get('players', []) or [] if p.get('player')}
    prop_rows = []
    missing_projection = []
    out_actionable = []

    for row in master.get('props', []) or []:
        item = dict(row)
        player = str(item.get('player') or '')
        stat = str(first(item, 'stat', 'market', 'prop_type') or '').upper()
        line = f(first(item, 'line', 'market_line', 'consensus_line', 'best_line'))
        projection = f(first(item, 'projection', 'proj', 'model_projection', 'projected_value'))
        if projection is None and line is not None:
            old_edge = f(item.get('edge'))
            if old_edge is not None:
                projection = round(line + old_edge, 3)
        if projection is None or line is None:
            missing_projection.append({'player': player, 'stat': stat, 'line': line, 'projection': projection})
            continue

        edge = round(projection - line, 2)
        recommendation = side_from_edge(edge)
        confidence = f(first(item, 'confidence', 'final_score', 'model_confidence'))
        eligible = bool(item.get('eligible', item.get('eligible_for_bet', True)))
        injury_status = str(item.get('injury_status') or '').upper()
        if injury_status in {'OUT', 'DOUBTFUL'} or not eligible:
            recommendation = 'PASS'
            eligible = False
        elif injury_status in {'QUESTIONABLE', 'UNKNOWN'} and recommendation != 'PASS':
            # Keep the model direction visible while explicitly marking it non-actionable.
            eligible = False

        if injury_status in {'OUT', 'DOUBTFUL'} and recommendation != 'PASS':
            out_actionable.append(player)

        profile = players.get(norm(player), {})
        prop_rows.append({
            'target_date': target,
            'player': player,
            'team': item.get('team'),
            'game': item.get('game'),
            'stat': stat,
            'line': line,
            'model_projection': round(projection, 2),
            'edge': edge,
            'recommendation': recommendation,
            'confidence': confidence,
            'eligible': eligible and recommendation != 'PASS',
            'best_over_book': item.get('best_over_book'),
            'best_over_price': item.get('best_over_price'),
            'best_under_book': item.get('best_under_book'),
            'best_under_price': item.get('best_under_price'),
            'projected_minutes': item.get('projected_minutes'),
            'minutes_delta': item.get('minutes_delta'),
            'injury_status': item.get('injury_status'),
            'injury_adjusted': bool(item.get('injury_adjusted')),
            'injury_projection_factor': item.get('injury_projection_factor'),
            'injury_detail': item.get('injury_detail'),
            'roll5_pts': profile.get('roll5_pts'),
            'roll5_reb': profile.get('roll5_reb'),
            'roll5_ast': profile.get('roll5_ast'),
            'roll5_mpg': profile.get('roll5_mpg'),
            'prediction_source': 'injury_adjusted_master_prop_projection',
        })

    if out_actionable:
        raise SystemExit(f'Unavailable players remain actionable: {sorted(set(out_actionable))}')
    if not prop_rows:
        raise SystemExit('No current model-backed Player Props predictions were generated')

    buy_target = str(buy.get('target_date') or buy.get('date') or '')[:10]
    buy_rows = buy.get('rows') or buy.get('signals') or buy.get('buy_signals') or buy.get('bets') or []
    current_buy = []
    if buy_target == target:
        current_buy = [dict(r) for r in buy_rows if str(r.get('date') or r.get('target_date') or target)[:10] == target]

    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': target,
        'schema_version': 'sprint19-m02-unified-predictions-v1',
        'status': 'READY',
        'source_policy': {
            'games': 'data/dashboard/wnba_sprint2_phase2.json',
            'player_props': 'injury-adjusted data/dashboard/wnba_master.json props',
            'best_bets': 'data/dashboard/wnba_v5_buy_signals.json only; no Phase 2 fallback',
        },
        'injury_generated_at_utc': injury_stamp,
        'games_generated_at_utc': game_stamp,
        'games': current_games,
        'player_props': prop_rows,
        'best_bets': current_buy,
        'summary': {
            'games': len(current_games),
            'player_prop_predictions': len(prop_rows),
            'player_props_injury_adjusted': sum(bool(r.get('injury_adjusted')) for r in prop_rows),
            'actionable_player_props': sum(bool(r.get('eligible')) for r in prop_rows),
            'v5_best_bets': len(current_buy),
            'missing_projection_rows_skipped': len(missing_projection),
        },
    }
    OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')

    audit = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': target,
        'module': 'SPRINT19-M02',
        'status': 'READY',
        'game_projection_after_injury_refresh': True,
        'games': len(current_games),
        'player_prop_predictions': len(prop_rows),
        'player_props_with_model_projection': sum(r.get('model_projection') is not None for r in prop_rows),
        'player_props_injury_adjusted': sum(bool(r.get('injury_adjusted')) for r in prop_rows),
        'actionable_out_props': len(out_actionable),
        'best_bets_source': 'wnba_v5_buy_signals.json',
        'best_bets_current_rows': len(current_buy),
        'phase2_best_bets_fallback_enabled': False,
        'missing_projection_rows_skipped': len(missing_projection),
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
