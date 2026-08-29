from __future__ import annotations

import json
import os
import re
import subprocess
import sys
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
.altPerfSection{margin-top:14px;padding-top:14px;border-top:1px solid #17263c}.altPerfSection h3{margin:0 0 4px;font-size:15px}.altPerfSectionNote{font-size:10px;color:#738198;margin-bottom:10px}.altPerfAlert{border:1px solid #6b5724;background:#171307;color:#ffd166;border-radius:10px;padding:11px;margin-bottom:12px;font-size:12px}.altPerfBreakouts{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}.altPerfBox{border:1px solid #17263c;border-radius:10px;overflow:auto}.altPerfBox h4{margin:0;padding:10px 11px;border-bottom:1px solid #17263c;font-size:12px}.altPerfMini{width:100%;border-collapse:collapse;min-width:360px}.altPerfMini th,.altPerfMini td{padding:8px 9px;border-bottom:1px solid #111d2e;text-align:left;font-size:10px}.altPerfMini th{color:#69768d;text-transform:uppercase;letter-spacing:.07em}.altPerfMini tr:last-child td{border-bottom:0}
.altPerfDaily{margin-top:12px}.altPerfDailyTable{width:100%;border-collapse:collapse;min-width:820px}.altPerfDailyTable th,.altPerfDailyTable td{padding:9px;border-bottom:1px solid #111d2e;text-align:left;font-size:10px;white-space:nowrap}.altPerfDailyTable th{color:#69768d;text-transform:uppercase;letter-spacing:.07em}.altPerfWin{color:#52e0aa;font-weight:800}.altPerfLoss{color:#ff7188;font-weight:800}.altPerfPush{color:#ffd166;font-weight:800}.altPerfFilter{width:100%;min-width:105px;padding:7px 8px;border:1px solid #263750;border-radius:7px;background:#07101d;color:#dbe6f6;font:inherit;text-transform:none;letter-spacing:0}.altPerfFilter:focus{outline:1px solid #52e0aa}.altPerfFilterRow th{padding-top:6px;padding-bottom:8px}.altPerfFilterCount{margin:8px 2px 0;color:#738198;font-size:10px}
@media(max-width:800px){.altPerfPanel{margin-left:-10px;margin-right:-10px;border-radius:0}.altPerfGrid2{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>'''


def replace_element(html: str, tag: str, element_id: str, replacement: str) -> str:
    pattern = rf'<{tag} id="{re.escape(element_id)}">.*?</{tag}>'
    html, count = re.subn(pattern, lambda _m: replacement, html, count=1, flags=re.S)
    if count:
        return html
    anchor = '</head>' if tag == 'style' else '</body>'
    return html.replace(anchor, replacement + '\n' + anchor, 1)


def load_payload() -> tuple[dict, str]:
    candidates = []
    try:
        payload = json.loads(DATA.read_text(encoding='utf-8')) if DATA.exists() else {}
        if isinstance(payload, dict):
            candidates.append((str(payload.get('generated_at_utc') or ''), payload, 'working-tree'))
    except Exception:
        pass
    try:
        subprocess.run(['git','fetch','--quiet','origin','main'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw = subprocess.run(['git','show','origin/main:data/dashboard/wnba_alt_performance.json'], check=True, capture_output=True, text=True).stdout
        payload = json.loads(raw)
        if isinstance(payload, dict):
            candidates.append((str(payload.get('generated_at_utc') or ''), payload, 'origin/main'))
    except Exception:
        pass
    if not candidates:
        return {}, 'missing'
    _stamp, payload, source = max(candidates, key=lambda item: item[0])
    return payload, source


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    payload, payload_source = load_payload()
    data_script = f'<script id="{DATA_ID}">window.WNBA_ALT_PERFORMANCE_DATA={json.dumps(payload, separators=(",", ":"), ensure_ascii=False)};</script>'
    script = r'''<script id="alt-props-performance-panel-script">(function(){
const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');
const arr=v=>Array.isArray(v)?v:[];
const D=()=>window.WNBA_ALT_PERFORMANCE_DATA||{};
const pct=v=>v===null||v===undefined?'—':(Number(v)*100).toFixed(1)+'%';
const cls=v=>Number(v||0)>0?'altPerfGood':Number(v||0)<0?'altPerfBad':'altPerfNeutral';
function mini(title,rows){const body=arr(rows).slice(0,8).map(r=>`<tr><td><b>${esc(r.group??'—')}</b></td><td>${esc(r.wins??0)}-${esc(r.losses??0)}-${esc(r.pushes??0)}</td><td>${pct(r.hit_rate)}</td><td class="${cls(r.profit_loss_units)}">${Number(r.profit_loss_units||0).toFixed(2)}u</td><td class="${cls(r.roi)}">${pct(r.roi)}</td></tr>`).join('');return `<div class="altPerfBox"><h4 class="mono">${esc(title)}</h4><table class="altPerfMini"><thead><tr><th>Group</th><th>Record</th><th>Hit</th><th>P/L</th><th>ROI</th></tr></thead><tbody>${body||'<tr><td colspan="5">No graded results yet.</td></tr>'}</tbody></table></div>`}
function researchMini(title,rows){const body=arr(rows).map(r=>`<tr><td><b>${esc(r.group??'—')}</b></td><td>${esc(r.decisions??r.candidates??0)}</td><td>${pct(r.hit_rate)}</td></tr>`).join('');return `<div class="altPerfBox"><h4 class="mono">${esc(title)}</h4><table class="altPerfMini"><thead><tr><th>Tier</th><th>Graded sample</th><th>Hit rate</th></tr></thead><tbody>${body||'<tr><td colspan="3">No graded research rows yet.</td></tr>'}</tbody></table></div>`}
function daily(y){const body=arr(y.rows).map(r=>{const out=String(r.outcome||'').toUpperCase(),oc=out==='WIN'?'altPerfWin':out==='LOSS'?'altPerfLoss':'altPerfPush';return `<tr><td><b>${esc(r.player||'—')}</b><br><span class="altPerfPanelNote">${esc(r.game||'')}</span></td><td>${esc(r.stat||'—')} ${esc(r.side||'—')} ${esc(r.alt_line??'—')}</td><td>${Number(r.streak_score||0).toFixed(1)}</td><td>${esc(r.actual??'—')}</td><td>${esc(r.best_odds??'—')}</td><td>${esc(r.best_book||'—')}</td><td class="${oc}">${esc(out||'—')}</td><td class="${cls(r.profit_loss)}">${Number(r.profit_loss||0).toFixed(2)}u</td></tr>`}).join('');return `<div class="altPerfSection"><h3 class="mono">YESTERDAY'S ALT RESULTS · ${esc(y.date||'—')}</h3><div class="altPerfSectionNote mono">Frozen BET recommendations only. Model score is the score recorded before the game.</div><div class="altPerfGrid2"><div class="altPerfMetric"><div class="altPerfMetricLabel">BET sample</div><div class="altPerfMetricValue">${esc(y.n??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Record</div><div class="altPerfMetricValue">${esc(y.wins??0)}-${esc(y.losses??0)}-${esc(y.pushes??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Win rate</div><div class="altPerfMetricValue">${pct(y.hit_rate)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Units</div><div class="altPerfMetricValue ${cls(y.profit_loss_units)}">${Number(y.profit_loss_units||0).toFixed(2)}u</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">ROI</div><div class="altPerfMetricValue ${cls(y.roi)}">${pct(y.roi)}</div></div></div><div class="altPerfBox altPerfDaily"><table class="altPerfDailyTable"><thead><tr><th>Player / Game</th><th>Pick</th><th>Model score</th><th>Actual</th><th>Odds</th><th>Sportsbook</th><th>Result</th><th>Units</th></tr></thead><tbody>${body||'<tr><td colspan="8">No verified ALT BET results for yesterday yet.</td></tr>'}</tbody></table></div></div>`}
function installDailyFilters(){const table=document.querySelector('.altPerfDailyTable');if(!table||table.dataset.filters==='1')return;table.dataset.filters='1';const rows=Array.from(table.tBodies[0]?.rows||[]).filter(r=>r.cells.length===8);rows.forEach(r=>{r.dataset.playerGame=(r.cells[0].textContent||'').toLowerCase();r.dataset.score=String(parseFloat(r.cells[2].textContent)||0);r.dataset.result=(r.cells[6].textContent||'').trim().toUpperCase()});const filter=document.createElement('tr');filter.className='altPerfFilterRow';filter.innerHTML='<th><input class="altPerfFilter" data-alt-filter="player" placeholder="Filter player/game"></th><th></th><th><select class="altPerfFilter" data-alt-filter="score"><option value="ALL">All scores</option><option value="80">80+</option><option value="70">70–79.9</option><option value="60">60–69.9</option><option value="0">Below 60</option></select></th><th></th><th></th><th></th><th><select class="altPerfFilter" data-alt-filter="result"><option value="ALL">All results</option><option value="WIN">WIN</option><option value="LOSS">LOSS</option><option value="PUSH">PUSH</option></select></th><th></th>';table.tHead.appendChild(filter);const count=document.createElement('div');count.className='altPerfFilterCount mono';table.parentElement.insertAdjacentElement('afterend',count);const apply=()=>{const q=(filter.querySelector('[data-alt-filter="player"]').value||'').trim().toLowerCase(),band=filter.querySelector('[data-alt-filter="score"]').value,result=filter.querySelector('[data-alt-filter="result"]').value;let shown=0;rows.forEach(r=>{const score=Number(r.dataset.score),scoreOk=band==='ALL'||band==='80'&&score>=80||band==='70'&&score>=70&&score<80||band==='60'&&score>=60&&score<70||band==='0'&&score<60,resultOk=result==='ALL'||r.dataset.result===result,textOk=!q||r.dataset.playerGame.includes(q);r.hidden=!(scoreOk&&resultOk&&textOk);if(!r.hidden)shown++});count.textContent=`Showing ${shown} of ${rows.length} graded BET recommendations`};filter.addEventListener('input',apply);filter.addEventListener('change',apply);apply()}
function panel(){const raw=D(),p=raw.alt_performance||raw||{},s=p.summary||{},l=p.live_performance||{},r=p.research_archive||{},c=p.calibration_training_set||{};const liveRate=l.sample_sufficient?pct(l.hit_rate):'—',liveRoi=l.sample_sufficient?pct(l.roi):'—';return `<section id="alt-props-performance-panel" class="altPerfPanel"><div class="altPerfPanelHead"><div><div class="altPerfPanelTitle mono">ALT Props Performance</div><div class="altPerfPanelNote mono">Live recommendations, research diagnostics, and calibration evidence are reported separately.</div></div></div><div class="altPerfSection"><h3 class="mono">1 · LIVE PERFORMANCE</h3><div class="altPerfSectionNote mono">Only frozen pregame rows whose archived action was BET. These are the model's recommendation results.</div>${l.sample_sufficient?'':`<div class="altPerfAlert mono">${esc(l.message||'Insufficient sample — BET recommendations just started')}</div>`}<div class="altPerfGrid2"><div class="altPerfMetric"><div class="altPerfMetricLabel">BET sample</div><div class="altPerfMetricValue">${esc(l.n??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Record</div><div class="altPerfMetricValue">${esc(l.wins??0)}-${esc(l.losses??0)}-${esc(l.pushes??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Win rate</div><div class="altPerfMetricValue">${liveRate}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Units</div><div class="altPerfMetricValue ${cls(l.profit_loss_units)}">${Number(l.profit_loss_units||0).toFixed(2)}u</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">ROI</div><div class="altPerfMetricValue ${cls(l.roi)}">${liveRoi}</div></div></div></div><div class="altPerfSection"><h3 class="mono">2 · RESEARCH ARCHIVE</h3><div class="altPerfSectionNote mono">Diagnostic only: did LEAN out-hit WATCH, and WATCH out-hit PASS? These were not recommended wagers, so no record, units, or ROI is displayed here.</div>${researchMini('Tier ordering · '+(r.tier_order_verified?'VERIFIED':'NOT VERIFIED'),r.tiers)}</div><div class="altPerfSection"><h3 class="mono">3 · CALIBRATION TRAINING SET</h3><div class="altPerfSectionNote mono">A segment qualifies independently by score, stat, side, and price bucket. League-wide row count alone cannot trigger readiness.</div><div class="altPerfGrid2"><div class="altPerfMetric"><div class="altPerfMetricLabel">Training rows</div><div class="altPerfMetricValue">${esc(c.graded_training_rows??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Qualified segments</div><div class="altPerfMetricValue">${esc(c.qualified_segment_count??0)}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Segment status</div><div class="altPerfMetricValue">${esc(c.status||'Collecting')}</div></div><div class="altPerfMetric"><div class="altPerfMetricLabel">Forward BET validation</div><div class="altPerfMetricValue">${c.live_bet_validation_ready?'Ready':'Collecting'} · n=${esc(c.live_bet_validation_n??0)}</div></div></div></div><div class="altPerfSection"><h3 class="mono">Archive Diagnostics</h3><div class="altPerfSectionNote mono">All exact ALT candidates: ${esc(s.archived_candidates??0)} archived · ${esc(s.graded??0)} graded · ${esc(s.pending??0)} pending.</div><div class="altPerfBreakouts">${mini('By Score Band',p.by_score_band)}${mini('By Stat',p.by_stat)}${mini('By Side',p.by_side)}${mini('By Sportsbook',p.by_sportsbook)}</div></div></section>`}
function append(){const root=document.getElementById('root');if(!root)return;if(document.getElementById('alt-props-performance-panel'))return;const host=root.querySelector('.altDesk')||root;host.insertAdjacentHTML('beforeend',panel());const p=D().alt_performance||D()||{},perf=document.getElementById('alt-props-performance-panel');if(perf){perf.insertAdjacentHTML('afterend',`<section class="altPerfPanel">${daily(p.yesterday_performance||{})}</section>`);installDailyFilters()}}
const prevRender=window.render;window.render=function(view){if(typeof prevRender==='function')prevRender(view);if(view==='alt-props')setTimeout(append,10)};
const prevFilter=window.altPropsSetFilter;window.altPropsSetFilter=function(kind,value){if(typeof prevFilter==='function')prevFilter(kind,value);setTimeout(append,10)};
window.WNBA_ALT_PROPS_PERFORMANCE_PANEL={version:'2.1',location:'below-alt-props-table',separated_live_research_calibration:true,shows_pending:true,presentation_only_default:true};
})();</script>'''

    html = HTML.read_text(encoding='utf-8')
    html = replace_element(html, 'style', STYLE_ID, STYLE)
    html = replace_element(html, 'script', DATA_ID, data_script)
    html = replace_element(html, 'script', SCRIPT_ID, script)
    HTML.write_text(html, encoding='utf-8')

    summary = payload.get('summary') or {}
    print({'status':'PASS','alt_props_performance':'below-table','data':bool(payload),'payload_source':payload_source,'archived':summary.get('archived_candidates'),'graded':summary.get('graded'),'pending':summary.get('pending'),'shows_pending':True,'presentation_only':True})

    # This file is a renderer. It must not mutate or re-run the canonical M03
    # decision chain during a Pages build. A legacy explicit opt-in remains for
    # controlled/manual recovery only.
    if os.getenv('ALT_PANEL_RUN_M03') != '1':
        return

    target = subprocess.run([sys.executable,'active_slate_date.py'], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1].strip()
    subprocess.run([sys.executable,'scripts/wnba_s19_m03_dashboard_consumer.py','--date',target], check=True)
    subprocess.run([sys.executable,'patch_dashboard_s19_m03.py'], check=True)
    print({'status':'PASS','sprint':19,'module':'M03','canonical_consumer_installed':True,'target_date':target,'explicit_opt_in':True})


if __name__ == '__main__':
    main()
