from __future__ import annotations

import json
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_minutes_projection_v2.json')

CSS=r'''<style id="v4-minutes-projection-style">.minutesGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.minutesCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.minutesValue{font-size:26px;font-weight:950}.minutesRange{color:#8fa0bd;font-size:12px}.minutesQuality{display:inline-block;margin-top:8px;border:1px solid #30435f;border-radius:999px;padding:3px 8px;font-size:11px}.minutesReasons{margin-top:8px;color:#8fa0bd;font-size:11px}</style>'''
SCRIPT=r'''<script id="v4-minutes-projection-script">(function(){window.minutesProjection=function(){const p=DATA.minutes_projection||{},rows=Array.isArray(p.projections)?p.projections:[];const body=rows.slice(0,24).map(r=>`<div class="minutesCard"><div class="small mono">${E(r.team||'—')} · ${E(r.opponent||'—')}</div><b>${E(r.player)}</b><div class="minutesValue mono">${E(r.projected_minutes)}</div><div class="minutesRange mono">P10 ${E(r.minutes_p10)} · P50 ${E(r.minutes_p50)} · P90 ${E(r.minutes_p90)}</div><div class="small mono">Confidence ${E(r.confidence)} · ${E(r.injury_status)}</div><span class="minutesQuality mono">${E(r.data_quality_status)}</span><div class="minutesReasons">${(r.reasons||[]).slice(0,3).map(E).join(' · ')}</div></div>`).join('');return `<div class="section"><h2 class="mono">Minutes Projection v2</h2><div class="small mono">Projected playing-time distributions feeding Projection Engine v2.</div><div class="minutesGrid">${body||'<div class="empty mono">No minute projections available.</div>'}</div></div>`};})();</script>'''

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
    data=f'<script id="v4-minutes-projection-data">DATA.minutes_projection={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html=replace_block(html,'<script id="v4-minutes-projection-data">','</script>',data) if 'id="v4-minutes-projection-data"' in html else html.replace('</body>',data+'</body>')
    html=replace_block(html,'<style id="v4-minutes-projection-style">','</style>',CSS) if 'id="v4-minutes-projection-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace_block(html,'<script id="v4-minutes-projection-script">','</script>',SCRIPT) if 'id="v4-minutes-projection-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8')
    print('Minutes Projection v2 dashboard block added')
if __name__=='__main__':main()
