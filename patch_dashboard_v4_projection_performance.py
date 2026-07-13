from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_projection_performance.json')
CSS=r'''<style id="v4-projection-performance-style">.ppGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.ppCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.ppValue{font-size:26px;font-weight:950}.ppTable{width:100%;border-collapse:collapse;margin-top:12px}.ppTable th,.ppTable td{padding:8px;border-bottom:1px solid #1d2b42;text-align:left;font-size:12px}.ppLocked{color:#8fa0bd}.ppReview{color:#ffd166}.ppEligible{color:#00e39b}</style>'''
SCRIPT=r'''<script id="v4-projection-performance-script">(function(){window.projectionPerformance=function(){const p=DATA.projection_performance||{},s=p.summary||{},rows=Array.isArray(p.by_stat)?p.by_stat:[],recs=Array.isArray(p.recommendations)?p.recommendations:[];const recMap=Object.fromEntries(recs.map(r=>[r.stat,r]));const table=rows.map(r=>{const rec=recMap[r.group]||{};const cls=rec.status==='CALIBRATION_ELIGIBLE'?'ppEligible':rec.status==='WEIGHT_REVIEW'?'ppReview':'ppLocked';return `<tr><td>${E(r.group)}</td><td>${E(r.graded)}</td><td>${r.mae==null?'—':E(r.mae)}</td><td>${r.bias==null?'—':E(r.bias)}</td><td>${r.p10_p90_coverage==null?'—':(Number(r.p10_p90_coverage)*100).toFixed(1)+'%'}</td><td>${r.hit_rate==null?'—':(Number(r.hit_rate)*100).toFixed(1)+'%'}</td><td class="${cls}">${E(rec.status||'LOCKED')}</td></tr>`}).join('');return `<div class="section"><h2 class="mono">Projection Performance</h2><div class="small mono">Frozen pregame projections graded from the verified Player Game Log Warehouse.</div><div class="ppGrid"><div class="ppCard"><div class="small">Graded</div><div class="ppValue mono">${E(s.graded||0)}</div></div><div class="ppCard"><div class="small">MAE</div><div class="ppValue mono">${s.mae==null?'—':E(s.mae)}</div></div><div class="ppCard"><div class="small">Bias</div><div class="ppValue mono">${s.bias==null?'—':E(s.bias)}</div></div><div class="ppCard"><div class="small">P10–P90 Coverage</div><div class="ppValue mono">${s.p10_p90_coverage==null?'—':(Number(s.p10_p90_coverage)*100).toFixed(1)+'%'}</div></div><div class="ppCard"><div class="small">Hit Rate</div><div class="ppValue mono">${s.hit_rate==null?'—':(Number(s.hit_rate)*100).toFixed(1)+'%'}</div></div><div class="ppCard"><div class="small">ROI</div><div class="ppValue mono">${s.roi==null?'—':(Number(s.roi)*100).toFixed(1)+'%'}</div></div></div><table class="ppTable"><thead><tr><th>Stat</th><th>N</th><th>MAE</th><th>Bias</th><th>Coverage</th><th>Hit</th><th>Calibration</th></tr></thead><tbody>${table||'<tr><td colspan="7">No graded projections yet.</td></tr>'}</tbody></table><div class="small mono">Bias diagnosis unlocks at 50; stat-weight review at 100; simulation-variance review at 200. No automatic weight changes occur before eligibility.</div></div>`};const previous=window.altPerformance;window.altPerformance=function(){const base=typeof previous==='function'?previous():'';return base+window.projectionPerformance()};})();</script>'''
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
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-projection-performance-data">DATA.projection_performance={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-projection-performance-data">','</script>',data) if 'id="v4-projection-performance-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-projection-performance-style">','</style>',CSS) if 'id="v4-projection-performance-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-projection-performance-script">','</script>',SCRIPT) if 'id="v4-projection-performance-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Projection Performance added to Performance Center')
if __name__=='__main__':main()
