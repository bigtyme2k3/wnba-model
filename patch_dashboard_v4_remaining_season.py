from __future__ import annotations

import json
import re
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_remaining_season_intelligence.json')

CSS = r'''<style id="v4-remaining-season-style">
.rsGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.rsCard{border:1px solid #22334f;border-radius:12px;padding:11px;background:#08101c}
.rsRow{display:grid;grid-template-columns:50px 1fr repeat(5,minmax(70px,.7fr));gap:8px;padding:8px 4px;border-bottom:1px solid #17233a;align-items:center;font-size:12px}
.rsHard{color:#ff8b9d}.rsEasy{color:#49e3a5}
@media(max-width:700px){.rsRow{grid-template-columns:42px 1fr 70px 70px}.rsHide{display:none}}
</style>'''

SCRIPT = r'''<script id="v4-remaining-season-script">
/* WNBA_REMAINING_SEASON_ROUTE view==='remaining' */
(function(){
 const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 window.remainingSeasonView=function(){
  const d=(window.DATA&&DATA.remaining_season)||{},s=d.summary||{},t=d.teams||[],g=d.games||[];
  const rows=t.map(x=>`<div class="rsRow"><b>#${e(x.difficulty_rank)}</b><b>${e(x.team)}</b><span>${e(x.remaining_games)} games</span><span>${e(x.schedule_difficulty)} diff</span><span class="rsHide">${e(x.back_to_backs)} B2B</span><span class="rsHide">${e(x.three_in_four)} 3-in-4</span><span class="rsHide">${e(x.travel_miles)} mi</span></div>`).join('');
  return `<div class="section"><h2 class="mono">Remaining Season Intelligence</h2><div class="rsGrid"><div class="rsCard"><div class="small">Remaining games</div><b>${e(s.remaining_games||0)}</b></div><div class="rsCard"><div class="small">Teams tracked</div><b>${e(s.teams||0)}</b></div><div class="rsCard"><div class="small">First game</div><b>${e((s.first_game_utc||'').slice(0,10)||'—')}</b></div><div class="rsCard"><div class="small">Last game</div><b>${e((s.last_game_utc||'').slice(0,10)||'—')}</b></div></div></div><div class="section"><h3 class="mono">Schedule Difficulty</h3>${rows||'<div class="empty mono">Schedule data not loaded.</div>'}</div><div class="section"><h3 class="mono">Next Games</h3>${g.slice(0,20).map(x=>`<div class="prodGate"><span>${e(x.away)} @ ${e(x.home)}</span><b>${e((x.date_utc||'').replace('T',' ').slice(0,16))} UTC</b></div>`).join('')}</div></div>`;
 };
})();
</script>'''


def replace_block(html: str, start: str, end: str, replacement: str) -> str:
    i = html.find(start)
    if i < 0:
        return html
    j = html.find(end, i)
    if j < 0:
        return html
    return html[:i] + replacement.strip() + html[j + len(end):]


def inject_navigation(html: str) -> tuple[str, bool]:
    if re.search(r"['\"]remaining['\"]\s*,\s*['\"]Remaining Season['\"]", html):
        return html, True

    patterns = [
        r"(\[\s*['\"]production['\"]\s*,\s*['\"]Production['\"]\s*\])",
        r"(\[\s*['\"]mission['\"]\s*,\s*['\"]Mission Control['\"]\s*\])",
        r"(\[\s*['\"]health['\"]\s*,\s*['\"]V4 Health['\"]\s*\])",
    ]
    for pattern in patterns:
        updated, count = re.subn(pattern, "['remaining','Remaining Season']," + r"\1", html, count=1)
        if count:
            return updated, True
    return html, False


def inject_route(html: str) -> tuple[str, bool]:
    if re.search(r"view\s*===?\s*['\"]remaining['\"]", html):
        return html, True

    route_patterns = [
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]production['\"]\s*\)\s*root\.innerHTML\s*=\s*safe\(window\.productionReadiness\))",
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]mission['\"]\s*\))",
        r"(else\s+if\s*\(\s*view\s*===?\s*['\"]health['\"]\s*\))",
    ]
    insertion = "else if(view==='remaining')root.innerHTML=safe(window.remainingSeasonView);"
    for pattern in route_patterns:
        updated, count = re.subn(pattern, insertion + r"\1", html, count=1)
        if count:
            return updated, True
    return html, False


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')

    try:
        payload = json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
    except Exception:
        payload = {}

    html = HTML.read_text(encoding='utf-8')
    blob = '<script id="v4-remaining-season-data">window.DATA=window.DATA||{};DATA.remaining_season=' + json.dumps(payload, separators=(',', ':')) + ';</script>'

    if 'id="v4-remaining-season-data"' in html:
        html = replace_block(html, '<script id="v4-remaining-season-data">', '</script>', blob)
    else:
        html = html.replace('</body>', blob + '</body>')

    if 'id="v4-remaining-season-style"' in html:
        html = replace_block(html, '<style id="v4-remaining-season-style">', '</style>', CSS)
    else:
        html = html.replace('</head>', CSS + '</head>')

    if 'id="v4-remaining-season-script"' in html:
        html = replace_block(html, '<script id="v4-remaining-season-script">', '</script>', SCRIPT)
    else:
        html = html.replace('</body>', SCRIPT + '</body>')

    html, nav_ok = inject_navigation(html)
    html, route_ok = inject_route(html)

    if not nav_ok:
        raise SystemExit('Remaining Season patch failed: navigation anchor not found')
    if not route_ok:
        raise SystemExit('Remaining Season patch failed: router anchor not found')
    if not re.search(r"view\s*===?\s*['\"]remaining['\"]", html):
        raise SystemExit('Remaining Season patch failed: route marker absent after injection')

    HTML.write_text(html, encoding='utf-8')
    print('Remaining Season Intelligence tab and route embedded')


if __name__ == '__main__':
    main()
