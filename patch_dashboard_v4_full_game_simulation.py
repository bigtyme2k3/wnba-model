from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_full_game_simulation_v2.json')
CSS=r'''<style id="v4-full-game-simulation-style">.fgGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.fgCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.fgScore{font-size:26px;font-weight:950}.fgRange{font-size:11px;color:#8fa0bd}.fgPair{margin-top:8px;padding-top:8px;border-top:1px solid #20304b;font-size:11px}</style>'''
SCRIPT=r'''<script id="v4-full-game-simulation-script">(function(){window.fullGameSimulation=function(){const p=DATA.full_game_simulation||{},rows=Array.isArray(p.games)?p.games:[];const cards=rows.map(g=>{const s=g.score_distribution||{},pair=(g.direct_cross_player_pairs||[])[0];return `<div class="fgCard"><b>${E(g.game)}</b><div class="row"><div><div class="small">Away Mean</div><div class="fgScore mono">${E(s.away_mean)}</div></div><div><div class="small">Home Mean</div><div class="fgScore mono">${E(s.home_mean)}</div></div><div><div class="small">Total</div><div class="fgScore mono">${E(s.total_mean)}</div></div></div><div class="fgRange mono">Total P10 ${E(s.total_p10)} · P90 ${E(s.total_p90)} · Margin ${E(s.margin_mean)} · OT ${(Number(s.overtime_probability||0)*100).toFixed(1)}%</div><div class="small mono">Players ${E((g.players||[]).length)} · 10,000 shared simulations</div>${pair?`<div class="fgPair mono">Direct pair: ${pair.legs.map(x=>`${E(x.player)} ${E(x.stat)} ${E(x.side)} ${E(x.line)}`).join(' + ')} · Joint ${(Number(pair.joint_probability||0)*100).toFixed(1)}% · Corr ${E(pair.correlation)}</div>`:''}</div>`}).join('');return `<div class="section"><h2 class="mono">Full-Game Simulation v2</h2><div class="small mono">Both teams and all available players share pace, efficiency, overtime, and blowout outcomes.</div><div class="fgGrid">${cards||'<div class="empty mono">No full-game simulations available.</div>'}</div></div>`};const previous=window.unifiedSimulation;window.unifiedSimulation=function(){const base=typeof previous==='function'?previous():'';return window.fullGameSimulation()+base};})();</script>'''
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
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-full-game-simulation-data">DATA.full_game_simulation={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-full-game-simulation-data">','</script>',data) if 'id="v4-full-game-simulation-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-full-game-simulation-style">','</style>',CSS) if 'id="v4-full-game-simulation-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-full-game-simulation-script">','</script>',SCRIPT) if 'id="v4-full-game-simulation-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Full-Game Simulation v2 added to Model Center')
if __name__=='__main__':main()
