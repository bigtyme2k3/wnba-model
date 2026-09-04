"""Build canonical WNBA injury context without mutating downstream artifacts.

This module owns only the injury-intelligence artifacts and minute projection
support file.  Game predictions, player-prop predictions, master slate data,
and portfolio/decision artifacts are downstream consumers and must be rebuilt
by their own workflows.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAW = Path('data/raw')
DASH = Path('data/dashboard')
WH = Path('data/warehouse')
MASTER_PATHS = [DASH / 'wnba_master.json', Path('data/master/wnba_master.json')]
STATUS_FACTORS = {
    'OUT': 0.0,
    'DOUBTFUL': 0.15,
    'QUESTIONABLE': 0.65,
    'PROBABLE': 0.92,
    'ACTIVE': 1.0,
    'UNKNOWN': 0.80,
}
CONF_PENALTY = {
    'OUT': 100,
    'DOUBTFUL': 35,
    'QUESTIONABLE': 15,
    'PROBABLE': 4,
    'ACTIVE': 0,
    'UNKNOWN': 10,
}


def load_json(path: Path, default: Any):
    try:
        return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def dump(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(data, path.open('w', encoding='utf-8'), indent=2, allow_nan=False)


def norm(value: Any) -> str:
    text = str(value or '').lower().replace('’', "'")
    text = re.sub(r'\b(jr\.?|sr\.?|ii|iii|iv)\b', '', text)
    return ' '.join(re.sub(r"[^a-z0-9' -]", '', text).split())


def sf(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return list(csv.DictReader(path.open(encoding='utf-8', newline='')))
    except Exception:
        return []


def player_pool() -> dict[str, dict]:
    raw = load_json(RAW / 'wnba_players_live.json', {})
    rows: list[dict] = []
    if isinstance(raw, dict):
        for name, item in raw.items():
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault('player', name)
                rows.append(row)
    elif isinstance(raw, list):
        rows = raw

    output: dict[str, dict] = {}
    for row in rows:
        name = str(row.get('player') or row.get('athlete_display_name') or row.get('name') or '')
        if not name:
            continue
        mpg = sf(
            row.get('roll5_mpg')
            or row.get('mpg')
            or row.get('minutes')
            or row.get('minutes_per_game')
            or row.get('avg_minutes'),
            0,
        )
        usage = sf(row.get('usage_rate') or row.get('usage') or row.get('usg_pct'), 0)
        if usage and usage < 1:
            usage *= 100
        output[norm(name)] = {
            'player': name,
            'team': str(row.get('team') or row.get('team_name') or ''),
            'position': str(row.get('position') or row.get('pos') or ''),
            'mpg': mpg,
            'usage': usage,
            'raw': row,
        }
    return output


def todays_teams(master: dict, target_date: str) -> set[str]:
    teams: set[str] = set()
    games = master.get('games', []) or master.get('today_games', []) or []
    for game in games:
        game_date = str(game.get('game_date') or master.get('target_date') or '')[:10]
        bucket = str(game.get('bucket') or 'today')
        if game_date and game_date != target_date:
            continue
        if bucket not in {'today', ''}:
            continue
        for key in ('home_team', 'away_team', 'home', 'away'):
            if game.get(key):
                teams.add(str(game[key]))
    return teams


def build(target_date: str) -> dict:
    master = next((load_json(path, {}) for path in MASTER_PATHS if path.exists()), {})
    teams = todays_teams(master, target_date)
    players = player_pool()
    injuries = read_csv(RAW / f'injuries_{target_date}.csv') or read_csv(RAW / 'injuries_today.csv')

    filtered: list[dict] = []
    for row in injuries:
        if teams and row.get('team') not in teams:
            continue
        severity = str(row.get('severity') or row.get('status') or 'UNKNOWN').upper()
        if severity not in STATUS_FACTORS:
            severity = 'UNKNOWN'
        item = dict(row)
        item['severity'] = severity
        item['player_key'] = norm(row.get('player'))
        filtered.append(item)

    injury_by = {row['player_key']: row for row in filtered if row['player_key']}
    roster: dict[str, list[dict]] = defaultdict(list)
    for player in players.values():
        if player['team']:
            roster[player['team']].append(player)

    adjustments: dict[str, dict] = {}
    beneficiaries: list[dict] = []
    team_impacts: list[dict] = []

    for team in teams or roster.keys():
        missing_minutes = 0.0
        missing_usage = 0.0
        team_injuries = [row for row in filtered if row.get('team') == team]

        for injury in team_injuries:
            player = players.get(injury['player_key'], {})
            base = sf(player.get('mpg'), 25)
            usage = sf(player.get('usage'), 18)
            factor = STATUS_FACTORS[injury['severity']]
            projected = round(base * factor, 1)
            adjustments[injury['player_key']] = {
                'player': injury.get('player'),
                'team': team,
                'severity': injury['severity'],
                'base_minutes': base,
                'projected_minutes': projected,
                'minutes_delta': round(projected - base, 1),
                'usage': usage,
                'projection_factor': factor,
                'confidence_penalty': CONF_PENALTY[injury['severity']],
                'is_out': injury['severity'] in {'OUT', 'DOUBTFUL'},
                'detail': injury.get('detail', ''),
                'source': injury.get('source', ''),
            }
            missing_minutes += max(0, base - projected)
            missing_usage += max(0, usage * (1 - factor))

        candidates = [
            player
            for player in roster.get(team, [])
            if norm(player['player']) not in injury_by and player['mpg'] > 0
        ]
        candidates.sort(key=lambda player: player['mpg'], reverse=True)
        weights: list[tuple[dict, float, float]] = []
        for player in candidates[:8]:
            headroom = max(0, 38 - player['mpg'])
            role = max(1, player['mpg']) * (1 + max(0, player['usage']) / 100) * max(0.2, headroom / 10)
            weights.append((player, role, headroom))

        total_weight = sum(weight for _, weight, _ in weights) or 1
        allocated = 0.0
        for player, weight, headroom in weights:
            share = weight / total_weight
            boost = min(headroom, missing_minutes * share)
            usage_boost = min(7.0, missing_usage * share)
            if boost < 0.2 and usage_boost < 0.2:
                continue
            key = norm(player['player'])
            base = player['mpg']
            projected = min(38, base + boost)
            allocated += boost
            adjustments[key] = {
                'player': player['player'],
                'team': team,
                'severity': 'BENEFICIARY',
                'base_minutes': base,
                'projected_minutes': round(projected, 1),
                'minutes_delta': round(projected - base, 1),
                'usage': player['usage'],
                'usage_delta': round(usage_boost, 2),
                'projection_factor': round((projected / max(base, 1)) * (1 + usage_boost / 100), 4),
                'confidence_penalty': 0,
                'is_out': False,
                'detail': 'Minutes/usage redistributed from unavailable teammates',
                'source': 'injury_intelligence',
            }
            beneficiaries.append(adjustments[key])

        team_impacts.append({
            'team': team,
            'injuries': len(team_injuries),
            'missing_minutes': round(missing_minutes, 1),
            'minutes_reallocated': round(allocated, 1),
            'impact_level': 'HIGH' if missing_minutes >= 45 else 'MED' if missing_minutes >= 20 else 'LOW',
        })

    # Diagnostics are computed against the canonical master props but never
    # written back into that file. Downstream builders apply these adjustments.
    props = master.get('props', []) or []
    adjusted_props = 0
    blocked_props = 0
    limited_props = 0
    for prop in props:
        adjustment = adjustments.get(norm(prop.get('player')))
        if not adjustment:
            continue
        adjusted_props += 1
        if adjustment.get('is_out'):
            blocked_props += 1
        elif str(adjustment.get('severity') or '').upper() in {'QUESTIONABLE', 'UNKNOWN'}:
            limited_props += 1

    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        'generated_at_utc': generated_at,
        'target_date': target_date,
        'freshness_minutes': 0,
        'artifact_owner': 'WNBA V5 Injury Intelligence',
        'source_only': True,
        'canonical_master_mutated': False,
        'canonical_player_props_mutated': False,
        'downstream_prediction_artifacts_mutated': False,
        'downstream_decision_artifacts_mutated': False,
        'teams': sorted(teams),
        'injuries': filtered,
        'adjustments': list(adjustments.values()),
        'team_impacts': team_impacts,
        'summary': {
            'injuries_on_slate': len(filtered),
            'out_or_doubtful': sum(row['severity'] in {'OUT', 'DOUBTFUL'} for row in filtered),
            'questionable': sum(row['severity'] == 'QUESTIONABLE' for row in filtered),
            'probable': sum(row['severity'] == 'PROBABLE' for row in filtered),
            'beneficiaries': len(beneficiaries),
            'props_adjusted_diagnostic': adjusted_props,
            'props_blocked_diagnostic': blocked_props,
            'props_limited_diagnostic': limited_props,
            # Compatibility aliases: counts only; no downstream artifact was changed.
            'recommendations_blocked': blocked_props,
            'recommendations_limited': limited_props,
        },
        'policy': (
            'This artifact is context-only. Game, prop, master, and portfolio artifacts '
            'must consume injury intelligence in their own builders.'
        ),
    }

    dump(WH / 'wnba_injury_intelligence.json', report)
    dump(DASH / 'wnba_injury_intelligence.json', report)

    RAW.mkdir(parents=True, exist_ok=True)
    with (RAW / 'minute_projections.csv').open('w', encoding='utf-8', newline='') as handle:
        columns = [
            'game_date', 'player', 'team', 'severity', 'base_minutes', 'proj_min',
            'minutes_delta', 'usage_delta', 'projection_factor', 'is_out',
        ]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for adjustment in adjustments.values():
            writer.writerow({
                'game_date': target_date,
                'player': adjustment['player'],
                'team': adjustment['team'],
                'severity': adjustment['severity'],
                'base_minutes': adjustment['base_minutes'],
                'proj_min': adjustment['projected_minutes'],
                'minutes_delta': adjustment['minutes_delta'],
                'usage_delta': adjustment.get('usage_delta', 0),
                'projection_factor': adjustment['projection_factor'],
                'is_out': adjustment['is_out'],
            })

    print(json.dumps(report['summary'], indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True)
    args = parser.parse_args()
    build(args.date)


if __name__ == '__main__':
    main()
