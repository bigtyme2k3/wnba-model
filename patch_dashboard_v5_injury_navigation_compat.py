from __future__ import annotations

import re
from pathlib import Path

HTML = Path('docs/index.html')


def inject_navigation(html: str) -> tuple[str, bool]:
    if re.search(r"['\"]injuries['\"]\s*,\s*['\"]Injuries['\"]", html):
        return html, True

    anchors = [
        r"(\[\s*['\"]ai-center['\"]\s*,\s*['\"]AI Center['\"]\s*\])",
        r"(\[\s*['\"]ai['\"]\s*,\s*['\"]AI Center['\"]\s*\])",
        r"(\[\s*['\"]best['\"]\s*,\s*['\"]Best Bets['\"]\s*\])",
        r"(\[\s*['\"]health['\"]\s*,\s*['\"]Data Health['\"]\s*\])",
        r"(\[\s*['\"]results['\"]\s*,\s*['\"]Results['\"]\s*\])",
    ]
    for pattern in anchors:
        updated, count = re.subn(pattern, "['injuries','Injuries']," + r"\1", html, count=1)
        if count:
            return updated, True

    # Generic compact tabs-array fallback.
    match = re.search(r"const\s+tabs\s*=\s*\[(.*?)\];", html, flags=re.S)
    if match:
        block = match.group(0)
        insertion = "['injuries','Injuries'],"
        updated = block.replace('[', '[' + insertion, 1)
        return html.replace(block, updated, 1), True
    return html, False


def inject_route(html: str) -> tuple[str, bool]:
    if re.search(r"view\s*===?\s*['\"]injuries['\"]", html):
        return html, True

    route = "else if(view==='injuries')html=invoke('Injury Intelligence',[window.injuryIntelligence]);"
    anchors = [
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]ai-center['\"])",
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]ai['\"])",
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]best['\"])",
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]health['\"])",
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]results['\"])",
    ]
    for pattern in anchors:
        updated, count = re.subn(pattern, route + r"\1", html, count=1)
        if count:
            return updated, True

    # Support renderers that assign root.innerHTML directly.
    direct = "else if(view==='injuries')root.innerHTML=(typeof window.injuryIntelligence==='function'?window.injuryIntelligence():'');"
    anchors = [
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]results['\"])",
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]portfolio['\"])",
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]health['\"])",
    ]
    for pattern in anchors:
        updated, count = re.subn(pattern, direct + r"\1", html, count=1)
        if count:
            return updated, True
    return html, False


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    html = HTML.read_text(encoding='utf-8')
    html, nav_ok = inject_navigation(html)
    html, route_ok = inject_route(html)
    HTML.write_text(html, encoding='utf-8')

    # Injury data and player-prop context remain useful even if a future
    # navigation redesign prevents exposing the dedicated tab.
    if nav_ok and route_ok:
        print('Injury Intelligence navigation and route repaired')
    else:
        print(f'Injury Intelligence compatibility warning: nav={nav_ok} route={route_ok}')


if __name__ == '__main__':
    main()
