from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_live_projection_v1.json')
CSS=r'''<style id="v4-live-projection-style">.liveGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px}.liveCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.liveScore{font-size:28px;font-weight:950}.livePlayer{border-top:1px solid #1d2b42;padding-top:8px;margin-top:8px}.livePulse{display:inline-block;width:8px;height:8px;border-radius:50%;background:#00e39b;margin-right:6px}.liveRange{font-size:10px;color:#8fa0bd}</style>'''
SCRIPT=r'''<script id="v4-live-projection-script">(function(){window.liveProjection=function(){const p=DATA.live_projection||{},games=Array.isArray(p.games)?p.games:[];const cards=games.map(g=>{const players=(g.players||[]).slice(0,10).map(r=>{const d=r.distributions||{};return `<div class="livePlayer"><b>${E(r.player)}</b><div class="small mono">MIN ${E(r.live_minutes)} → ${E(r.projected_final_minutes)}${r.foul_trouble?' · FOUL TROUBLE':''}</div><div class="small mono">PTS ${E(d.PTS?.mean??'—')} · REB ${E(d.REB?.mean??'—')} · AST ${E(d.AST?.mean??'—')} · PRA ${E(d.PRA?.mean??'—')}</div><div class="liveRange mono">PTS ${E(d.PTS?.p10??'—')}–${E(d.PTS?.p90??'—')} · Live weight ${(Number(r.live_weight||0)*100).toFixed(0)}%</div></div>`}).join('');return `<div class="liveCard"><div><span class="livePulse"></span><b>${E(g.game)}</b></div><div class="small mono">Q${E(g.period)} ${E(g.clock)} · ${E(g.away_score)}-${E(g.home_score)}</div><div class="row"><div><div class="small">Final Total</div><div class="liveScore mono">${E(g.projected_final_total)}</div></div><div><div class="small">Final Margin</div><div class="liveScore mono">${E(g.projected_final_margin)}</div></div></div>${players}</div>`}).join('');return `<div class="section"><h2 class="mono">Live In-Game Projections</h2><div class="small mono">Pregame priors updated with score, clock, pace, minutes, usage, and foul state.</div><div class="liveGrid">${cards||'<div class="empty mono">No WNBA games are currently in progress.</div>'}</div></div>`};const priorGames=window.games;window.games=function(){const base=typeof priorGames==='function'?priorGames():'';const live=(DATA.live_projection?.summary?.live_games||0)>0?window.liveProjection():'';return live+base};})();</script>'''
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
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-live-projection-data">DATA.live_projection={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-live-projection-data">','</script>',data) if 'id="v4-live-projection-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-live-projection-style">','</style>',CSS) if 'id="v4-live-projection-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-live-projection-script">','</script>',SCRIPT) if 'id="v4-live-projection-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Live In-Game Projections added to Today')
if __name__=='__main__':main()
