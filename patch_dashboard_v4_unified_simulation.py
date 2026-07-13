from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_unified_player_simulation_v2.json')
CSS=r'''<style id="v4-unified-simulation-style">.uniGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.uniCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.uniLine{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin:10px 0}.uniStat{border:1px solid #1d2b42;border-radius:9px;padding:7px}.uniValue{font-size:20px;font-weight:950}.uniRange{font-size:9px;color:#8fa0bd}.uniMarket{margin-top:8px;padding-top:8px;border-top:1px solid #20304b}.uniPair{margin-top:6px;color:#8fa0bd;font-size:11px}</style>'''
SCRIPT=r'''<script id="v4-unified-simulation-script">(function(){window.unifiedSimulation=function(){const p=DATA.unified_simulation||{},rows=Array.isArray(p.players)?p.players:[];const body=rows.slice(0,24).map(r=>{const d=r.distributions||{};const stat=s=>`<div class="uniStat"><div class="small mono">${s}</div><div class="uniValue mono">${E(d[s]?.mean??'—')}</div><div class="uniRange mono">${E(d[s]?.p10??'—')}–${E(d[s]?.p90??'—')}</div></div>`;const m=r.best_market;const pair=(r.same_player_pairs||[])[0];return `<div class="uniCard"><div class="small mono">${E(r.team||'—')} · ${E(r.opponent||'—')}</div><b>${E(r.player)}</b><div class="small mono">Confidence ${E(r.confidence)} · ${E(r.data_quality_status)} · 10,000 sims</div><div class="uniLine">${stat('MIN')}${stat('PTS')}${stat('REB')}${stat('AST')}${stat('3PM')}${stat('STL')}${stat('BLK')}${stat('TOV')}${stat('PRA')}${stat('RA')}</div>${m?`<div class="uniMarket mono"><b>${E(m.action)}</b> ${E(m.stat)} ${E(m.side)} ${E(m.line)} · ${Math.round(Number(m.hit_probability||0)*100)}% · EV ${m.expected_value_per_unit==null?'—':(Number(m.expected_value_per_unit)*100).toFixed(1)+'%'}</div>`:''}${pair?`<div class="uniPair mono">Pair: ${pair.legs.map(x=>`${E(x.stat)} ${E(x.side)} ${E(x.line)}`).join(' + ')} · Joint ${Math.round(Number(pair.joint_probability||0)*100)}% · ${E(pair.classification)}</div>`:''}</div>`}).join('');return `<div class="section"><h2 class="mono">Unified Player Simulation v2</h2><div class="small mono">One simulated stat line powers every supported prop, combo, correlation, and same-player pair.</div><div class="uniGrid">${body||'<div class="empty mono">No unified simulations available.</div>'}</div></div>`};})();</script>'''
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
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-unified-simulation-data">DATA.unified_simulation={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-unified-simulation-data">','</script>',data) if 'id="v4-unified-simulation-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-unified-simulation-style">','</style>',CSS) if 'id="v4-unified-simulation-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-unified-simulation-script">','</script>',SCRIPT) if 'id="v4-unified-simulation-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Unified Player Simulation v2 dashboard block added')
if __name__=='__main__':main()
