from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html'); DATA=Path('data/dashboard/wnba_live_results_engine.json')
CSS=r'''<style id="v4-live-results-style">.lrCard{border:1px solid #263854;border-radius:16px;padding:14px;background:#08101c;margin:12px 0}.lrTop{display:flex;justify-content:space-between;align-items:center;gap:10px}.lrStatus{border:1px solid currentColor;border-radius:999px;padding:4px 8px;font-size:10px;font-weight:900}.lrWatching{color:#00e39b}.lrQueue{color:#ffd166}.lrGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}.lrKpi{border:1px solid #20304b;border-radius:10px;padding:9px}.lrKpi b{display:block;font-size:20px}.lrGame{padding:7px 0;border-top:1px solid #1d2b42;font-size:11px}@media(max-width:700px){.lrGrid{grid-template-columns:repeat(2,1fr)}}</style>'''
SCRIPT=r'''<script id="v4-live-results-script">(function(){window.liveResultsEngine=function(){const p=DATA.live_results_engine||{},s=p.summary||{},queued=Array.isArray(p.grading_queue)?p.grading_queue:[],active=Array.isArray(p.games)?p.games.filter(g=>g.status==='LIVE'||g.status==='HALFTIME'):[];const status=p.run_grading?'GRADING QUEUED':'WATCHING';return `<div class="lrCard"><div class="lrTop"><div><b>Live Results Engine</b><div class="small mono">Credit-free game-status monitor · updated ${E(p.generated_at_utc||'—')}</div></div><span class="lrStatus ${p.run_grading?'lrQueue':'lrWatching'}">${status}</span></div><div class="lrGrid"><div class="lrKpi"><span>Games</span><b class="mono">${E(s.games||0)}</b></div><div class="lrKpi"><span>Live</span><b class="mono">${E(s.live||0)}</b></div><div class="lrKpi"><span>Queued</span><b class="mono">${E(s.queued||0)}</b></div><div class="lrKpi"><span>Graded</span><b class="mono">${E(s.graded_total||0)}</b></div></div>${active.map(g=>`<div class="lrGame"><b>${E(g.game)}</b> · ${E(g.status)}</div>`).join('')}${queued.map(g=>`<div class="lrGame"><b>${E(g.game)}</b> · waiting to grade</div>`).join('')}</div>`};const prior=window.health;window.health=function(){return window.liveResultsEngine()+(typeof prior==='function'?prior():'')}})();</script>'''

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
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-live-results-data">DATA.live_results_engine={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-live-results-data">','</script>',data) if 'id="v4-live-results-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-live-results-style">','</style>',CSS) if 'id="v4-live-results-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-live-results-script">','</script>',SCRIPT) if 'id="v4-live-results-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Live Results Engine tile added')
if __name__=='__main__':main()
