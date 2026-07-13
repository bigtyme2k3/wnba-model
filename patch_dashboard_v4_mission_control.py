from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_mission_control.json')
CSS=r'''<style id="v4-mission-control-style">.mcBanner{border:1px solid #263854;border-radius:14px;padding:12px 14px;margin:12px 0}.mcReady{border-color:#00e39b;color:#00e39b}.mcDegraded{border-color:#ffd166;color:#ffd166}.mcBlocked{border-color:#ff4d67;color:#ff4d67}.mcGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.mcCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#08101c}.mcTop{display:flex;justify-content:space-between;gap:8px;align-items:center}.mcGreen{color:#00e39b}.mcYellow{color:#ffd166}.mcRed{color:#ff4d67}.mcStatus{font-size:11px;font-weight:900;border:1px solid currentColor;border-radius:999px;padding:4px 8px}.mcIssue{font-size:11px;margin-top:7px}.mcMeta{font-size:10px;color:#8fa0bd;margin-top:7px}.mcAltAlert{border:1px solid #ffd166;background:#171307;border-radius:12px;padding:10px 12px;margin:10px 0;color:#ffd166}.mcAltMode{margin-top:7px;font-size:11px;color:#c9b76e}.mcTable{width:100%;border-collapse:collapse;margin-top:12px}.mcTable th,.mcTable td{padding:8px;border-bottom:1px solid #1d2b42;text-align:left;font-size:12px}@media(max-width:700px){.mcGrid{grid-template-columns:1fr}}</style>'''
SCRIPT=r'''<script id="v4-mission-control-script">(function(){const mc=()=>DATA.mission_control||{};const cls=s=>s==='GREEN'?'mcGreen':s==='YELLOW'?'mcYellow':'mcRed';window.missionControl=function(){const p=mc(),s=p.summary||{},checks=Array.isArray(p.checks)?p.checks:[];const bannerClass=p.publication_status==='READY'?'mcReady':p.publication_status==='DEGRADED'?'mcDegraded':'mcBlocked';const cards=checks.map(c=>`<div class="mcCard"><div class="mcTop"><b>${E(c.component)}</b><span class="mcStatus ${cls(c.status)}">${E(c.status)}</span></div><div class="mcMeta mono">Rows ${E(c.rows)} · ${E(c.action)}</div>${(c.issues||[]).map(x=>`<div class="mcIssue mcRed">${E(x)}</div>`).join('')}${(c.warnings||[]).map(x=>`<div class="mcIssue mcYellow">${E(x)}</div>`).join('')}<div class="mcMeta mono">Updated ${E(c.generated_at_utc||'—')} · Retries ${E(c.retry_count||0)}</div></div>`).join('');return `<div class="section"><h2 class="mono">Mission Control</h2><div class="mcBanner ${bannerClass}"><b>${E(p.publication_status||'UNKNOWN')}</b> · ${E(p.publication_message||'')}</div><div class="row"><div class="kpi"><b>${E(s.green||0)}</b><span>GREEN</span></div><div class="kpi"><b>${E(s.yellow||0)}</b><span>YELLOW</span></div><div class="kpi"><b>${E(s.red||0)}</b><span>RED</span></div><div class="kpi"><b>${E(s.retry_required||0)}</b><span>RETRY</span></div></div><div class="mcGrid">${cards}</div></div>`};const oldHealth=window.health;window.health=function(){const base=typeof oldHealth==='function'?oldHealth():'';return window.missionControl()+base};const oldAlt=window.altStreaks;window.altStreaks=function(){const p=mc(),available=p.alt_props?.available;const base=typeof oldAlt==='function'?oldAlt():'';if(available===false){const standardCount=(DATA.alt_streaks?.summary?.standard_rows||0);const alert=`<div class="section"><div class="mcAltAlert"><b>Sportsbook alternate lines unavailable</b><div class="small">The source returned standard player-prop lines but no true alternate lines. Unsupported ALT recommendations remain withheld.</div><div class="mcAltMode mono">Showing ${E(standardCount)} verified standard-line streak rows below · Action: ${E(p.alt_props?.action||'PUBLISH_DEGRADED')} · Retry ${E(p.alt_props?.retry_count||0)}/2</div></div></div>`;return alert+base}return base};})();</script>'''

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
    html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-mission-control-data">DATA.mission_control={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html=replace_block(html,'<script id="v4-mission-control-data">','</script>',data) if 'id="v4-mission-control-data"' in html else html.replace('</body>',data+'</body>')
    html=replace_block(html,'<style id="v4-mission-control-style">','</style>',CSS) if 'id="v4-mission-control-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace_block(html,'<script id="v4-mission-control-script">','</script>',SCRIPT) if 'id="v4-mission-control-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8');print('Mission Control added to V4 Health')
if __name__=='__main__':main()
