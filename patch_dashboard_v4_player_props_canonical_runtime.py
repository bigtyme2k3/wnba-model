from __future__ import annotations

import json
import re
from pathlib import Path

HTML = Path('docs/index.html')
PROPS = Path('data/dashboard/wnba_player_props.json')
MARKER = 'v4-player-props-canonical-runtime'


def replace_one(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'Unable to replace dashboard function: {label} (matches={count})')
    return updated


def main() -> None:
    html = HTML.read_text(encoding='utf-8')
    payload = json.loads(PROPS.read_text(encoding='utf-8'))
    rows = payload.get('rows') or []
    if not isinstance(rows, list) or not rows:
        raise SystemExit('Canonical player props file has no rows')

    embedded = json.dumps(rows, separators=(',', ':')).replace('</', '<\\/')
    data_script = f'<script id="{MARKER}">window.WNBA_CANONICAL_PLAYER_PROPS={embedded};</script>'
    if f'id="{MARKER}"' in html:
        html = re.sub(rf'<script id="{MARKER}">.*?</script>', data_script, html, count=1, flags=re.S)
    else:
        html = html.replace('</head>', data_script + '</head>', 1)

    html = replace_one(
        html,
        r"function\s+propData\s*\(\s*\)\s*\{.*?\}",
        "function propData(){return A(window.WNBA_CANONICAL_PLAYER_PROPS||[])}",
        'propData',
    )
    html = replace_one(
        html,
        r"function\s+playerTeam\s*\(\s*r\s*\)\s*\{.*?\}",
        "function playerTeam(r){return String(r.team||r.player_team||r.team_name||r.current_team||'').trim()}",
        'playerTeam',
    )
    html = replace_one(
        html,
        r"function\s+histVals\s*\([^)]*\)\s*\{.*?\}\s*function\s+hitInfo",
        "function histVals(r,n=5){const c=[r.recent_values,r.last_10_values,r.last10,r.game_log_values,r.history].find(Array.isArray);return A(c).map(Number).filter(Number.isFinite).slice(0,n)}\nfunction hitInfo",
        'histVals',
    )

    # Prevent stale embedded rows from being presented as a top pick before render.
    html = html.replace('Toronto Tempo @ Golden State Valkyries', 'STALE_MATCHUP_REMOVED')
    HTML.write_text(html, encoding='utf-8')

    check = HTML.read_text(encoding='utf-8')
    required = [MARKER, 'window.WNBA_CANONICAL_PLAYER_PROPS', "function propData(){return A(window.WNBA_CANONICAL_PLAYER_PROPS||[])}"]
    missing = [item for item in required if item not in check]
    if missing:
        raise SystemExit('Canonical renderer verification failed: ' + ', '.join(missing))
    if 'function playerTeam(r){let g=' in check or 'function histVals(r,n=5){let base=' in check:
        raise SystemExit('Legacy synthetic Player Props functions remain')
    print(json.dumps({'target_date': payload.get('target_date'), 'canonical_rows': len(rows), 'marker': MARKER}, indent=2))


if __name__ == '__main__':
    main()
