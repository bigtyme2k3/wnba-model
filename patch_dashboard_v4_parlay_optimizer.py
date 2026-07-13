from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_parlay_optimizer_v2.json')
CSS=r'''<style id="v4-parlay-optimizer-style">.parlayGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.parlayCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.parlayLeg{padding:6px 0;border-bottom:1px solid #1d2b42}.parlayScore{font-size:26px;font-weight:950}.parlayWarn{color:#ffd166;font-size:11px}.parlayBet{color:#00e39b;font-weight:900}.parlayLean{color:#ffd166;font-weight:900}.parlayPass{color:#ff4d67;font-weight:900}</style>'''
SCRIPT=r'''<script id="v4-parlay-optimizer-script">(function(){window.parlayOptimizer=function(){const p=DATA.parlay_optimizer||{},rows=Array.isArray(p.parlays)?p.parlays:[];const cards=rows.map(r=>{const cls=r.action==='BET'?'parlayBet':r.action==='LEAN'?'parlayLean':'parlayPass';const legs=(r.legs||[]).map(l=>`<div class="parlayLeg mono">${E(l.player||'')} ${E(l.stat)} ${E(l.side)} ${E(l.line)} · ${E(l.sportsbook||'—')} ${E(l.odds||'—')}</div>`).join('');return `<div class="parlayCard"><div class="row"><b>#${E(r.rank)} ${E(r.parlay_type)}</b><div class="parlayScore mono">${E(r.score)}</div></div>${legs}<div class="row"><span class="${cls}">${E(r.action)}</span><span class="mono">Joint ${Math.round(Number(r.joint_probability||0)*100)}%</span><span class="mono">EV ${r.expected_value_per_unit==null?'—':(Number(r.expected_value_per_unit)*100).toFixed(1)+'%'}</span></div><div class="small mono">${E(r.calculation_method)} · Risk ${E(r.risk_level)} · Units ${E(r.recommended_units)}</div>${r.warning?`<div class="parlayWarn">${E(r.warning)}</div>`:''}</div>`}).join('');return `<div class="section"><h2 class="mono">Parlay Optimizer v2</h2><div class="small mono">Direct same-player joint probabilities plus clearly labeled conservative cross-player estimates.</div><div class="parlayGrid">${cards||'<div class="empty mono">No qualified parlay combinations available.</div>'}</div></div>`};const previous=window.topPlays;window.topPlays=function(){const base=typeof previous==='function'?previous():'';return base+window.parlayOptimizer()};window.best=window.topPlays;})();</script>'''
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
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-parlay-optimizer-data">DATA.parlay_optimizer={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-parlay-optimizer-data">','</script>',data) if 'id="v4-parlay-optimizer-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-parlay-optimizer-style">','</style>',CSS) if 'id="v4-parlay-optimizer-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-parlay-optimizer-script">','</script>',SCRIPT) if 'id="v4-parlay-optimizer-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Parlay Optimizer v2 added beneath Top Plays')
if __name__=='__main__':main()
