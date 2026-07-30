from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_alt_performance.json')
CSS=r'''<style id="v4-alt-performance-style">.altPerfGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:14px 0}.altPerfCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.altPerfValue{font-size:25px;font-weight:950}.altPerfTableWrap{overflow:auto;border:1px solid #1e2a43;border-radius:16px;margin-top:14px}.altPerfTable{min-width:760px}.altPerfGood{color:#00e39b}.altPerfBad{color:#ff4d67}.altPerfNeutral{color:#ffd166}.altPerfNote{font-size:11px;color:#8090aa;margin-top:10px}.routerError{border:1px solid #ff4d67;background:#1b0b12;color:#ff9baa;border-radius:14px;padding:16px}.routerMeta{font-size:11px;color:#8090aa;margin-top:8px}</style>'''
SCRIPT=r'''<script id="v4-alt-performance-script">(function(){
const esc=v=>typeof E==='function'?E(v):String(v??'');
const arr=v=>Array.isArray(v)?v:[];
const val=(v,d='—')=>v===undefined||v===null||v===''?d:v;
function pct(v){return v===null||v===undefined?'—':(Number(v)*100).toFixed(1)+'%'}
function cls(v){v=Number(v||0);return v>0?'altPerfGood':v<0?'altPerfBad':'altPerfNeutral'}
function table(title,rows){const body=arr(rows).map(r=>`<tr><td><b>${esc(r.group)}</b></td><td>${esc(r.decisions)}</td><td>${esc(r.wins)}-${esc(r.losses)}-${esc(r.pushes)}</td><td>${pct(r.hit_rate)}</td><td class="${cls(r.profit_loss_units)}">${Number(r.profit_loss_units||0).toFixed(2)}u</td><td class="${cls(r.roi)}">${pct(r.roi)}</td></tr>`).join('');return `<div class="section"><h3 class="mono">${esc(title)}</h3><div class="altPerfTableWrap"><table class="altPerfTable"><thead><tr><th>Group</th><th>Decisions</th><th>Record</th><th>Hit Rate</th><th>P/L</th><th>ROI</th></tr></thead><tbody>${body||'<tr><td colspan="6">No graded results yet.</td></tr>'}</tbody></table></div></div>`}
window.altPerformance=function(){const p=DATA.alt_performance||{},s=p.summary||{};return `<div class="section"><div class="row"><div><h2 class="mono">ALT Performance</h2><div class="small mono">Frozen pregame snapshots graded against verified player game logs.</div></div></div><div class="altPerfGrid"><div class="altPerfCard"><div class="small">Archived</div><div class="altPerfValue">${esc(val(s.archived_candidates,0))}</div></div><div class="altPerfCard"><div class="small">Graded</div><div class="altPerfValue">${esc(val(s.graded,0))}</div></div><div class="altPerfCard"><div class="small">Record</div><div class="altPerfValue">${esc(val(s.wins,0))}-${esc(val(s.losses,0))}-${esc(val(s.pushes,0))}</div></div><div class="altPerfCard"><div class="small">Hit Rate</div><div class="altPerfValue">${pct(s.hit_rate)}</div></div><div class="altPerfCard"><div class="small">P/L</div><div class="altPerfValue ${cls(s.profit_loss_units)}">${Number(s.profit_loss_units||0).toFixed(2)}u</div></div><div class="altPerfCard"><div class="small">ROI</div><div class="altPerfValue ${cls(s.roi)}">${pct(s.roi)}</div></div><div class="altPerfCard"><div class="small">Recommended Threshold</div><div class="altPerfValue">${esc(val(s.recommended_minimum_score_band))}</div></div><div class="altPerfCard"><div class="small">Calibration</div><div class="altPerfValue">${s.calibration_ready?'Ready':'Collecting'}</div></div></div><div class="altPerfNote mono">Closing line and CLV remain blank until verified closing-market snapshots are available.</div></div>${table('By Grade',p.by_grade)}${table('By Score Band',p.by_score_band)}${table('By Action',p.by_action)}${table('By Stat',p.by_stat)}${table('By Side',p.by_side)}${table('By Sportsbook',p.by_sportsbook)}${table('By Matchup Rank Source',p.by_matchup_rank_source)}`};

const NAV=[
 ['games','Games',['gamesV25','games']],
 ['gameprops','Game Props',['marketsV25','gameProps']],
 ['props','Player Props',['props']],
 ['altstreaks','ALT Streaks',['altStreaks']],
 ['altperf','ALT Performance',['altPerformance']],
 ['dailyedges','Daily Edges',['dailyEdges']],
 ['ensemble','Ensemble',['ensembleIntelligence']],
 ['simulation','Simulation',['unifiedSimulation']],
 ['best','Best Bets',['bestBets','topPlays','best']],
 ['portfolio','Portfolio',['portfolio']],
 ['ai','AI Center',['ai']],
 ['results','Results',['results']],
 ['performance','Performance',['fullGamePerformance','projectionPerformance']],
 ['explainability','Explainability',['topPlays','best']],
 ['market','Market Intelligence',['marketIntelligence']],
 ['mission','Mission Control',['missionControl']],
 ['health','Health',['health']]
];
function resolve(names){for(const name of names){if(typeof window[name]==='function')return window[name]}return null}
function chrome(view){const tabs=document.getElementById('tabs');if(!tabs)return;tabs.innerHTML=NAV.map(([id,label])=>`<button class="tab ${id===view?'a':''}" data-view="${id}" onclick="window.render('${id}')">${label}</button>`).join('')}
function unavailable(view,names){return `<div class="section"><div class="routerError mono"><b>${esc(view)} is unavailable.</b><div class="routerMeta">Expected one of: ${esc(names.join(', '))}</div></div></div>`}
window.render=function(view='games'){
 const row=NAV.find(x=>x[0]===view)||NAV[0]; view=row[0]; chrome(view);
 const root=document.getElementById('root'); if(!root)return;
 try{
   const fn=resolve(row[2]);
   root.innerHTML=fn?String(fn()??''):unavailable(row[1],row[2]);
   if(!root.innerHTML.trim())root.innerHTML=unavailable(row[1],row[2]);
   if(view==='props'&&typeof window.drawProps==='function')window.drawProps();
 }catch(err){root.innerHTML=`<div class="section"><div class="routerError mono"><b>${esc(row[1])} failed to render.</b><div class="routerMeta">${esc(err&&err.stack?err.stack:String(err))}</div></div></div>`}
 window.scrollTo(0,0);
};
window.WNBA_FINAL_ROUTER={views:NAV.map(x=>x[0]),version:'final-router-v1'};
window.render('games');
})();</script>'''
def replace_block(html,start_marker,end_marker,replacement):
    s=html.find(start_marker)
    if s<0:return html
    e=html.find(end_marker,s)
    if e<0:return html
    return html[:s]+replacement.strip()+html[e+len(end_marker):]
def main():
    if not HTML.exists():raise SystemExit('docs/index.html missing')
    try:payload=json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
    except Exception:payload={}
    html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-alt-performance-data">DATA.alt_performance={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html=replace_block(html,'<script id="v4-alt-performance-data">','</script>',data) if 'id="v4-alt-performance-data"' in html else html.replace('</body>',data+'</body>')
    html=replace_block(html,'<style id="v4-alt-performance-style">','</style>',CSS) if 'id="v4-alt-performance-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace_block(html,'<script id="v4-alt-performance-script">','</script>',SCRIPT) if 'id="v4-alt-performance-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8');print('ALT Performance and final authoritative router applied')
if __name__=='__main__':main()
