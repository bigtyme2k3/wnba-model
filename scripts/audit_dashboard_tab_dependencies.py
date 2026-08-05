from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path('.')
OUT_JSON = Path('docs/audit/dashboard_tab_dependency_map.json')
OUT_MD = Path('docs/audit/DASHBOARD_TAB_DEPENDENCY_MAP.md')

BUILD_CHAIN = [
    Path('build_dashboard_v4.py'),
    Path('patch_dashboard_v4_games_markets.py'),
    Path('patch_dashboard_v4_consistency.py'),
    Path('patch_dashboard_v4_live_slate.py'),
    Path('patch_dashboard_v4_portfolio_ai.py'),
    Path('patch_dashboard_navigation_v2.py'),
]

TABS = [
    'Games', 'Game Performance', 'Game Props', 'Player Props', 'ALT Streaks',
    'ALT Performance', 'Daily Edges', 'Ensemble', 'Simulation', 'Best Bets',
    'Portfolio', 'AI Center', 'Results', 'Performance',
]

JSON_RE = re.compile(r"(?:data/dashboard/)?[A-Za-z0-9_./-]+\.json")
FUNC_RE = re.compile(r"(?:function\s+|window\.)([A-Za-z0-9_]+)\s*(?:=\s*function)?\s*\(")
SYNTHETIC_PATTERNS = {
    'team_guess_from_player_name': re.compile(r"player\|\|''\)\.length\)%2|length\)%2"),
    'synthetic_history_generator': re.compile(r"function\s+hist\s*\(|wig=\["),
    'silent_json_fallback': re.compile(r"except\s+Exception:\s*\n\s*pass|return\s+default"),
    'missing_model_placeholder': re.compile(r"Model pending"),
}

TAB_HINTS = {
    'Games': ['games', 'gamesV25'],
    'Game Performance': ['gamePerformance', 'performance'],
    'Game Props': ['marketsV25', 'gameProps', 'markets'],
    'Player Props': ['props', 'playerProps'],
    'ALT Streaks': ['altStreak', 'streak'],
    'ALT Performance': ['altPerformance'],
    'Daily Edges': ['dailyEdges', 'edges'],
    'Ensemble': ['ensemble'],
    'Simulation': ['simulation', 'monte'],
    'Best Bets': ['bestBets', 'best'],
    'Portfolio': ['portfolio'],
    'AI Center': ['aiCenter', 'ai'],
    'Results': ['results'],
    'Performance': ['performance'],
}


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def main() -> None:
    files = []
    all_json = set()
    for path in BUILD_CHAIN:
        text = read(path)
        json_refs = sorted(set(JSON_RE.findall(text)))
        funcs = sorted(set(FUNC_RE.findall(text)))
        flags = [name for name, rx in SYNTHETIC_PATTERNS.items() if rx.search(text)]
        files.append({
            'file': str(path),
            'exists': path.exists(),
            'json_references': json_refs,
            'functions': funcs,
            'risk_flags': flags,
        })
        all_json.update(json_refs)

    tabs = []
    for tab in TABS:
        hints = [h.lower() for h in TAB_HINTS.get(tab, [])]
        owners = []
        sources = set()
        flags = set()
        for item in files:
            funcs = [f.lower() for f in item['functions']]
            file_text = read(Path(item['file'])).lower()
            if any(h in funcs or h in file_text for h in hints):
                owners.append(item['file'])
                sources.update(item['json_references'])
                flags.update(item['risk_flags'])
        tabs.append({
            'tab': tab,
            'renderers': sorted(set(owners)),
            'json_sources': sorted(sources),
            'risk_flags': sorted(flags),
            'status': 'mapped' if owners else 'unmapped',
        })

    payload = {
        'build_chain': [str(p) for p in BUILD_CHAIN],
        'files': files,
        'tabs': tabs,
        'all_json_references': sorted(all_json),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    lines = ['# Dashboard Tab Dependency Map', '', '## Build chain', '']
    for path in BUILD_CHAIN:
        lines.append(f'- `{path}`')
    lines += ['', '## Tab ownership', '']
    for tab in tabs:
        lines.append(f"### {tab['tab']}")
        lines.append(f"- Status: **{tab['status']}**")
        lines.append('- Renderers: ' + (', '.join(f'`{x}`' for x in tab['renderers']) or 'None found'))
        lines.append('- JSON sources: ' + (', '.join(f'`{x}`' for x in tab['json_sources']) or 'None found'))
        lines.append('- Risk flags: ' + (', '.join(tab['risk_flags']) or 'None detected'))
        lines.append('')
    lines += ['## Immediate blockers', '']
    blockers = []
    for item in files:
        for flag in item['risk_flags']:
            blockers.append((item['file'], flag))
    for path, flag in blockers:
        lines.append(f'- `{path}` — **{flag}**')
    if not blockers:
        lines.append('- None detected.')
    OUT_MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'tabs': len(tabs), 'mapped': sum(t['status']=='mapped' for t in tabs), 'risk_flags': len(blockers)}, indent=2))


if __name__ == '__main__':
    main()
