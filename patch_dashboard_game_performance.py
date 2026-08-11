"""Expose Game Performance as a single routed renderer for the locked V4 UI."""
from __future__ import annotations

import json
import re
from pathlib import Path

from wnba_game_performance import build as build_game_performance

HTML = Path("docs/index.html")
DATA = Path("data/dashboard/wnba_game_performance.json")
STYLE_ID = "game-performance-route-style"
SCRIPT_ID = "game-performance-route-script"

STYLE = r'''<style id="game-performance-route-style">
.gp-summary{display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:12px;margin:14px 0 20px}.gp-metric,.gp-card{background:#091625;border:1px solid #1d334b;border-radius:16px;padding:16px}.gp-metric span,.gp-grid span{display:block;color:#8ea1b6;font-size:12px;text-transform:uppercase;letter-spacing:.08em}.gp-metric b{display:block;font-size:25px;margin-top:7px;color:#eef5ff}.gp-archive{background:#07111e;border:1px solid #1d334b;border-radius:16px;padding:12px;margin-top:12px}.gp-archive-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:4px 4px 10px}.gp-archive-head h3{margin:0}.gp-toolbar{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin:0 4px 10px}.gp-filter,.gp-sort{background:#0b1423;border:1px solid #263854;color:#b7c6da;border-radius:999px;padding:7px 11px;font:inherit;cursor:pointer}.gp-filter.a,.gp-sort.a{border-color:#3de6b0;color:#3de6b0;background:#09271f}.gp-search{min-width:210px;flex:1;background:#08111f;border:1px solid #263854;border-radius:10px;color:#eef5ff;padding:8px 10px;font:inherit}.gp-count{margin-left:auto;color:#8190aa;font-size:11px}.gp-scroll{max-height:58vh;overflow-y:auto;overscroll-behavior:contain;padding-right:5px}.gp-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.gp-card{padding:13px}.gp-card h3{margin:4px 0 12px;color:#f1f5f9;font-size:16px}.gp-date{color:#20d89b;font-size:11px}.gp-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.gp-grid div{background:#07111e;border:1px solid #162a40;border-radius:10px;padding:8px}.gp-grid b,.gp-grid small,.gp-grid em{display:block;margin-top:4px}.gp-grid em.win{color:#20d89b}.gp-grid em.loss{color:#ff667d}.gp-grid em.pass{color:#f4bf4f}.gp-grid em.push{color:#77b7ff}@media(max-width:900px){.gp-summary{grid-template-columns:repeat(2,1fr)}.gp-cards{grid-template-columns:1fr}.gp-grid{grid-template-columns:repeat(2,1fr)}.gp-scroll{max-height:62vh}.gp-count{width:100%;margin-left:0}.gp-search{min-width:100%}}
</style>'''


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    build_game_performance()
    payload = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    raw = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    script = r'''<script id="game-performance-route-script">(function(){
const D=__PAYLOAD__;window.WNBA_GAME_PERFORMANCE=D;
let gpFilter='ALL',gpSort='DATE',gpDir='DESC',gpSearch='';
const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const pct=v=>{const n=Number(v);return Number.isFinite(n)?(n*100).toFixed(1)+'%':'—'};
const rec=o=>{o=(o&&o.record)?o.record:(o||{});return `${Number(o.wins||0)}-${Number(o.losses||0)}-${Number(o.pushes||0)}`};
const val=(r,k)=>{if(k==='DATE')return String(r.target_date||'');if(k==='GAME')return String(r.game||'').toLowerCase();if(k==='SPREAD')return String(r.spread_result||'');if(k==='TOTAL')return String(r.total_result||'');if(k==='MARGIN_ERR')return Number(r.margin_error??9999);if(k==='TOTAL_ERR')return Number(r.total_error??9999);return ''};
const cmp=(a,b)=>{const av=val(a,gpSort),bv=val(b,gpSort);const c=(typeof av==='number'&&typeof bv==='number')?av-bv:String(av).localeCompare(String(bv));return gpDir==='ASC'?c:-c};
function filteredRows(){let rows=Array.isArray(D.recent_games)?D.recent_games.slice():[];if(gpFilter==='SPREAD_WIN')rows=rows.filter(r=>String(r.spread_result||'').toUpperCase()==='WIN');else if(gpFilter==='SPREAD_LOSS')rows=rows.filter(r=>String(r.spread_result||'').toUpperCase()==='LOSS');else if(gpFilter==='TOTAL_WIN')rows=rows.filter(r=>String(r.total_result||'').toUpperCase()==='WIN');else if(gpFilter==='TOTAL_LOSS')rows=rows.filter(r=>String(r.total_result||'').toUpperCase()==='LOSS');else if(gpFilter==='PICKED')rows=rows.filter(r=>String(r.spread_result||'').toUpperCase()!=='PASS'||String(r.total_result||'').toUpperCase()!=='PASS');if(gpSearch){const q=gpSearch.toLowerCase();rows=rows.filter(r=>`${r.target_date||''} ${r.game||''} ${r.spread_recommendation||r.spread_pick||''} ${r.total_recommendation||r.total_pick||''}`.toLowerCase().includes(q))}return rows.sort(cmp)}
function archiveHtml(){const all=Array.isArray(D.recent_games)?D.recent_games:[],rows=filteredRows();const f=(key,label)=>`<button class="gp-filter ${gpFilter===key?'a':''}" onclick="window.gpSetFilter('${key}')">${label}</button>`;const s=(key,label)=>`<button class="gp-sort ${gpSort===key?'a':''}" onclick="window.gpSetSort('${key}')">${label}${gpSort===key?(gpDir==='ASC'?' ▲':' ▼'):''}</button>`;const cards=rows.map(r=>`<article class="gp-card"><div class="gp-date mono">${esc(r.target_date||'')}</div><h3 class="mono">${esc(r.game||'Unknown game')}</h3><div class="gp-grid"><div><span>Spread pick</span><b>${esc(r.spread_recommendation||r.spread_pick||'PASS')}</b><em class="${String(r.spread_result||'').toLowerCase()}">${esc(r.spread_result||'PENDING')}</em></div><div><span>Total pick</span><b>${esc(r.total_recommendation||r.total_pick||'PASS')}</b><em class="${String(r.total_result||'').toLowerCase()}">${esc(r.total_result||'PENDING')}</em></div><div><span>Projected</span><b>${esc(r.projected_away_score)}–${esc(r.projected_home_score)}</b><small>Total ${esc(r.projected_total)}</small><small>Margin err ${esc(r.margin_error)}</small></div><div><span>Actual</span><b>${esc(r.actual_away_score)}–${esc(r.actual_home_score)}</b><small>Total ${esc(r.actual_total)}</small><small>Total err ${esc(r.total_error)}</small></div></div></article>`).join('');return `<div class="gp-archive"><div class="gp-archive-head"><h3 class="mono">Graded Game Archive</h3><span class="small mono">${rows.length} of ${all.length} games · scroll inside</span></div><div class="gp-toolbar"><input class="gp-search" value="${esc(gpSearch)}" placeholder="Search team, game or date" oninput="window.gpSetSearch(this.value)">${f('ALL','All')}${f('PICKED','Model Picks')}${f('SPREAD_WIN','Spread Wins')}${f('SPREAD_LOSS','Spread Losses')}${f('TOTAL_WIN','Total Wins')}${f('TOTAL_LOSS','Total Losses')}<span class="gp-count">Sort:</span>${s('DATE','Date')}${s('GAME','Game')}${s('SPREAD','Spread Result')}${s('TOTAL','Total Result')}${s('MARGIN_ERR','Margin Error')}${s('TOTAL_ERR','Total Error')}</div><div class="gp-scroll"><div class="gp-cards">${cards||'<div class="gp-card">No graded games match this filter.</div>'}</div></div></div>`}
window.fullGamePerformance=function(){const s=D.summary||{},sp=D.spread||{},to=D.total||{};return `<div class="section"><h2 class="mono">Game Performance</h2><p class="small mono">Frozen pregame spreads, totals and projected scores graded against final results. Historical grading is evaluation data; model parameters are not auto-changed from this page.</p><div class="gp-summary"><div class="gp-metric"><span>Archived games</span><b>${Number(s.archived_games||0)}</b></div><div class="gp-metric"><span>Graded games</span><b>${Number(s.graded_games||0)}</b></div><div class="gp-metric"><span>Spread record</span><b>${rec(sp)}</b><small>${pct(sp.hit_rate)}</small></div><div class="gp-metric"><span>Total record</span><b>${rec(to)}</b><small>${pct(to.hit_rate)}</small></div><div class="gp-metric"><span>Margin MAE</span><b>${esc(s.avg_margin_error)}</b></div><div class="gp-metric"><span>Total MAE</span><b>${esc(s.avg_total_error)}</b></div></div>${archiveHtml()}</div>`};
function rerenderArchive(){const root=document.getElementById('root');if(!root)return;const box=root.querySelector('.gp-archive');if(box){const tmp=document.createElement('div');tmp.innerHTML=archiveHtml();box.replaceWith(tmp.firstElementChild)}}
window.gpSetFilter=f=>{gpFilter=f;rerenderArchive()};window.gpSetSearch=q=>{gpSearch=q;rerenderArchive();const i=document.querySelector('.gp-search');if(i){i.focus();i.setSelectionRange(i.value.length,i.value.length)}};window.gpSetSort=k=>{if(gpSort===k)gpDir=gpDir==='ASC'?'DESC':'ASC';else{gpSort=k;gpDir=(k==='DATE')?'DESC':'ASC'};rerenderArchive()};
})();</script>'''.replace('__PAYLOAD__', raw)
    html = HTML.read_text(encoding="utf-8")
    html = re.sub(r'<!-- WNBA_GAME_PERFORMANCE_START -->.*?<!-- WNBA_GAME_PERFORMANCE_END -->', '', html, flags=re.S)
    html = re.sub(r'<style id="game-performance-route-style">.*?</style>', '', html, flags=re.S)
    html = re.sub(r'<script id="game-performance-route-script">.*?</script>', '', html, flags=re.S)
    html = html.replace('</head>', STYLE + '\n</head>', 1)
    html = html.replace('</body>', script + '\n</body>', 1)
    HTML.write_text(html, encoding="utf-8")
    print({'status':'PASS','renderer':'fullGamePerformance','standalone_nav':False,'archive_scroll':True,'archive_filters':True,'archive_sorting':True})


if __name__ == "__main__":
    main()
