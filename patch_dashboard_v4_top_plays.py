from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_cross_market_top_plays.json')
CSS=r'''<style id="v4-top-plays-style">.tpGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px}.tpCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.tpRank{font-size:22px;font-weight:950}.tpScore{font-size:28px;font-weight:950}.tpMeta{color:#8fa0bd;font-size:11px}.tpBet{color:#00e39b;font-weight:900}.tpLean{color:#ffd166;font-weight:900}.tpWatch{color:#7fb3ff;font-weight:900}.tpPass{color:#ff4d67;font-weight:900}.tpUnits{margin-top:8px;border-top:1px solid #20304b;padding-top:8px}</style>'''
SCRIPT=r'''<script id="v4-top-plays-script">(function(){window.topPlays=function(){const p=DATA.top_plays||{},rows=Array.isArray(p.top_plays)?p.top_plays:[];const cards=rows.map(r=>{const cls=r.decision==='BET'?'tpBet':r.decision==='LEAN'?'tpLean':r.decision==='WATCH'?'tpWatch':'tpPass';const play=r.player?`${E(r.player)} ${E(r.side)} ${E(r.line)} ${E(r.stat)}`:`${E(r.game)} ${E(r.side)} ${E(r.line)} ${E(r.stat)}`;return `<div class="tpCard"><div class="row"><div class="tpRank mono">#${E(r.rank)}</div><div class="tpScore mono">${E(r.top_play_score)}</div></div><b>${play}</b><div class="tpMeta mono">${E(r.market_type)} · ${E(r.sportsbook||'—')} · ${E(r.odds||'—')}</div><div class="row"><span class="${cls}">${E(r.decision)}</span><span class="mono">${Math.round(Number(r.hit_probability||0)*100)}% hit</span><span class="mono">EV ${r.expected_value_per_unit==null?'—':(Number(r.expected_value_per_unit)*100).toFixed(1)+'%'}</span></div><div class="tpMeta">Confidence ${E(r.confidence||'—')} · Risk ${E(r.risk_level)} · Quality ${E(r.data_quality_status)}</div><div class="tpUnits mono">Units ${E(r.recommended_units_final??0)}${r.exposure_penalty?` · ${E(r.exposure_penalty)}`:''}</div></div>`}).join('');const s=p.summary||{};return `<div class="section"><h2 class="mono">Cross-Market Top Plays</h2><div class="small mono">Game markets, standard props, and ALT props ranked together with exposure controls.</div><div class="row"><div class="kpi"><b>${E(s.bets||0)}</b><span>BET</span></div><div class="kpi"><b>${E(s.leans||0)}</b><span>LEAN</span></div><div class="kpi"><b>${E(s.allocated_units||0)}</b><span>UNITS</span></div></div><div class="tpGrid">${cards||'<div class="empty mono">No qualified priced markets available.</div>'}</div></div>`};window.best=window.topPlays;})();</script>'''
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
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-top-plays-data">DATA.top_plays={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-top-plays-data">','</script>',data) if 'id="v4-top-plays-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-top-plays-style">','</style>',CSS) if 'id="v4-top-plays-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-top-plays-script">','</script>',SCRIPT) if 'id="v4-top-plays-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Cross-Market Top Plays installed as Best Bets')
if __name__=='__main__':main()
