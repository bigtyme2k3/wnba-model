from __future__ import annotations

import json
from pathlib import Path

DASHBOARD = Path('docs/index.html')
MASTER = Path('data/dashboard/wnba_master.json')
INGESTED = Path('data/dashboard/wnba_player_props.json')
MARKER = 'v4-player-props-truth'


def game_name(row: dict) -> str:
    return str(row.get('game') or row.get('matchup') or '').strip()


def explicit_team(row: dict) -> str:
    for key in ('team', 'player_team', 'team_name', 'current_team'):
        value = row.get(key)
        if value:
            return str(value).strip()
    return ''


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def main() -> None:
    html = DASHBOARD.read_text(encoding='utf-8')
    master = load_json(MASTER, {})
    games = [g for g in master.get('games', []) if isinstance(g, dict) and str(g.get('bucket', '')).lower() == 'today']
    current_games = {str(g.get('game') or '').strip() for g in games if g.get('game')}
    current_teams = {
        str(team).strip()
        for g in games
        for team in (g.get('away_team'), g.get('home_team'))
        if team
    }

    ingested = load_json(INGESTED, {})
    target = str(master.get('target_date') or '')
    if str(ingested.get('target_date') or '') == target and isinstance(ingested.get('rows'), list):
        source_rows = [r for r in ingested['rows'] if isinstance(r, dict)]
        source_name = str(INGESTED)
    else:
        source_rows = [r for r in master.get('props', []) if isinstance(r, dict)]
        source_name = str(MASTER) + ':props'

    clean_rows = []
    excluded = []
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
        'target_date': target,
        'source': source_name,
        'current_games': sorted(current_games),
        'current_teams': sorted(current_teams),
        'rows': clean_rows,
        'source_count': len(source_rows),
        'active_count': len(clean_rows),
        'excluded_count': len(excluded),
        'excluded_sample': excluded[:50],
    }
    out = Path('data/dashboard/wnba_player_props_current_slate.json')
    out.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    script = f'''<script id="{MARKER}">
(function(){{
 const TRUTH={json.dumps(payload, separators=(',', ':'))};
 const A=v=>Array.isArray(v)?v:[];
 window.propsRaw=()=>A(TRUTH.rows);
 window.teamFor=r=>String(r.team||r.player_team||r.team_name||r.current_team||'').trim();
 window.oppFor=(r,t)=>String(r.game||r.matchup||'').split(' @ ').find(x=>x&&x!==t)||'';
 const realHistory=(r,n)=>{{
   const candidates=[r.recent_values,r.last_10_values,r.last10,r.game_log_values,r.history];
   for(const c of candidates){{if(Array.isArray(c)) return c.map(Number).filter(Number.isFinite).slice(0,n);}}
   return [];
 }};
 window.hist=realHistory;
 window.hit=(vals,line,side)=>{{
   vals=A(vals).filter(Number.isFinite);
   if(!vals.length) return {{h:0,p:null}};
   const h=vals.filter(v=>side==='UNDER'?v<Number(line):v>Number(line)).length;
   return {{h,p:Math.round(h/vals.length*100)}};
 }};
 window.propRow=function(r){{
   const team=window.teamFor(r), matchup=String(r.game||r.matchup||''), parts=matchup.split(' @ ');
   if(!team||!TRUTH.current_teams.includes(team)||!TRUTH.current_games.includes(matchup)) return '';
   const opponent=parts.find(x=>x!==team)||'';
   const side=String(r.signal||r.side||'WATCH').toUpperCase();
   const history=realHistory(r,10);
   const line=Number(r.line??r.consensus_line);
   const hits=history.length&&Number.isFinite(line)?history.filter(v=>side==='UNDER'?v<line:v>line).length:null;
   const pct=hits===null?null:Math.round(hits/history.length*100);
   const recommendation=String(r.recommendation||r.ai_recommendation||r.decision||'WATCH');
   return `<div class="propRow"><div class="player"><div class="logo mono">${{window.E(team.split(/\\s+/).map(x=>x[0]).join('').slice(0,3))}}</div><div><div class="name">${{window.E(r.player)}}</div><div class="team mono">${{window.E(team)}} · ${{window.E(opponent)}}</div></div></div><div class="stat mono">${{window.E(r.stat)}}</div><div class="lineVal mono">${{window.E(r.line??r.consensus_line??'-')}}</div><div class="odds mono">${{window.E(r.best_over_price??r.over_price??'-')}}</div><div class="odds mono">${{window.E(r.best_under_price??r.under_price??'-')}}</div><div class="hist"><div class="small mono">${{history.length?`Verified history: ${{history.join(', ')}}`:'Verified history unavailable'}}</div></div><div class="hit mono"><div class="pct">${{pct===null?'—':pct+'%'}}</div><div>${{window.E(side)}}</div><div class="rec">${{hits===null?'No fabricated L10':hits+'/'+history.length}}</div></div><div class="small mono">${{window.E(r.projection??r.pred??'-')}}</div><div class="small mono">${{window.E(recommendation)}}</div></div>`;
 }};
 window.WNBA_PLAYER_PROPS_TRUTH=TRUTH;
}})();
</script>'''

    if f'id="{MARKER}"' in html:
        start = html.index(f'<script id="{MARKER}"')
        end = html.index('</script>', start) + len('</script>')
        html = html[:start] + script + html[end:]
    else:
        html = html.replace('</body>', script + '</body>')
    DASHBOARD.write_text(html, encoding='utf-8')
    print(json.dumps({'target_date': target, 'source_file': source_name, 'source': len(source_rows), 'active': len(clean_rows), 'excluded': len(excluded)}, indent=2))


if __name__ == '__main__':
    main()
