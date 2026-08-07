from __future__ import annotations

import json
import re
from pathlib import Path

HTML = Path('docs/index.html')
DASH = Path('data/dashboard')
MARKER = 'canonical-daily-runtime-v1'
END_MARKER = 'canonical-daily-runtime-end-v1'


def load(name: str, default):
    path = DASH / name
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')

    manifest = load('wnba_daily_canonical_manifest.json', {})
    master = load('wnba_master.json', {})
    props = load('wnba_player_props.json', {})
    target = str(manifest.get('target_date') or master.get('target_date') or props.get('target_date') or '')
    games = master.get('today_games') or []
    rows = props.get('rows') or []

    if not target:
        raise SystemExit('Canonical target date missing')
    if manifest.get('status') != 'PASS':
        raise SystemExit(f"Canonical manifest not PASS: {manifest.get('failures')}")
    if props.get('target_date') != target:
        raise SystemExit('Canonical player props date mismatch')

    payload = json.dumps({
        'target_date': target,
        'generated_at_utc': manifest.get('generated_at_utc'),
        'games': games,
        'props': rows,
        'game_count': len(games),
        'prop_count': len(rows),
    }, ensure_ascii=False).replace('</', '<\\/')

    block = f'''\n<!-- {MARKER} -->
<style id="canonical-daily-runtime-style">
.canon-panel{{border:1px solid #26334f;border-radius:18px;background:#0b1220;padding:16px;color:#e5e7eb}}
.canon-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
.canon-card{{border:1px solid #26334f;border-radius:14px;padding:13px;background:#0b1020}}
.canon-table{{width:100%;border-collapse:collapse}}.canon-table th,.canon-table td{{padding:11px;border-bottom:1px solid #26334f;text-align:left}}
.canon-muted{{color:#94a3b8;font-size:12px}}.canon-good{{color:#34d399}}@media(max-width:800px){{.canon-grid{{grid-template-columns:1fr}}}}
</style>
<script id="canonical-daily-runtime-script">
(function(){{
 const C={payload}; window.WNBA_CANONICAL_DAILY=C;
 const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
 const exact=t=>[...document.querySelectorAll('h1,h2,h3,h4,div,span,p')].find(e=>e.children.length===0&&e.textContent.trim()===t);
 function updateDate(){{
   const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
   let n; while(n=walker.nextNode()){{
     if(/Slate\s+\d{{4}}-\d{{2}}-\d{{2}}/.test(n.nodeValue)) n.nodeValue=n.nodeValue.replace(/Slate\s+\d{{4}}-\d{{2}}-\d{{2}}/,'Slate '+C.target_date);
   }}
 }}
 function gamesHtml(){{return `<div class="canon-panel" data-canonical-panel="games"><h2>Today's Games</h2><div class="canon-muted">Canonical slate ${{esc(C.target_date)}} · ${{C.game_count}} games</div><div class="canon-grid" style="margin-top:12px">${{C.games.map(g=>`<div class="canon-card"><b>${{esc(g.game)}}</b><div class="canon-muted">${{esc(g.start_time)}} · ${{esc(g.status)}}</div><div style="margin-top:8px">Spread ${{esc(g.spread)}} · Total ${{esc(g.total)}}</div></div>`).join('')||'<div class="canon-card">No games scheduled.</div>'}}</div></div>`}}
 function propsHtml(){{return `<div class="canon-panel" data-canonical-panel="props"><h2>Player Props</h2><div class="canon-muted">Canonical Odds API rows · ${{C.prop_count}} props · ${{esc(C.target_date)}}</div><div style="overflow:auto;margin-top:12px"><table class="canon-table"><thead><tr><th>Player</th><th>Game</th><th>Stat</th><th>Line</th><th>Best Over</th><th>Best Under</th><th>History</th></tr></thead><tbody>${{C.props.slice(0,500).map(r=>`<tr><td><b>${{esc(r.player)}}</b><div class="canon-muted">${{esc(r.team)}}</div></td><td>${{esc(r.game)}}</td><td class="canon-good">${{esc(r.stat)}}</td><td>${{esc(r.line)}}</td><td>${{esc(r.best_over_book)}} ${{esc(r.best_over_price)}}</td><td>${{esc(r.best_under_book)}} ${{esc(r.best_under_price)}}</td><td>—</td></tr>`).join('')}}</tbody></table></div></div>`}}
 function replacePanel(title,html,requiredWords,key){{
   if(document.querySelector(`[data-canonical-panel="${{key}}"]`)) return true;
   const h=exact(title); if(!h) return false; let p=h;
   for(let i=0;i<7&&p;i++,p=p.parentElement){{
     const txt=p.textContent||'';
     if(requiredWords.every(w=>txt.includes(w))){{
       const wrapper=document.createElement('div'); wrapper.innerHTML=html;
       p.replaceWith(wrapper.firstElementChild); return true;
     }}
   }}
   return false;
 }}
 function apply(){{
   updateDate();
   replacePanel("Today's Games",gamesHtml(),['Yesterday Results'],'games');
   replacePanel('Player Props',propsHtml(),['All Games','Showing'],'props');
   document.querySelectorAll('*').forEach(e=>{{if(e.children.length===0&&/\b(?:NaN|null%)\b/.test(e.textContent||''))e.textContent='—'}});
 }}
 apply(); setTimeout(apply,500); setTimeout(apply,1800);
 new MutationObserver(()=>{{clearTimeout(window.__canonTimer);window.__canonTimer=setTimeout(apply,120)}}).observe(document.body,{{childList:true,subtree:true}});
}})();
</script>
<!-- {END_MARKER} -->\n'''

    html = HTML.read_text(encoding='utf-8')
    html = re.sub(
        rf'\n?<!-- {re.escape(MARKER)} -->.*?<!-- {re.escape(END_MARKER)} -->\n?',
        '\n',
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        rf'\n?<!-- {re.escape(MARKER)} -->\s*<style id="canonical-daily-runtime-style">.*?</style>\s*<script id="canonical-daily-runtime-script">.*?</script>\s*',
        '\n',
        html,
        count=1,
        flags=re.S,
    )
    if '</body>' in html:
        html = html.replace('</body>', block + '\n</body>', 1)
    else:
        raise SystemExit('Dashboard shell invalid: closing body tag missing before canonical patch')

    HTML.write_text(html, encoding='utf-8')
    print({'target_date': target, 'games': len(games), 'props': len(rows), 'marker': MARKER, 'shell_preserved': True})


if __name__ == '__main__':
    main()
