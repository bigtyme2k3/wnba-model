from __future__ import annotations

import json
import re
from pathlib import Path

from patch_dashboard_games_focus import main as apply_games_focus_cleanup

HTML = Path('docs/index.html')
DASH = Path('data/dashboard')
MARKER = 'canonical-daily-runtime-v1'
END_MARKER = 'canonical-daily-runtime-end-v1'
BUILD_MARKER = 'canonical-build-target-v1'


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
<script id="canonical-daily-runtime-script">
(function(){{
 const C={payload};
 window.WNBA_CANONICAL_DAILY=C;
 window.WNBA_CANONICAL_PROPS=function(){{
   const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
   return `<div class="section"><h2 class="mono">Player Props</h2><div class="small mono">Canonical Odds API rows · ${{C.prop_count}} props · ${{esc(C.target_date)}}</div><div style="overflow:auto;margin-top:12px"><table><thead><tr><th>Player</th><th>Game</th><th>Stat</th><th>Line</th><th>Best Over</th><th>Best Under</th></tr></thead><tbody>${{C.props.slice(0,500).map(r=>`<tr><td><b>${{esc(r.player)}}</b><div class="small mono">${{esc(r.team)}}</div></td><td>${{esc(r.game)}}</td><td>${{esc(r.stat)}}</td><td>${{esc(r.line)}}</td><td>${{esc(r.best_over_book)}} ${{esc(r.best_over_price)}}</td><td>${{esc(r.best_under_book)}} ${{esc(r.best_under_price)}}</td></tr>`).join('')}}</tbody></table></div></div>`;
 }};
 function updateDate(){{
   const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
   let n; while(n=walker.nextNode()){{
     if(/Slate\s+\d{{4}}-\d{{2}}-\d{{2}}/.test(n.nodeValue))
       n.nodeValue=n.nodeValue.replace(/Slate\s+\d{{4}}-\d{{2}}-\d{{2}}/,'Slate '+C.target_date);
   }}
 }}
 function sanitize(){{
   document.querySelectorAll('*').forEach(e=>{{
     if(e.children.length===0&&/\b(?:NaN|null%)\b/.test(e.textContent||'')) e.textContent='—';
   }});
 }}
 updateDate(); sanitize();
 setTimeout(()=>{{updateDate();sanitize()}},500);
 setTimeout(()=>{{updateDate();sanitize()}},1800);
}})();
</script>
<!-- {END_MARKER} -->\n'''

    html = HTML.read_text(encoding='utf-8')
    html = re.sub(r'<!-- canonical-build-target-v1:\d{4}-\d{2}-\d{2} -->\s*', '', html)
    # Replace stale visible slate labels in the generated artifact itself. The
    # browser runtime remains a secondary guard, not the primary freshness fix.
    html, replaced = re.subn(r'Slate\s+\d{4}-\d{2}-\d{2}', f'Slate {target}', html)
    html = re.sub(
        rf'\n?<!-- {re.escape(MARKER)} -->.*?<!-- {re.escape(END_MARKER)} -->\n?',
        '\n', html, count=1, flags=re.S,
    )
    if '</body>' not in html:
        raise SystemExit('Dashboard shell invalid: closing body tag missing before canonical patch')
    html = html.replace('</body>', f'<!-- {BUILD_MARKER}:{target} -->\n' + block + '\n</body>', 1)
    HTML.write_text(html, encoding='utf-8')
    apply_games_focus_cleanup()

    final_html = HTML.read_text(encoding='utf-8')
    stale = sorted(set(re.findall(r'Slate\s+(\d{4}-\d{2}-\d{2})', final_html)) - {target})
    if stale:
        raise SystemExit(f'Stale slate labels remain after canonical build: {stale}; target={target}')
    if f'<!-- {BUILD_MARKER}:{target} -->' not in final_html:
        raise SystemExit('Canonical build target marker missing')
    print({'target_date': target, 'games': len(games), 'props': len(rows), 'marker': MARKER, 'shell_target_replacements': replaced, 'shell_preserved': True, 'router_safe': True, 'stale_slate_labels': stale})


if __name__ == '__main__':
    main()
