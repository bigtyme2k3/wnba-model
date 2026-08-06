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
    if isinstance(payload, dict):
        for key in ('rows', 'props', 'markets', 'player_props'):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def main() -> None:
    html = DASHBOARD.read_text(encoding='utf-8')
    master = json.loads(MASTER.read_text(encoding='utf-8'))
    canonical = json.loads(CANONICAL.read_text(encoding='utf-8'))

    games = [g for g in master.get('games', []) if isinstance(g, dict) and str(g.get('bucket', '')).lower() == 'today']
    current_games = {str(g.get('game') or '').strip() for g in games if g.get('game')}
    current_teams = {str(t).strip() for g in games for t in (g.get('away_team'), g.get('home_team')) if t}

    clean, excluded = [], []
    for row in rows_from(canonical):
        matchup = str(row.get('game') or row.get('matchup') or '').strip()
        team = str(row.get('team') or row.get('player_team') or row.get('team_name') or row.get('current_team') or '').strip()
        reasons = []
        if matchup not in current_games:
            reasons.append('off_slate_matchup')
        if not team:
            reasons.append('missing_explicit_team')
        elif team not in current_teams:
            reasons.append('off_slate_team')
        if reasons:
            excluded.append({'player': row.get('player'), 'game': matchup, 'team': team, 'reasons': reasons})
        else:
            item = dict(row)
            item['team'] = team
            clean.append(item)

    payload = {
        'target_date': master.get('target_date'),
        'source_file': str(CANONICAL),
        'current_games': sorted(current_games),
        'current_teams': sorted(current_teams),
        'rows': clean,
        'source_count': len(rows_from(canonical)),
        'active_count': len(clean),
        'excluded_count': len(excluded),
        'excluded_sample': excluded[:50],
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    js = json.dumps(payload, separators=(',', ':'))
    script = f'''<script id="{MARKER}">
window.CANONICAL_PLAYER_PROPS={js};
window.propData=function(){{return Array.isArray(window.CANONICAL_PLAYER_PROPS.rows)?window.CANONICAL_PLAYER_PROPS.rows:[];}};
window.playerTeam=function(r){{return String(r.team||r.player_team||r.team_name||r.current_team||'').trim();}};
window.histVals=function(r,n=5){{for(const k of ['recent_values','last_10_values','last10','game_log_values','history']){{const v=r[k];if(Array.isArray(v))return v.map(Number).filter(Number.isFinite).slice(0,n);}}return [];}};
window.hitInfo=function(vals,line,side){{vals=Array.isArray(vals)?vals.filter(Number.isFinite):[];if(!vals.length)return {{hits:0,pct:null,side:side==='UNDER'?'UNDER':'OVER',total:0}};line=Number(line);const over=side!=='UNDER';const hits=vals.filter(v=>over?v>line:v<line).length;return {{hits,pct:Math.round(hits/vals.length*100),side:over?'OVER':'UNDER',total:vals.length}};}};
</script>'''

    if f'id="{MARKER}"' in html:
        html = re.sub(rf'<script id="{MARKER}">.*?</script>', script, html, count=1, flags=re.S)
    else:
        html = html.replace('</body>', script + '</body>')

    DASHBOARD.write_text(html, encoding='utf-8')
    print(json.dumps({'target_date': payload['target_date'], 'source': payload['source_count'], 'active': payload['active_count'], 'excluded': payload['excluded_count']}, indent=2))


if __name__ == '__main__':
    main()
