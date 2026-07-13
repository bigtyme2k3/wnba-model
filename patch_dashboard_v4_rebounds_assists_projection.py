from __future__ import annotations

import json
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_rebounds_assists_projection_v2.json')
CSS=r'''<style id="v4-ra-projection-style">.raGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.raCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.raStats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}.raStat{border:1px solid #1d2b42;border-radius:10px;padding:8px}.raValue{font-size:22px;font-weight:950}.raRange{font-size:10px;color:#8fa0bd}.raMarket{margin-top:8px;padding-top:8px;border-top:1px solid #20304b}.raBet{color:#00e39b;font-weight:900}.raLean{color:#ffd166;font-weight:900}.raPass{color:#ff4d67;font-weight:900}</style>'''
SCRIPT=r'''<script id="v4-ra-projection-script">(function(){window.reboundsAssistsProjection=function(){const p=DATA.ra_projection||{},rows=Array.isArray(p.projections)?p.projections:[];const body=rows.slice(0,24).map(r=>{const d=r.projections||{};const card=stat=>`<div class="raStat"><div class="small mono">${stat}</div><div class="raValue mono">${E(d[stat]?.mean??'—')}</div><div class="raRange mono">${E(d[stat]?.p10??'—')}–${E(d[stat]?.p90??'—')}</div></div>`;const m=(r.markets||[])[0];const cls=m?.action==='BET'?'raBet':m?.action==='LEAN'?'raLean':'raPass';return `<div class="raCard"><div class="small mono">${E(r.team||'—')} · ${E(r.opponent||'—')}</div><b>${E(r.player)}</b><div class="small mono">Minutes ${E(r.projected_minutes)} · Confidence ${E(r.confidence)}</div><div class="raStats">${card('REB')}${card('AST')}${card('PRA')}${card('PR')}${card('PA')}${card('RA')}</div>${m?`<div class="raMarket mono"><span class="${cls}">${E(m.action)}</span> ${E(m.stat)} ${E(m.side)} ${E(m.line)} · ${Math.round(Number(m.hit_probability||0)*100)}% · EV ${m.expected_value_per_unit==null?'—':(Number(m.expected_value_per_unit)*100).toFixed(1)+'%'}</div>`:''}<div class="small">${(r.reasons||[]).slice(0,4).map(E).join(' · ')}</div></div>`}).join('');return `<div class="section"><h2 class="mono">REB / AST / Combo Projection v2</h2><div class="small mono">Shared 10,000-run simulations preserve correlation across PTS, REB, AST, PRA, PR, PA, and RA.</div><div class="raGrid">${body||'<div class="empty mono">No joint projections available.</div>'}</div></div>`};})();</script>'''
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
    html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-ra-projection-data">DATA.ra_projection={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html=replace_block(html,'<script id="v4-ra-projection-data">','</script>',data) if 'id="v4-ra-projection-data"' in html else html.replace('</body>',data+'</body>')
    html=replace_block(html,'<style id="v4-ra-projection-style">','</style>',CSS) if 'id="v4-ra-projection-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace_block(html,'<script id="v4-ra-projection-script">','</script>',SCRIPT) if 'id="v4-ra-projection-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8');print('Joint REB/AST projection dashboard block added')
if __name__=='__main__':main()
