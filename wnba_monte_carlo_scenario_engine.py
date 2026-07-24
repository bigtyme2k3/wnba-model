from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

DASH = Path('data/dashboard')
WARE = Path('data/warehouse')
ENSEMBLE = DASH / 'wnba_ensemble_intelligence.json'
EDGES = DASH / 'wnba_daily_edges.json'
LOGS = WARE / 'wnba_player_game_logs.json'
OUTS = [DASH / 'wnba_monte_carlo_scenarios.json', WARE / 'wnba_monte_carlo_scenarios.json']

STAT_KEYS = {
    'PTS': ('pts', 'total_pts'), 'REB': ('reb',), 'AST': ('ast',), '3PM': ('threes', 'three_pm'),
    'PRA': ('pra',), 'PR': ('pr',), 'PA': ('pa',), 'RA': ('ra',), 'STL': ('stl',), 'BLK': ('blk',), 'TOV': ('tov',),
}
DEFAULT_SD = {'PTS': 5.2, 'REB': 3.1, 'AST': 2.7, '3PM': 1.55, 'PRA': 7.3, 'PR': 6.3, 'PA': 6.0, 'RA': 4.3, 'STL': 1.05, 'BLK': 0.95, 'TOV': 1.55}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def norm(v: Any) -> str:
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    pos = clamp(p, 0, 1) * (len(values) - 1)
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def american_profit(odds: float | None) -> float:
    if odds is None or odds == 0:
        return 100 / 110
    return odds / 100 if odds > 0 else 100 / abs(odds)


def implied_probability(odds: float | None) -> float | None:
    if odds is None or odds == 0:
        return None
    return 100 / (odds + 100) if odds > 0 else abs(odds) / (abs(odds) + 100)


def stat_value(row: dict[str, Any], stat: str) -> float | None:
    scoring = row.get('scoring') if isinstance(row.get('scoring'), dict) else {}
    box = row.get('boxscore') if isinstance(row.get('boxscore'), dict) else {}
    pts = num(scoring.get('total_pts') if scoring else row.get('pts'))
    reb = num(box.get('reb') if box else row.get('reb'))
    ast = num(box.get('ast') if box else row.get('ast'))
    threes = num(scoring.get('three_pm') if scoring else row.get('threes'))
    direct = {'PTS': pts, 'REB': reb, 'AST': ast, '3PM': threes, 'STL': num(box.get('stl')), 'BLK': num(box.get('blk')), 'TOV': num(box.get('tov'))}
    if stat in direct:
        return direct[stat]
    if stat == 'PRA' and None not in (pts, reb, ast): return pts + reb + ast
    if stat == 'PR' and None not in (pts, reb): return pts + reb
    if stat == 'PA' and None not in (pts, ast): return pts + ast
    if stat == 'RA' and None not in (reb, ast): return reb + ast
    return None


def history_map() -> dict[tuple[str, str], list[float]]:
    payload = load(LOGS, {})
    groups: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    for row in payload.get('records', []) if isinstance(payload, dict) else []:
        if not isinstance(row, dict) or row.get('did_not_play') is True:
            continue
        player = norm(row.get('player'))
        if not player:
            continue
        for stat in DEFAULT_SD:
            value = stat_value(row, stat)
            if value is not None:
                groups[(player, stat)].append((str(row.get('game_date') or ''), value))
    out = {}
    for key, items in groups.items():
        items.sort(key=lambda x: x[0], reverse=True)
        out[key] = [v for _, v in items[:30]]
    return out


def sample_sd(values: list[float], fallback: float) -> float:
    if len(values) < 5:
        return fallback
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / max(1, len(values) - 1)
    return clamp(math.sqrt(variance), fallback * 0.65, fallback * 1.8)


def source_candidates() -> tuple[list[dict[str, Any]], str, str | None]:
    ensemble = load(ENSEMBLE, {})
    rows = ensemble.get('ranked_edges', []) if isinstance(ensemble, dict) else []
    if rows:
        return [r for r in rows if isinstance(r, dict)], 'ensemble', ensemble.get('target_date')
    edges = load(EDGES, {})
    rows = edges.get('top_edges', []) if isinstance(edges, dict) else []
    return [r for r in rows if isinstance(r, dict)], 'daily_edges', edges.get('target_date') if isinstance(edges, dict) else None


