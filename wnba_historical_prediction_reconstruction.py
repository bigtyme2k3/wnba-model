from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path('data/warehouse/wnba_odds_warehouse_v2.sqlite')
OUTS = [
    Path('data/dashboard/wnba_historical_prediction_reconstruction.json'),
    Path('data/warehouse/wnba_historical_prediction_reconstruction.json'),
]


def num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def norm(v: Any) -> str:
    return ' '.join(str(v or '').strip().lower().split())


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}


def pick(cols: set[str], *names: str) -> str | None:
    return next((n for n in names if n in cols), None)


def q(col: str | None, alias: str) -> str:
    return f't."{col}" AS "{alias}"' if col else f'NULL AS "{alias}"'


def implied_probability(odds: float | None) -> float | None:
    if odds is None or odds == 0:
        return None
    return (-odds) / ((-odds) + 100.0) if odds < 0 else 100.0 / (odds + 100.0)


def profit_units(result: str, odds: float | None) -> float:
    r = norm(result)
    if r in {'push', 'void', 'cancelled', 'canceled'}:
        return 0.0
    if r in {'loss', 'lost'}:
        return -1.0
    if r not in {'win', 'won'}:
        return 0.0
    if odds is None or odds == 0:
        return 0.9091
    return odds / 100.0 if odds > 0 else 100.0 / abs(odds)


def beta_rate(wins: int, losses: int, prior: float = 0.5, strength: float = 12.0) -> float:
    n = wins + losses
    return (wins + prior * strength) / (n + strength)


