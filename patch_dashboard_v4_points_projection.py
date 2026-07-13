from __future__ import annotations

import json
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_points_projection_v2.json')
CSS=r'''<style id="v4-points-projection-style">.pointsGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}.pointsCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.pointsValue{font-size:28px;font-weight:950}.pointsRange{font-size:12px;color:#8fa0bd}.pointsShots{margin-top:8px;font-size:11px;color:#8fa0bd}.pointsMarkets{margin-top:10px;border-top:1px solid #20304b;padding-top:8px}.pointsBet{color:#00e39b;font-weight:900}.pointsLean{color:#ffd166;font-weight:900}.pointsPass{color:#ff4d67;font-weight:900}</style>'''
SCRIPT=r'''<script id="v4-points-projection-script">(function(){window.pointsProjection=function(){const p=DATA.points_projection||{},rows=Array.isArray(p.projections)?p.projections:[];const body=rows.slice(0,24).map(r=>{const s=r.shot_distribution||{};const m=(r.markets||[])[0];const cls=m?.action==='BET'?'pointsBet':m?.action==='LEAN'?'pointsLean':'pointsPass';return `<div class="pointsCard"><div class="small mono">${E(r.team||'—')} · ${E(r.opponent||'—')}</div><b>${E(r.player)}</b><div class="pointsValue mono">${E(r.projected_points)}</div><div class="pointsRange mono">P10 ${E(r.points_p10)} · P50 ${E(r.points_p50)} · P90 ${E(r.points_p90)}</div><div class="small mono">Confidence ${E(r.confidence)} · ${E(r.data_quality_status)}</div><div class="pointsShots mono">2PA ${E(s.two_point_attempts)} · 3PA ${E(s.three_point_attempts)} · FTA ${E(s.free_throw_attempts)}</div>${m?`<div class="pointsMarkets mono"><span class="${cls}">${E(m.action)}</span> ${E(m.side)} ${E(m.line)} · ${Math.round(Number(m.hit_probability||0)*100)}% · EV ${m.expected_value_per_unit==null?'—':(Number(m.expected_value_per_unit)*100).toFixed(1)+'%'}</div>`:''}<div class="small">${(r.reasons||[]).slice(0,3).map(E).join(' · ')}</div></div>`}).join('');return `<div class="section"><h2 class="mono">Points Projection v2</h2><div class="small mono">10,000-simulation scoring distributions, shot mix, and sportsbook edge.</div><div class="pointsGrid">${body||'<div class="empty mono">No points projections available.</div>'}</div></div>`};})();</script>'''
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
    html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-points-projection-data">DATA.points_projection={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html=replace_block(html,'<script id="v4-points-projection-data">','</script>',data) if 'id="v4-points-projection-data"' in html else html.replace('</body>',data+'</body>')
    html=replace_block(html,'<style id="v4-points-projection-style">','</style>',CSS) if 'id="v4-points-projection-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace_block(html,'<script id="v4-points-projection-script">','</script>',SCRIPT) if 'id="v4-points-projection-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8');print('Points Projection v2 dashboard block added')
if __name__=='__main__':main()
