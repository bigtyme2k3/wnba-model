from __future__ import annotations

import json
import re
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_alt_performance.json')
STYLE_ID = 'alt-props-performance-panel-style'
SCRIPT_ID = 'alt-props-performance-panel-script'
DATA_ID = 'alt-props-performance-panel-data'

STYLE = r'''<style id="alt-props-performance-panel-style">
.altPerfPanel{margin-top:18px;border:1px solid #17263c;border-radius:12px;background:#050a12;padding:16px}
.altPerfPanelHead{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;margin-bottom:12px}
.altPerfPanelTitle{font-size:20px;font-weight:900;letter-spacing:.03em}.altPerfPanelNote{font-size:10px;color:#738198}
.altPerfGrid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:9px;margin-bottom:14px}
.altPerfMetric{border:1px solid #1b2a40;border-radius:10px;background:#08111f;padding:10px}.altPerfMetricLabel{font-size:9px;color:#6f7d96;text-transform:uppercase;letter-spacing:.1em}.altPerfMetricValue{font-size:20px;font-weight:900;margin-top:4px}
.altPerfGood{color:#52e0aa}.altPerfBad{color:#ff7188}.altPerfNeutral{color:#ffd166}
.altPerfBreakouts{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}.altPerfBox{border:1px solid #17263c;border-radius:10px;overflow:auto}.altPerfBox h4{margin:0;padding:10px 11px;border-bottom:1px solid #17263c;font-size:12px}.altPerfMini{width:100%;border-collapse:collapse;min-width:360px}.altPerfMini th,.altPerfMini td{padding:8px 9px;border-bottom:1px solid #111d2e;text-align:left;font-size:10px}.altPerfMini th{color:#69768d;text-transform:uppercase;letter-spacing:.07em}.altPerfMini tr:last-child td{border-bottom:0}
@media(max-width:800px){.altPerfPanel{margin-left:-10px;margin-right:-10px;border-radius:0}.altPerfGrid2{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>'''


def replace_element(html: str, tag: str, element_id: str, replacement: str) -> str:
    pattern = rf'<{tag} id="{re.escape(element_id)}">.*?</{tag}>'
    html, count = re.subn(pattern, lambda _m: replacement, html, count=1, flags=re.S)
    if count:
        return html
    anchor = '</head>' if tag == 'style' else '</body>'
    return html.replace(anchor, replacement + '\n' + anchor, 1)


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    try:
        payload = json.loads(DATA.read_text(encoding='utf-8')) if DATA.exists() else {}
    except Exception:
        payload = {}

    data_script = f'<script id="{DATA_ID}">window.WNBA_ALT_PERFORMANCE_DATA={json.dumps(payload, separators=(",", ":"), ensure_ascii=False)};</script>'
    script = r'''<script id="alt-props-performance-panel-script">(function(){
const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');
const arr=v=>Array.isArray(v)?v:[];
const D=()=>window.WNBA_ALT_PERFORMANCE_DATA||{};
const pct=v=>v===null||v===undefined?'—':(Number(v)*100).toFixed(1)+'%';
const cls=v=>Number(v||0)>0?'altPerfGood':Number(v||0)<0?'altPerfBad':'altPerfNeutral';
function mini(title,rows){const body=arr(rows).slice(0,8).map(r=>`<tr><td><b>${esc(r.group??'—')}</b></td><td>${esc(r.wins??0)}-${esc(r.losses??0)}-${esc(r.pushes??0)}</td><td>${pct(r.hit_rate)}</td><td class="${cls(r.profit_loss_units)}">${Number(r.profit_loss_units||0).toFixed(2)}u</td><td class="${cls(r.roi)}">${pct(r.roi)}</td></tr>`).join('');return `<div class="altPerfBox"><h4 class="mono">${esc(title)}</h4><table class="altPerfMini"><thead><tr><th>Group</th><th>Record</th><th>Hit</th><th>P/L</th><th>ROI</th></tr></thead><tbody>${body||'<tr><td colspan="5">No graded results yet.</td></tr>'}</tbody></table></div>`}
function panel(){const raw=D(),p=raw.alt_performance||raw||{},s=p.summary||{};return `<section id="alt-props-performance-panel" class="altPerfPanel"><div class="altPerfPanelHead"><div><div class="altPerfPanelTitle mono">ALT Props Performance</div><div class="altPerfPanelNote mono">Frozen pregame ALT selections graded against verified results. Pending includes current-slate picks awaiting final results plus any historical rows still missing verified actuals.</div></div></div><div class="altPerfGrid2"><div class="altPerfMetric"><div class="altPerfMetricLabel">Archived</div><div class="altPerfMetricValue">${esc(s.archived_candidates??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Graded</div><div class="altPerfMetricValue">${esc(s.graded??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Pending</div><div class="altPerfMetricValue altPerfNeutral">${esc(s.pending??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Record</div><div class="altPerfMetricValue">${esc(s.wins??0)}-${esc(s.losses??0)}-${esc(s.pushes??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Hit Rate</div><div class="altPerfMetricValue">${pct(s.hit_rate)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">P/L</div><div class="altPerfMetricValue ${cls(s.profit_loss_units)}">${Number(s.profit_loss_units||0).toFixed(2)}u</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">ROI</div><div class="altPerfMetricValue ${cls(s.roi)}">${pct(s.roi)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Threshold</div><div class="altPerfMetricValue">${esc(s.recommended_minimum_score_band??'—')}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Calibration</div><div class="altPerfMetricValue">${s.calibration_ready?'Ready':'Collecting'}</div></div></div><div class="altPerfBreakouts">${mini('By Score Band',p.by_score_band)}${mini('By Stat',p.by_stat)}${mini('By Side',p.by_side)}${mini('By Sportsbook',p.by_sportsbook)}</div></section>`}
function append(){const root=document.getElementById('root');if(!root)return;if(document.getElementById('alt-props-performance-panel'))return;const host=root.querySelector('.altDesk')||root;host.insertAdjacentHTML('beforeend',panel())}
const prevRender=window.render;window.render=function(view){if(typeof prevRender==='function')prevRender(view);if(view==='alt-props')setTimeout(append,10)};
const prevFilter=window.altPropsSetFilter;window.altPropsSetFilter=function(kind,value){if(typeof prevFilter==='function')prevFilter(kind,value);setTimeout(append,10)};
window.WNBA_ALT_PROPS_PERFORMANCE_PANEL={version:'1.1',location:'below-alt-props-table',shows_pending:true};
})();</script>'''

    html = HTML.read_text(encoding='utf-8')
    html = replace_element(html, 'style', STYLE_ID, STYLE)
    html = replace_element(html, 'script', DATA_ID, data_script)
    html = replace_element(html, 'script', SCRIPT_ID, script)
    HTML.write_text(html, encoding='utf-8')
    print({'status':'PASS','alt_props_performance':'below-table','data':DATA.exists(),'shows_pending':True})


if __name__ == '__main__':
    main()