def load_joined(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'wagers' not in tables or 'grades' not in tables:
        return [], {'reason': 'wagers or grades table missing', 'tables': sorted(tables)}

    wc, gc = columns(conn, 'wagers'), columns(conn, 'grades')
    wager_id = pick(wc, 'wager_id', 'id')
    grade_wager_id = pick(gc, 'wager_id', 'id')
    result_col = pick(gc, 'result', 'grade', 'outcome', 'status')
    if not wager_id or not grade_wager_id or not result_col:
        return [], {'reason': 'required join columns missing', 'wager_columns': sorted(wc), 'grade_columns': sorted(gc)}

    aliases = {
        'wager_id': wager_id,
        'event_id': pick(wc, 'event_id'),
        'captured_at': pick(wc, 'captured_at', 'snapshot_time', 'created_at', 'timestamp'),
        'market': pick(wc, 'market_key', 'market', 'stat', 'prop_type'),
        'sportsbook': pick(wc, 'sportsbook', 'book', 'bookmaker'),
        'selection': pick(wc, 'selection', 'side', 'outcome_name', 'name'),
        'line': pick(wc, 'line', 'point', 'threshold'),
        'odds': pick(wc, 'odds', 'price', 'american_odds'),
        'player': pick(wc, 'player', 'player_name', 'description'),
        'team': pick(wc, 'team', 'team_name'),
        'is_closing': pick(wc, 'is_closing', 'closing'),
    }
    select = [q(col, alias) for alias, col in aliases.items()]
    select += [f'g."{result_col}" AS result']
    for alias, names in {
        'actual': ('actual', 'actual_value', 'final_value'),
        'clv': ('clv', 'closing_line_value'),
        'grade_profit': ('profit_units', 'units', 'profit', 'pnl'),
    }.items():
        col = pick(gc, *names)
        select.append(f'g."{col}" AS "{alias}"' if col else f'NULL AS "{alias}"')

    raw = conn.execute(
        f'SELECT {", ".join(select)} FROM wagers t JOIN grades g ON t."{wager_id}" = g."{grade_wager_id}"'
    ).fetchall()
    rows = [dict(r) for r in raw]

    # Add event chronology when available.
    event_times: dict[str, str] = {}
    if 'events' in tables and aliases['event_id']:
        ec = columns(conn, 'events')
        eid = pick(ec, 'event_id', 'id')
        etime = pick(ec, 'commence_time', 'start_time', 'game_date', 'event_time')
        if eid and etime:
            for r in conn.execute(f'SELECT "{eid}", "{etime}" FROM events'):
                event_times[str(r[0])] = str(r[1] or '')
    for row in rows:
        row['event_time'] = event_times.get(str(row.get('event_id') or ''), '') or str(row.get('captured_at') or '')
    return rows, {'tables': sorted(tables), 'joined_rows': len(rows), 'event_times_found': len(event_times)}


def build() -> dict[str, Any]:
    if not DB.exists():
        report = {'status': 'missing_database', 'generated_at_utc': datetime.now(timezone.utc).isoformat()}
        return write(report)

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows, source = load_joined(conn)

    settled = []
    for r in rows:
        result = norm(r.get('result'))
        if result not in {'win', 'won', 'loss', 'lost', 'push', 'void', 'cancelled', 'canceled'}:
            continue
        r['result_norm'] = result
        r['won'] = 1 if result in {'win', 'won'} else 0 if result in {'loss', 'lost'} else None
        r['sort_key'] = str(r.get('event_time') or '') + '|' + str(r.get('wager_id') or '')
        settled.append(r)
    settled.sort(key=lambda x: x['sort_key'])

    # Rolling statistics are updated only after each wager is scored, preventing outcome leakage.
    overall = [0, 0]
    groups: dict[tuple[str, ...], list[int]] = defaultdict(lambda: [0, 0])
    reconstructed: list[dict[str, Any]] = []
    chronology_ok = all(bool(r.get('event_time')) for r in settled)

    for r in settled:
        market = norm(r.get('market')) or 'unknown'
        book = norm(r.get('sportsbook')) or 'unknown'
        selection = norm(r.get('selection')) or 'unknown'
        player = norm(r.get('player'))
        keys = [
            ('market', market),
            ('market_book', market, book),
            ('market_side', market, selection),
        ]
        if player:
            keys.append(('player_market', player, market))

        rates, samples = [], []
        for key in keys:
            w, l = groups[key]
            rates.append(beta_rate(w, l))
            samples.append(w + l)
        ow, ol = overall
        prior_rate = beta_rate(ow, ol)
        historical_prob = (sum(rates) + prior_rate) / (len(rates) + 1)
        prior_sample = sum(samples)

        odds = num(r.get('odds'))
        market_prob = implied_probability(odds)
        # Pregame reconstruction blends prior-only performance with the contemporaneous market price.
        predicted_prob = historical_prob if market_prob is None else 0.65 * historical_prob + 0.35 * market_prob
        probability_edge = 0.0 if market_prob is None else predicted_prob - market_prob
        sample_strength = min(1.0, math.sqrt(max(prior_sample, 0)) / 12.0)
        edge_score = max(1.0, min(99.0, 50.0 + probability_edge * 180.0 + (historical_prob - 0.5) * 45.0 * sample_strength))

        result = r['result_norm']
        units = num(r.get('grade_profit'))
        if units is None:
            units = profit_units(result, odds)
        market_type = 'alternate' if any(x in market for x in ('alternate', 'alt_')) else 'standard'
        reconstructed.append({
            'wager_id': str(r.get('wager_id') or ''),
            'event_time': r.get('event_time'),
            'player': r.get('player'),
            'team': r.get('team'),
            'market': r.get('market') or 'unknown',
            'sportsbook': r.get('sportsbook') or 'unknown',
            'selection': r.get('selection'),
            'line': num(r.get('line')),
            'odds': odds,
            'result': result,
            'edge_score': round(edge_score, 4),
            'predicted_probability': round(predicted_prob, 6),
            'market_probability': round(market_prob, 6) if market_prob is not None else None,
            'historical_probability': round(historical_prob, 6),
            'prior_sample': prior_sample,
            'clv': num(r.get('clv')),
            'profit_units': round(units, 6),
            'market_type': market_type,
            'chronology_ok': bool(r.get('event_time')),
            'reconstruction_version': 'prior-only-v1',
        })

        if r['won'] is not None:
            if r['won']:
                overall[0] += 1
            else:
                overall[1] += 1
            for key in keys:
                groups[key][0 if r['won'] else 1] += 1

    conn.execute('DROP TABLE IF EXISTS historical_edge_predictions')
    conn.execute('''CREATE TABLE historical_edge_predictions (
        wager_id TEXT, event_time TEXT, player TEXT, team TEXT, market TEXT, sportsbook TEXT,
        selection TEXT, line REAL, odds REAL, result TEXT, edge_score REAL,
        predicted_probability REAL, market_probability REAL, historical_probability REAL,
        prior_sample INTEGER, clv REAL, profit_units REAL, market_type TEXT,
        chronology_ok INTEGER, reconstruction_version TEXT
    )''')
    conn.executemany('''INSERT INTO historical_edge_predictions VALUES (
        :wager_id,:event_time,:player,:team,:market,:sportsbook,:selection,:line,:odds,:result,
        :edge_score,:predicted_probability,:market_probability,:historical_probability,:prior_sample,
        :clv,:profit_units,:market_type,:chronology_ok,:reconstruction_version
    )''', reconstructed)
    conn.commit()
    conn.close()

    report = {
        'phase': 'historical-prediction-reconstruction',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'ok' if reconstructed else 'insufficient_data',
        'source': source,
        'summary': {
            'settled_rows_loaded': len(settled),
            'predictions_reconstructed': len(reconstructed),
            'chronology_complete': chronology_ok,
            'chronology_missing_rows': sum(not bool(r.get('event_time')) for r in settled),
            'minimum_prior_sample_met': sum(r['prior_sample'] >= 20 for r in reconstructed),
            'score_min': min((r['edge_score'] for r in reconstructed), default=None),
            'score_max': max((r['edge_score'] for r in reconstructed), default=None),
            'warning': 'Scores are reconstructed with rolling prior-only information. They are suitable for research, but are not identical to predictions saved live before tipoff.'
        },
        'methodology': {
            'future_outcome_leakage_blocked': True,
            'rolling_updates_after_scoring': True,
            'uses_current_row_outcome_for_score': False,
            'version': 'prior-only-v1'
        }
    }
    return write(report)


def write(report: dict[str, Any]) -> dict[str, Any]:
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open('w', encoding='utf-8'), indent=2, allow_nan=False)
    print(json.dumps(report.get('summary', report), indent=2))
    return report


def main() -> None:
    argparse.ArgumentParser().parse_args()
    build()


if __name__ == '__main__':
    main()