def scenario_specs(row: dict[str, Any]) -> list[dict[str, Any]]:
    injury = str(row.get('injury_status') or '').upper()
    specs = [
        {'name': 'baseline', 'weight': 0.62, 'mean_factor': 1.00, 'sd_factor': 1.00, 'description': 'Expected role and minutes'},
        {'name': 'minutes_up', 'weight': 0.10, 'mean_factor': 1.08, 'sd_factor': 1.05, 'description': 'Expanded role or overtime-friendly game'},
        {'name': 'minutes_down', 'weight': 0.10, 'mean_factor': 0.90, 'sd_factor': 1.08, 'description': 'Reduced rotation or mild limitation'},
        {'name': 'blowout', 'weight': 0.10, 'mean_factor': 0.82, 'sd_factor': 1.12, 'description': 'Fourth-quarter minutes loss'},
        {'name': 'foul_trouble', 'weight': 0.08, 'mean_factor': 0.76, 'sd_factor': 1.18, 'description': 'Early foul trouble or game disruption'},
    ]
    if injury in {'QUESTIONABLE', 'PROBABLE', 'UNKNOWN'}:
        specs[0]['weight'] -= 0.10
        specs[2]['weight'] += 0.06
        specs.append({'name': 'injury_limit', 'weight': 0.04, 'mean_factor': 0.68, 'sd_factor': 1.22, 'description': 'Active but materially limited'})
    total = sum(s['weight'] for s in specs)
    for spec in specs:
        spec['weight'] /= total
    return specs


def simulate_candidate(row: dict[str, Any], history: dict[tuple[str, str], list[float]], sims: int) -> dict[str, Any] | None:
    player = str(row.get('player') or '')
    stat = str(row.get('market') or row.get('stat') or '').upper().replace('PLAYER_', '')
    side = str(row.get('side') or row.get('signal') or 'OVER').upper()
    line = num(row.get('line'))
    projection = num(row.get('projection'))
    if line is None:
        return None
    values = history.get((norm(player), stat), [])
    hist_mean = sum(values[:10]) / len(values[:10]) if values else None
    if projection is None:
        projection = hist_mean if hist_mean is not None else line
    if hist_mean is not None and len(values) >= 5:
        mean = 0.72 * projection + 0.28 * hist_mean
    else:
        mean = projection
    base_sd = sample_sd(values, DEFAULT_SD.get(stat, max(1.2, abs(mean) * 0.25)))
    specs = scenario_specs(row)
    seed_text = f"{player}|{stat}|{side}|{line}|{row.get('game')}|sprint10-v1"
    rng = random.Random(sum((i + 1) * ord(ch) for i, ch in enumerate(seed_text)))
    all_values: list[float] = []
    scenario_rows = []
    remaining = max(1000, sims)
    for index, spec in enumerate(specs):
        count = remaining if index == len(specs) - 1 else max(1, round(max(1000, sims) * spec['weight']))
        remaining -= count
        vals = [max(0.0, rng.gauss(mean * spec['mean_factor'], base_sd * spec['sd_factor'])) for _ in range(count)]
        all_values.extend(vals)
        over = sum(v > line for v in vals) / len(vals)
        under = sum(v < line for v in vals) / len(vals)
        scenario_rows.append({
            'scenario': spec['name'], 'weight': round(spec['weight'], 4), 'simulations': len(vals),
            'mean': round(sum(vals) / len(vals), 2), 'over_probability': round(over, 4),
            'under_probability': round(under, 4), 'description': spec['description'],
        })
    all_values.sort()
    over_prob = sum(v > line for v in all_values) / len(all_values)
    under_prob = sum(v < line for v in all_values) / len(all_values)
    push_prob = max(0.0, 1.0 - over_prob - under_prob)
    signal_prob = under_prob if side in {'UNDER', 'NO'} else over_prob
    odds = num(row.get('odds'))
    implied = implied_probability(odds)
    profit = american_profit(odds)
    ev = signal_prob * profit - (1 - signal_prob)
    median = percentile(all_values, 0.50)
    downside = percentile(all_values, 0.10)
    upside = percentile(all_values, 0.90)
    volatility = base_sd / max(1.0, mean)
    risk = 'LOW' if signal_prob >= 0.62 and volatility <= 0.25 else 'MEDIUM' if signal_prob >= 0.55 and volatility <= 0.38 else 'HIGH'
    if row.get('calibration_extrapolated'):
        risk = 'HIGH'
    return {
        'player': player, 'team': row.get('team'), 'game': row.get('game'), 'stat': stat, 'side': side,
        'line': line, 'sportsbook': row.get('sportsbook'), 'odds': odds, 'market_type': row.get('market_type', 'standard'),
        'ensemble_score': row.get('ensemble_score'), 'ensemble_grade': row.get('grade'),
        'adaptive_probability': row.get('adaptive_probability') or row.get('calibrated_probability'),
        'simulation_probability': round(signal_prob, 4), 'over_probability': round(over_prob, 4),
        'under_probability': round(under_prob, 4), 'push_probability': round(push_prob, 4),
        'market_implied_probability': round(implied, 4) if implied is not None else None,
        'probability_edge': round(signal_prob - implied, 4) if implied is not None else None,
        'expected_value_per_unit': round(ev, 4), 'expected_value_percent': round(ev * 100, 2),
        'projection_mean': round(mean, 2), 'projection_sd': round(base_sd, 2), 'median': round(median, 2),
        'p10': round(downside, 2), 'p25': round(percentile(all_values, .25), 2),
        'p75': round(percentile(all_values, .75), 2), 'p90': round(upside, 2),
        'history_games': len(values), 'simulations': len(all_values), 'risk_band': risk,
        'calibration_extrapolated': bool(row.get('calibration_extrapolated')),
        'scenarios': scenario_rows,
        'explanation': [
            f'{signal_prob:.1%} simulated probability for {side}',
            f'Median outcome {median:.2f} versus line {line:g}',
            f'80% scenario interval {downside:.2f} to {upside:.2f}',
            f'Expected value {ev:+.2%} per unit at listed odds',
        ],
    }


