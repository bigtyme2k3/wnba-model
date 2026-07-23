from __future__ import annotations

import json
from pathlib import Path

HTML = Path("docs/index.html")
DATA = Path("data/dashboard/wnba_alt_streaks.json")

CSS = r'''<style id="v4-alt-streaks-display-style">
.altStreakWrap{display:grid;gap:14px}.altStreakControls{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 14px}.altStreakControls button{border:1px solid #263854;background:#08101c;color:#cbd7f1;border-radius:999px;padding:8px 12px;font-weight:800}.altStreakControls button.a{background:#17315d;color:#fff}.altStreakPlayer{border:1px solid #21314b;border-radius:16px;background:#08101c;padding:14px}.altStreakPlayer summary{cursor:pointer;font-weight:950;font-size:17px}.altStreakGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;margin-top:12px}.altStreakCard{border:1px solid #263854;border-radius:12px;padding:11px;background:#0a1322}.altStreakTop{display:flex;justify-content:space-between;gap:8px;align-items:center}.altStreakLine{font-size:16px;font-weight:950;color:#34e6a1}.altStreakBook{font-size:11px;color:#9eb0cc}.altStreakMeta{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:9px}.altStreakMetric{border-top:1px solid #1d2d46;padding-top:6px;font-size:11px}.altStreakMetric b{display:block;font-size:14px}.altStreakValues{margin-top:8px;color:#8fa0bd;font-size:10px;word-break:break-word}.altStreakEmpty{padding:18px;text-align:center;color:#8fa0bd}.altStreakSummary{display:flex;gap:12px;flex-wrap:wrap;color:#8fa0bd;font-size:11px}
</style>'''

SCRIPT = r'''<script id="v4-alt-streaks-display-script">
(function(){
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const pct=v=>v==null?'—':(Number(v)*100).toFixed(0)+'%';
 const odds=v=>{const n=Number(v);return Number.isFinite(n)?(n>0?'+'+n:String(n)):'—'};
 let mode='alternate';
 function card(r){const vals=(r.recent_values||[]).slice(0,10).join(', ');return `<div class="altStreakCard"><div class="altStreakTop"><div><div class="altStreakLine">${esc(r.side)} ${esc(r.stat)} ${esc(r.alt_line)}</div><div class="altStreakBook">${esc(r.best_book||'Unknown book')} · ${odds(r.best_odds)}</div></div><b>${esc(r.streak)} straight</b></div><div class="altStreakMeta"><div class="altStreakMetric">L10<b>${esc(r.last10_hits??r.l10_hits??'—')}/${esc(r.last10_games??r.l10_games??'—')} · ${pct(r.last10_pct??r.l10_pct)}</b></div><div class="altStreakMetric">Season<b>${esc(r.season_hits??'—')}/${esc(r.season_games??'—')} · ${pct(r.season_pct)}</b></div><div class="altStreakMetric">Average<b>${esc(r.average??'—')}</b></div></div><div class="altStreakValues">Recent: ${esc(vals||'Unavailable')}</div></div>`}
 function render(){const p=(window.DATA&&DATA.alt_streaks)||{};const rows=Array.isArray(p.rows)?p.rows:[];const filtered=rows.filter(r=>mode==='all'||r.line_type===mode);const groups={};filtered.forEach(r=>{(groups[r.player]||(groups[r.player]=[])).push(r)});const players=Object.entries(groups).sort((a,b)=>Math.max(...b[1].map(x=>x.streak||0))-Math.max(...a[1].map(x=>x.streak||0)));const s=p.summary||{};return `<div class="section"><h2 class="mono">ALT Streak Board</h2><div class="small mono">Exact sportsbook thresholds with verified current streaks. Books and lines stay separate.</div><div class="altStreakSummary"><span>${esc(s.alternate_rows||0)} ALT rows</span><span>${esc(s.alternate_players||0)} players</span><span>${esc((s.alternate_books||[]).length)} books</span><span>Minimum streak ${esc(s.minimum_streak||3)}</span></div><div class="altStreakControls"><button class="${mode==='alternate'?'a':''}" onclick="window.setAltStreakMode('alternate')">ALT only</button><button class="${mode==='standard'?'a':''}" onclick="window.setAltStreakMode('standard')">Standard</button><button class="${mode==='all'?'a':''}" onclick="window.setAltStreakMode('all')">All</button></div><div class="altStreakWrap">${players.map(([player,items])=>`<details class="altStreakPlayer"><summary>${esc(player)} <span class="small mono">${items.length} lines · best ${Math.max(...items.map(x=>x.streak||0))} straight</span></summary><div class="altStreakGrid">${items.map(card).join('')}</div></details>`).join('')||'<div class="altStreakEmpty mono">No active streaks match this filter.</div>'}</div></div>`}
 window.setAltStreakMode=function(next){mode=next;const root=document.getElementById('root');if(root&&typeof window.render==='function')window.render('altstreaks')};
 window.altStreaks=render;
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


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    try:
        payload = json.load(DATA.open(encoding="utf-8")) if DATA.exists() else {}
    except Exception:
        payload = {}
    html = HTML.read_text(encoding="utf-8")
    data = f'<script id="v4-alt-streaks-display-data">window.DATA=window.DATA||{{}};DATA.alt_streaks={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html = replace_block(html, '<script id="v4-alt-streaks-display-data">', '</script>', data) if 'id="v4-alt-streaks-display-data"' in html else html.replace('</body>', data + '</body>')
    html = replace_block(html, '<style id="v4-alt-streaks-display-style">', '</style>', CSS) if 'id="v4-alt-streaks-display-style"' in html else html.replace('</head>', CSS + '</head>')
    html = replace_block(html, '<script id="v4-alt-streaks-display-script">', '</script>', SCRIPT) if 'id="v4-alt-streaks-display-script"' in html else html.replace('</body>', SCRIPT + '</body>')
    HTML.write_text(html, encoding="utf-8")
    try:
        from patch_dashboard_v4_daily_edges import main as patch_daily_edges
        patch_daily_edges()
    except Exception as exc:
        raise RuntimeError(f"Daily Edges dashboard patch failed: {exc}") from exc
    print("ALT streak and Daily Edges dashboards embedded")


if __name__ == "__main__":
    main()
