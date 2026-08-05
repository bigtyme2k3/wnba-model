from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path('.')
DASH = ROOT / 'data' / 'dashboard'
OUT_JSON = ROOT / 'docs' / 'audit' / 'PLAYER_PROP_GENERATOR_LINEAGE.json'
OUT_MD = ROOT / 'docs' / 'audit' / 'PLAYER_PROP_GENERATOR_LINEAGE.md'

CANDIDATES = [
    Path('wnba_player_props_ingestion.py'),
    Path('scrape_odds_props.py'),
    Path('wnba_player_prop_intelligence.py'),
    Path('wnba_master_source_builder.py'),
    Path('wnba_current_slate.py'),
    Path('build_dashboard_v4.py'),
    Path('patch_dashboard_navigation_v2.py'),
]

OUTPUTS = [
    DASH / 'wnba_master.json',
    DASH / 'wnba_player_props.json',
    DASH / 'wnba_player_prop_intelligence.json',
    DASH / 'wnba_player_props_current_slate.json',
]


def load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ('props', 'rows', 'markets', 'player_props', 'items', 'data'):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def main() -> None:
    master = load(DASH / 'wnba_master.json') or {}
    today = [g for g in master.get('games', []) if isinstance(g, dict) and str(g.get('bucket', '')).lower() == 'today']
    games = {str(g.get('game') or '').strip() for g in today if g.get('game')}
    teams = set()
    for g in today:
        for key in ('away_team', 'home_team'):
            if g.get(key):
                teams.add(str(g[key]).strip())

    files = []
    for path in CANDIDATES:
        text = path.read_text(encoding='utf-8', errors='ignore') if path.exists() else ''
        files.append({
            'path': str(path),
            'exists': path.exists(),
            'mentions_odds_api': 'ODDS_API_KEY' in text or 'api.the-odds-api.com' in text,
            'writes_master': 'wnba_master.json' in text,
            'writes_player_props': 'wnba_player_props' in text,
            'reads_player_props': 'player_props' in text or 'props' in text,
        })

    outputs = []
    for path in OUTPUTS:
        payload = load(path)
        rs = rows(payload)
        off_slate = []
        missing_team = 0
        current = 0
        for row in rs:
            game = str(row.get('game') or row.get('matchup') or '').strip()
            team = str(row.get('team') or row.get('player_team') or '').strip()
            if not team:
                missing_team += 1
            if game in games and (not team or team in teams):
                current += 1
            else:
                off_slate.append({'player': row.get('player'), 'game': game, 'team': team})
        outputs.append({
            'path': str(path),
            'exists': path.exists(),
            'target_date': payload.get('target_date') if isinstance(payload, dict) else None,
            'row_count': len(rs),
            'current_slate_rows': current,
            'off_slate_rows': len(off_slate),
            'missing_team_rows': missing_team,
            'sample_off_slate': off_slate[:10],
        })

    report = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': master.get('target_date'),
        'games': sorted(games),
        'teams': sorted(teams),
        'candidate_generators': files,
        'outputs': outputs,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding='utf-8')

    lines = ['# Player Prop Generator Lineage', '', f"- Target date: `{report['target_date']}`", f"- Current games: {len(games)}", '', '## Candidate generators']
    for item in files:
        lines.append(f"- `{item['path']}` — exists={item['exists']}, odds_api={item['mentions_odds_api']}, writes_master={item['writes_master']}, writes_player_props={item['writes_player_props']}")
    lines += ['', '## Output health']
    for item in outputs:
        lines.append(f"- `{item['path']}` — rows={item['row_count']}, current={item['current_slate_rows']}, off_slate={item['off_slate_rows']}, missing_team={item['missing_team_rows']}, target={item['target_date']}")
    OUT_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
