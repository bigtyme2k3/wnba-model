from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_alt_market_warehouse.json')
CSS=r'''<style id="v4-alt-ladders-style">.alWrap{display:grid;gap:14px}.alPlayer{border:1px solid #21314b;border-radius:16px;background:#08101c;padding:14px}.alPlayer summary{cursor:pointer;font-weight:950;font-size:17px}.alStat{margin-top:12px;border-top:1px solid #20304b;padding-top:10px}.alBooks{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}.alBook{border:1px solid #263854;border-radius:12px;padding:10px;background:#0a1322}.alBookTitle{font-weight:900;margin-bottom:7px}.alLine{display:grid;grid-template-columns:68px 64px 1fr 1fr 1fr;gap:6px;align-items:center;padding:6px 0;border-top:1px solid #1c2a42;font-size:11px}.alLine:first-of-type{border-top:0}.alGood{color:#00e39b}.alBad{color:#ff6b7c}.alMuted{color:#8fa0bd}.alPill{border:1px solid currentColor;border-radius:999px;padding:3px 6px;text-align:center;font-weight:900}.alEmpty{padding:18px;text-align:center;color:#8fa0bd}@media(max-width:700px){.alLine{grid-template-columns:60px 58px 1fr 1fr}.alLine .alEv{display:none}}</style>'''
SCRIPT=r'''<script id="v4-alt-ladders-script">(function(){function pct(v){return v==null?'—':(Number(v)*100).toFixed(0)+'%'}function odds(v){const n=Number(v);return Number.isFinite(n)?(n>0?'+'+n:n):'—'}function lineCard(r){const ev=Number(r.expected_value_per_unit);const cls=Number.isFinite(ev)?(ev>0?'alGood':'alBad'):'alMuted';return `<div class="alLine"><span class="alPill">${E(r.display_threshold||r.threshold)}</span><b class="mono">${odds(r.odds)}</b><span>L5 ${pct(r.l5?.rate)}</span><span>L10 ${pct(r.l10?.rate)}</span><span class="alEv ${cls}">EV ${Number.isFinite(ev)?(ev*100).toFixed(1)+'%':'—'}</span></div>`}function bookCard(book){return `<div class="alBook"><div class="alBookTitle">${E(book.sportsbook)}</div>${(book.lines||[]).map(lineCard).join('')}</div>`}function playerCard(player){const stats=Object.values(player.stats||{}).map(stat=>`<div class="alStat"><b>${E(stat.stat)}</b><div class="alBooks">${Object.values(stat.sportsbooks||{}).map(bookCard).join('')}</div></div>`).join('');return `<details class="alPlayer"><summary>${E(player.player)} <span class="small mono">${E(player.game||'')}</span></summary>${stats}</details>`}window.altLadders=function(){const p=DATA.alt_market_warehouse||{},players=Array.isArray(p.players)?p.players:[],s=p.summary||{};return `<div class="section"><h2 class="mono">Sportsbook ALT Ladders</h2><div class="small mono">Exact thresholds by sportsbook. FanDuel, DraftKings, Fanatics, and other books remain separate; lines are never averaged.</div><div class="row"><span>${E(s.markets||0)} markets</span><span>${E(s.players||0)} players</span><span>${(s.sportsbooks||[]).map(E).join(', ')||'No books'}</span></div><div class="alWrap">${players.map(playerCard).join('')||'<div class="alEmpty mono">No true sportsbook alternate ladders were returned.</div>'}</div></div>`};const prior=window.altStreaks;window.altStreaks=function(){const base=typeof prior==='function'?prior():'';return window.altLadders()+base}})();</script>'''

def replace_block(html,start,end,replacement):
    i=html.find(start)
    if i<0:return html
    j=html.find(end,i)
    if j<0:return html
    return html[:i]+replacement.strip()+html[j+len(end):]

def main():
    if not HTML.exists():raise SystemExit('docs/index.html missing')
    try:payload=json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
    except Exception:payload={}
    html=HTML.read_text(encoding='utf-8')
    data=f'<script id="v4-alt-ladders-data">DATA.alt_market_warehouse={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html=replace_block(html,'<script id="v4-alt-ladders-data">','</script>',data) if 'id="v4-alt-ladders-data"' in html else html.replace('</body>',data+'</body>')
    html=replace_block(html,'<style id="v4-alt-ladders-style">','</style>',CSS) if 'id="v4-alt-ladders-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace_block(html,'<script id="v4-alt-ladders-script">','</script>',SCRIPT) if 'id="v4-alt-ladders-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8')
    print('Sportsbook ALT ladders added to Player Props')
if __name__=='__main__':main()
