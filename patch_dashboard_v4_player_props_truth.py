from __future__ import annotations

import json
import re
from pathlib import Path

DASHBOARD = Path('docs/index.html')
MASTER = Path('data/dashboard/wnba_master.json')
CANONICAL = Path('data/dashboard/wnba_player_props.json')
OUT = Path('data/dashboard/wnba_player_props_current_slate.json')
MARKER = 'v4-player-props-canonical-source'


def rows_from(payload):
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ('rows', 'props', 'markets', 'player_props'):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def game_name(row: dict) -> str:
    return str(row.get('game') or row.get('matchup') or '').strip()


def explicit_team(row: dict) -> str:
    for key in ('team', 'player_team', 'team_name', 'current_team'):
        value = row.get(key)
        if value:
            return str(value).strip()
    return ''


def replace_function(html: str, name: str, replacement: str) -> str:
    pattern = rf'function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{.*?\n\}}'
    updated, count = re.subn(pattern, replacement, html, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'Unable to replace dashboard function: {name}')
    return updated


def main() -> None:
    html = DASHBOARD.read_text(encoding='utf-8')
    master = json.loads(MASTER.read_text(encoding='utf-8'))
    canonical_payload = json.loads(CANONICAL.read_text(encoding='utf-8'))

    games = [g for g in master.get('games', []) if isinstance(g, dict) and str(g.get('bucket', '')).lower() == 'today']
    current_games = {str(g.get('game') or '').strip() for g in games if g.get('game')}
    current_teams = {
        str(team).strip()
        for g in games
        for team in (g.get('away_team'), g.get('home_team'))
        if team
    }

    source_rows = rows_from(canonical_payload)
    clean_rows, excluded = [], []
    for row in source_rows:
        matchup = game_name(row)
        team = explicit_team(row)
        reasons = []
        if matchup not in current_games:
            reasons.append('off_slate_matchup')
        if not team:
            reasons.append('missing_explicit_team')
        elif team not in current_teams:
            reasons.append('off_slate_team')
        if reasons:
            excluded.append({'player': row.get('player'), 'game': matchup, 'team': team, 'reasons': reasons})
            continue
        copied = dict(row)
        copied['team'] = team
        clean_rows.append(copied)

    payload = {
        'target_date': master.get('target_date'),
        'source_file': str(CANONICAL),
        'current_games': sorted(current_games),
        'current_teams': sorted(current_teams),
        'rows': clean_rows,
        'source_count': len(source_rows),
        'active_count': len(clean_rows),
        'excluded_count': len(excluded),
        'excluded_sample': excluded[:50],
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    canonical_js = json.dumps(payload, separators=(',', ':'))
    injection = f'<script id="{MARKER}">const CANONICAL_PLAYER_PROPS={canonical_js};</script>'
    if f'id="{MARKER}"' in html:
        html = re.sub(rf'<script id="{MARKER}">.*?</script>', injection, html, count=1, flags=re.S)
    else:
        html = html.replace('</head>', injection + '</head>')

    html = replace_function(
        html,
        'propData',
        "function propData(){return Array.isArray(CANONICAL_PLAYER_PROPS.rows)?CANONICAL_PLAYER_PROPS.rows:[]\n}"
    )
    html = replace_function(
        html,
        'playerTeam',
        "function playerTeam(r){return String(r.team||r.player_team||r.team_name||r.current_team||'').trim()\n}"
    )
    html = replace_function(
        html,
        'histVals',
        "function histVals(r,n=5){for(const k of ['recent_values','last_10_values','last10','game_log_values','history']){const v=r[k];if(Array.isArray(v))return v.map(Number).filter(Number.isFinite).slice(0,n)}return []\n}"
    )
    html = replace_function(
        html,
        'hitInfo',
        "function hitInfo(vals,line,side){vals=Array.isArray(vals)?vals.filter(Number.isFinite):[];if(!vals.length)return {hits:0,pct:null,side:side==='UNDER'?'UNDER':'OVER',total:0};line=Number(line);let over=side!=='UNDER';let hits=vals.filter(v=>over?v>line:v<line).length;return {hits,pct:Math.round(hits/vals.length*100),side:over?'OVER':'UNDER',total:vals.length}\n}"
    )

    DASHBOARD.write_text(html, encoding='utf-8')
    print(json.dumps({'target_date': payload['target_date'], 'source_file': str(CANONICAL), 'source': len(source_rows), 'active': len(clean_rows), 'excluded': len(excluded)}, indent=2))


if __name__ == '__main__':
    main()