def build(target: str | None, sims: int) -> dict[str, Any]:
    rows, source, source_date = source_candidates()
    history = history_map()
    simulations = []
    skipped = 0
    for row in rows:
        try:
            result = simulate_candidate(row, history, sims)
            if result:
                simulations.append(result)
            else:
                skipped += 1
        except Exception as exc:
            skipped += 1
            print(f'WARN Sprint 10 candidate skipped: {exc}')
    simulations.sort(key=lambda r: (r['expected_value_per_unit'], r['simulation_probability'], -(r['projection_sd'] or 0)), reverse=True)
    report = {
        'sprint': 10, 'phase': 'monte-carlo-scenario-engine',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': target or source_date or str(date.today()),
        'status': 'ok' if simulations else 'awaiting_live_slate',
        'summary': {
            'source': source, 'candidates_loaded': len(rows), 'candidates_simulated': len(simulations),
            'skipped': skipped, 'simulations_per_candidate': max(1000, sims),
            'positive_ev': sum(r['expected_value_per_unit'] > 0 for r in simulations),
            'probability_60_plus': sum(r['simulation_probability'] >= .60 for r in simulations),
            'low_risk': sum(r['risk_band'] == 'LOW' for r in simulations),
            'top_probability': simulations[0]['simulation_probability'] if simulations else None,
            'top_ev_percent': simulations[0]['expected_value_percent'] if simulations else None,
        },
        'top_scenarios': simulations[:20], 'all_simulations': simulations[:100],
        'methodology': {
            'distribution': 'scenario-weighted Gaussian with empirical player/stat volatility when available',
            'scenarios': ['baseline', 'minutes_up', 'minutes_down', 'blowout', 'foul_trouble', 'injury_limit when applicable'],
            'chronology_safe': True,
            'warning': 'Simulation probabilities are model estimates, not guarantees. Live minutes, injuries, and lineup news can materially change outcomes.',
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open('w', encoding='utf-8'), indent=2, allow_nan=False)
    print(json.dumps(report['summary'], indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default='')
    parser.add_argument('--sims', type=int, default=10000)
    args = parser.parse_args()
    build(args.date or None, max(1000, args.sims))


if __name__ == '__main__':
    main()
