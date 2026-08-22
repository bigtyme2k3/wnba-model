from __future__ import annotations

import json
from pathlib import Path

HTML = Path("docs/index.html")
PARLAYS = Path("data/dashboard/wnba_alt_parlays.json")

STYLE = r'''<style id="best-bets-alt-parlays-style">
.altParlayWrap{display:grid;gap:12px;margin-top:14px}.altParlayGame{border:1px solid #243653;border-radius:14px;padding:12px;background:#091321}.altParlayGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;margin-top:10px}.altParlayCard{border:1px solid #2c4163;border-radius:12px;padding:11px;background:#0b1627}.altParlayTier{font-size:10px;font-weight:900;letter-spacing:.08em}.altParlayTier.SAFE{color:#00e39b}.altParlayTier.BALANCED{color:#f3c969}.altParlayTier.UPSIDE{color:#9db6ff}.altLeg{padding:7px 0;border-top:1px solid #1b2b45}.altLeg:first-of-type{border-top:0}.altParlayPrice{font-size:18px;font-weight:950}.altParlayNote{font-size:10px;color:#8fa0bd;margin-top:8px}@media(max-width:700px){.altParlayGrid{grid-template-columns:1fr}}
</style>'''

SCRIPT = r'''<script id="best-bets-alt-parlays-script">
(function(){
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const pct=v=>v==null?'—':`${Math.round(Number(v)*100)}%`;
 const odds=v=>{const n=Number(v);return Number.isFinite(n)?(n>0?'+'+Math.round(n):String(Math.round(n))):'—'};
 function leg(l){const ev=Number(l.expected_value_per_unit);return `<div class="altLeg"><b>${esc(l.player||'')}</b> · ${esc(l.stat||'')} ${esc(l.side||'')} ${esc(l.display_threshold||l.threshold||'')}<div class="small mono">${esc(l.sportsbook||'')} ${odds(l.odds)} · L5 ${pct(l.l5_rate)} · L10 ${pct(l.l10_rate)}${Number.isFinite(ev)?` · EV ${(ev*100).toFixed(1)}%`:''}</div></div>`}
 function card(p){return `<div class="altParlayCard"><div class="row"><span class="altParlayTier ${esc(p.tier||'')}">${esc(p.tier||'')}</span><span class="altParlayPrice mono">${odds(p.estimated_independent_price)}</span></div><div class="small mono">${p.kind==='CROSS_GAME_ALT'?'Cross-game ALT':'Same-game ALT'} · ${esc(p.leg_count||0)} legs</div>${(p.legs||[]).map(leg).join('')}<div class="altParlayNote">Estimated independent price only; sportsbook SGP pricing/correlation may differ.</div></div>`}
 function section(){const src=(window.DATA&&DATA.best_bets_alt_parlays)||{},all=Array.isArray(src.parlays)?src.parlays:[];if(!all.length)return '<div class="section"><h2 class="mono">ALT Prop Parlays</h2><div class="empty mono">No current ALT parlay cards qualified.</div></div>';const same=all.filter(p=>p.kind==='SAME_GAME_ALT'),cross=all.filter(p=>p.kind==='CROSS_GAME_ALT'),groups={};same.forEach(p=>{const g=(p.games||[])[0]||'Game';(groups[g]||(groups[g]=[])).push(p)});let h=`<div class="section"><div class="row"><div><h2 class="mono">ALT Prop Parlays</h2><div class="small mono">2–3 cards per game plus mixed-game cards when the slate supports them.</div></div><div class="badge mono">${all.length} cards</div></div><div class="altParlayWrap">`;Object.entries(groups).forEach(([g,ps])=>{h+=`<div class="altParlayGame"><b class="mono">${esc(g)}</b><div class="altParlayGrid">${ps.map(card).join('')}</div></div>`});if(cross.length)h+=`<div class="altParlayGame"><b class="mono">Cross-Game Mix</b><div class="altParlayGrid">${cross.map(card).join('')}</div></div>`;return h+'</div></div>'}
 const prior=window.best;
 window.best=function(){const base=typeof prior==='function'?prior():'';return base+section()};
})();
</script>'''


def replace_block(html: str, marker: str, end: str, replacement: str) -> str:
    i = html.find(marker)
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
        payload = json.load(PARLAYS.open(encoding="utf-8")) if PARLAYS.exists() else {}
    except Exception:
        payload = {}
    html = HTML.read_text(encoding="utf-8")
    data = f'<script id="best-bets-alt-parlays-data">window.DATA=window.DATA||{{}};DATA.best_bets_alt_parlays={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html = replace_block(html, '<script id="best-bets-alt-parlays-data">', '</script>', data) if 'id="best-bets-alt-parlays-data"' in html else html.replace('</body>', data + '</body>')
    html = replace_block(html, '<style id="best-bets-alt-parlays-style">', '</style>', STYLE) if 'id="best-bets-alt-parlays-style"' in html else html.replace('</head>', STYLE + '</head>')
    html = replace_block(html, '<script id="best-bets-alt-parlays-script">', '</script>', SCRIPT) if 'id="best-bets-alt-parlays-script"' in html else html.replace('</body>', SCRIPT + '</body>')
    HTML.write_text(html, encoding="utf-8")
    print({"best_bets_alt_parlays": len(payload.get("parlays") or []), "target_date": payload.get("target_date")})


if __name__ == "__main__":
    main()
