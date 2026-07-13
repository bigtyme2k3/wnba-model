from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_ancillary_projection_v2.json')
CSS=r'''<style id="v4-ancillary-projection-style">.ancGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}.ancCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.ancStats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:10px 0}.ancStat{border:1px solid #1d2b42;border-radius:10px;padding:8px}.ancValue{font-size:22px;font-weight:950}.ancRange{font-size:10px;color:#8fa0bd}.ancMarket{margin-top:8px;padding-top:8px;border-top:1px solid #20304b}</style>'''
SCRIPT=r'''<script id="v4-ancillary-projection-script">(function(){window.ancillaryProjection=function(){const p=DATA.ancillary_projection||{},rows=Array.isArray(p.projections)?p.projections:[];const body=rows.slice(0,24).map(r=>{const d=r.projections||{};const card=s=>`<div class="ancStat"><div class="small mono">${s}</div><div class="ancValue mono">${E(d[s]?.mean??'—')}</div><div class="ancRange mono">${E(d[s]?.p10??'—')}–${E(d[s]?.p90??'—')}</div></div>`;const m=(r.markets||[])[0];return `<div class="ancCard"><div class="small mono">${E(r.team||'—')} · ${E(r.opponent||'—')}</div><b>${E(r.player)}</b><div class="small mono">Minutes ${E(r.projected_minutes)} · Confidence ${E(r.confidence)}</div><div class="ancStats">${card('3PM')}${card('STL')}${card('BLK')}${card('TOV')}</div>${m?`<div class="ancMarket mono"><b>${E(m.action)}</b> ${E(m.stat)} ${E(m.side)} ${E(m.line)} · ${Math.round(Number(m.hit_probability||0)*100)}% · EV ${m.expected_value_per_unit==null?'—':(Number(m.expected_value_per_unit)*100).toFixed(1)+'%'}</div>`:''}<div class="small">${(r.reasons||[]).slice(0,4).map(E).join(' · ')}</div></div>`}).join('');return `<div class="section"><h2 class="mono">3PM / STL / BLK / TOV Projection v2</h2><div class="small mono">Count-based 10,000-run simulations using projected minutes and verified matchup context.</div><div class="ancGrid">${body||'<div class="empty mono">No ancillary projections available.</div>'}</div></div>`};})();</script>'''
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
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-ancillary-projection-data">DATA.ancillary_projection={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-ancillary-projection-data">','</script>',data) if 'id="v4-ancillary-projection-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-ancillary-projection-style">','</style>',CSS) if 'id="v4-ancillary-projection-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-ancillary-projection-script">','</script>',SCRIPT) if 'id="v4-ancillary-projection-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Ancillary Projection v2 dashboard block added')
if __name__=='__main__':main()
