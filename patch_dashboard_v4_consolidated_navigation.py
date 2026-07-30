from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

HTML=Path('docs/index.html');PERFORMANCE=Path('data/dashboard/wnba_alt_performance.json');LOGS=Path('data/warehouse/wnba_player_game_logs.json')
CSS=r'''<style id="v4-consolidated-navigation-style">.navSectionNote{margin:0 0 14px;color:#7e8ba3;font-size:12px}.performanceJump{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.performanceJump button{border:1px solid #263854;background:#08101c;color:#cbd7f1;border-radius:999px;padding:8px 12px;font-weight:800}.propsStack{display:grid;gap:16px}.streakNote{border:1px solid #263854;border-radius:14px;padding:12px;background:#0a1322}.aiCenterGrid{display:grid;grid-template-columns:1fr;gap:16px}.routerError{border:1px solid #ff4d67;background:#210b12;color:#ff9aaa;border-radius:14px;padding:16px}.routerError pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:10px}#terminal-ui{display:none!important}body.show-system-health #terminal-ui{display:block!important}@media(min-width:1100px){.aiCenterGrid{grid-template-columns:1fr 1fr}}</style>'''
SCRIPT=r'''<script id="v4-consolidated-navigation-script">(function(){
if(typeof window.E!=='function')window.E=function(v){return String(v??'').replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})};
if(typeof window.S!=='function')window.S=function(v,d='—'){return v===undefined||v===null||v===''?d:v};
if(typeof window.q!=='function')window.q=function(id){return document.getElementById(id)};
window.sortableLabel=function(key,label){return String(label??key??'')};
window.sortLabel=window.sortableLabel;
if(typeof window.game!=='function')window.game=function(row){if(!row||typeof row!=='object')return String(row??'');return row.game||row.matchup||row.name||[row.away_team||row.away,row.home_team||row.home].filter(Boolean).join(' @ ')};
const NAV=[['games','Games'],['gameprops','Game Props'],['props','Player Props'],['altstreaks','ALT Streaks'],['altperf','ALT Performance'],['dailyedges','Daily Edges'],['ensemble','Ensemble'],['simulation','Simulation'],['best','Best Bets'],['portfolio','Portfolio'],['ai','AI Center'],['results','Results'],['performance','Performance'],['explainability','Explainability'],['market','Market Intelligence'],['mission','Mission Control'],['health','V4 Health']];
const arr=v=>Array.isArray(v)?v:[];const esc=v=>window.E(v);window.activeGame=window.activeGame||'';
window.propsRaw=function(){const source=arr(DATA?.master?.props).length?arr(DATA.master.props):arr(DATA?.props);const map=new Map();for(const r of source){if(!r||typeof r!=='object')continue;const key=[r.player,r.stat,r.line??r.consensus_line,r.game,r.best_over_price??r.over_price,r.best_under_price??r.under_price].join('|').toLowerCase();const old=map.get(key);if(!old||Number(r.book_count||0)>Number(old.book_count||0)||Number(r.confidence||r.final_score||0)>Number(old.confidence||old.final_score||0))map.set(key,r)}return [...map.values()]};
function optionList(values){return [...new Set(values.filter(Boolean).map(String))].sort().map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('')}
const canonicalProps=function(){const rows=window.propsRaw();const stats=optionList(rows.map(r=>r.stat));const books=optionList(rows.flatMap(r=>[r.book,r.best_book,r.best_over_book,r.best_under_book]));return `<div class="section"><h2 class="mono">Player Props</h2><div class="small mono">Current sportsbook lines with verified history and model context.</div><div class="tools"><input id="fPlayer" placeholder="Player" oninput="window.drawProps&&window.drawProps()"><select id="fStat" onchange="window.drawProps&&window.drawProps()"><option value="">All stats</option>${stats}</select><select id="fSide" onchange="window.drawProps&&window.drawProps()"><option value="">All sides</option><option>OVER</option><option>UNDER</option></select><select id="fBook" onchange="window.drawProps&&window.drawProps()"><option value="">All books</option>${books}</select><input id="fSearch" placeholder="Search all fields" oninput="window.drawProps&&window.drawProps()"></div><div class="small mono" id="propCount"></div><div class="propScroll"><div class="propHead mono"><div>Player</div><div>Stat</div><div>Line</div><div>Over</div><div>Under</div><div>L5 Stats</div><div>L5 Hit</div><div>L10 Hit</div><div>Match</div></div><div id="propRows"></div></div></div>`};
window.WNBA_CANONICAL_PROPS=canonicalProps;window.props=canonicalProps;
function fail(label,error){return `<div class="section"><div class="routerError"><b>${esc(label)} failed to render.</b><pre>${esc(error?.stack||String(error))}</pre></div></div>`}
function invoke(label,candidates){for(const fn of candidates){try{if(typeof fn==='function'){const html=fn();if(typeof html==='string'&&html.trim())return html}}catch(error){return fail(label,error)}}return `<div class="section"><div class="routerError"><b>${esc(label)} is unavailable.</b><div class="small mono">Expected a compatible renderer.</div></div></div>`}
function chrome(view){const tabs=document.getElementById('tabs');if(tabs)tabs.innerHTML=NAV.map(([id,label])=>`<button class="tab ${id===view?'a':''}" data-view="${id}" onclick="window.render('${id}')">${label}</button>`).join('')}
window.render=function(view='games'){const aliases={today:'games',markets:'gameprops',books:'props',alt:'altstreaks',edges:'dailyedges',ensembleedges:'ensemble',model:'ai'};view=aliases[view]||view;if(!NAV.some(([id])=>id===view))view='games';document.body.classList.toggle('show-system-health',view==='health');chrome(view);const root=document.getElementById('root');if(!root)return;let html='';if(view==='games')html=invoke('Games',[window.gamesV25,window.games]);else if(view==='gameprops')html=invoke('Game Props',[window.marketsV25,window.gameProps]);else if(view==='props')html=invoke('Player Props',[canonicalProps]);else if(view==='altstreaks')html=invoke('ALT Streaks',[window.altStreaks]);else if(view==='altperf')html=invoke('ALT Performance',[window.altPerformance]);else if(view==='dailyedges')html=invoke('Daily Edges',[window.dailyEdges]);else if(view==='ensemble')html=invoke('Ensemble',[window.ensembleIntelligence]);else if(view==='simulation')html=invoke('Simulation',[window.unifiedSimulation]);else if(view==='best')html=invoke('Best Bets',[window.bestBets,window.topPlays,window.best]);else if(view==='portfolio')html=invoke('Portfolio',[window.portfolio]);else if(view==='ai')html=invoke('AI Center',[window.ai]);else if(view==='results')html=invoke('Results',[window.results]);else if(view==='performance')html=invoke('Performance',[window.fullGamePerformance,window.projectionPerformance]);else if(view==='explainability')html=invoke('Explainability',[window.explainability]);else if(view==='market')html=invoke('Market Intelligence',[window.marketIntelligence]);else if(view==='mission')html=invoke('Mission Control',[window.missionControl]);else if(view==='health')html=invoke('V4 Health',[window.health]);root.innerHTML=html;if(view==='props'&&typeof window.drawProps==='function'){try{window.drawProps()}catch(error){root.innerHTML=fail('Player Props',error)}}window.scrollTo(0,0)};
window.WNBA_FINAL_ROUTER={version:'2.3',tabs:NAV.map(x=>x[0]),props_api:true,compatibility_helpers:['E','S','q','game','sortableLabel','sortLabel']};window.render('games')})();</script>'''
REAL_L5=r'''<script id="v4-real-last-five-script">(function(){
 const norm=v=>String(v??'').trim().toLowerCase();const n=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
 function history(r){const rows=(window.VERIFIED_PLAYER_HISTORY||{})[norm(r.player)]||[];const stat=String(r.stat||'').toUpperCase();return rows.map(g=>{const pts=n(g.pts),reb=n(g.reb),ast=n(g.ast),map={PTS:pts,REB:reb,AST:ast,'3PM':n(g.threes),PRA:pts!=null&&reb!=null&&ast!=null?pts+reb+ast:null,PR:pts!=null&&reb!=null?pts+reb:null,PA:pts!=null&&ast!=null?pts+ast:null,RA:reb!=null&&ast!=null?reb+ast:null,STL:n(g.stl),BLK:n(g.blk),TOV:n(g.tov)};return {value:map[stat],opp:g.opponent||'',date:g.date||''}}).filter(x=>x.value!=null).slice(0,10)}
 function rowBooks(r){return [r.book,r.best_book,r.best_over_book,r.best_under_book,r.over_book,r.under_book].filter(Boolean).map(norm)}
 function rowSide(r){return String(r.signal||r.side||'OVER').toUpperCase()}
 window.propRow=function(r){let team=(r.team&&norm(r.team)!=='nan')?r.team:(typeof teamFor==='function'?teamFor(r):''),side=rowSide(r),line=Number(r.line??r.consensus_line??0),games=history(r),v10=games.map(x=>x.value),v5=v10.slice(0,5),h5=v5.length&&typeof hit==='function'?hit(v5,line,side):{h:0,p:0},h10=v10.length&&typeof hit==='function'?hit(v10,line,side):{h:0,p:0},avg=v5.length?(v5.reduce((a,b)=>a+b,0)/v5.length).toFixed(1):'—',boxes=v5.length?v5.map((v,i)=>`<div class="box ${typeof isHit==='function'&&!isHit(v,line,side)?'miss':''}"><div class="num mono">${E(v)}</div><div class="opp mono">${E(games[i]?.opp||'-')}</div></div>`).join(''):'<div class="small mono">Verified L5 unavailable</div>';return `<div class="propRow"><div class="player"><div class="logo mono">${E((typeof abbr==='function'?abbr(team):team).slice(0,2)||String(r.player||'?').slice(0,2))}</div><div><div class="name">${E(r.player)}</div><div class="team mono">${E(typeof abbr==='function'?abbr(team):team)}</div></div></div><div class="stat mono">${E(r.stat)}</div><div class="lineVal mono">${E(r.line??r.consensus_line)}</div><div class="odds mono">${E(r.best_over_price??r.over_price)}</div><div class="odds mono">${E(r.best_under_price??r.under_price)}</div><div class="hist"><div class="boxes">${boxes}</div><div class="avg mono">L5 ${E(r.stat)} avg ${avg}</div></div><div class="hit mono"><div class="pct">${v5.length?h5.p+'%':'—'}</div><div>${E(side)}</div><div class="rec">${v5.length?h5.h+'/'+v5.length:'no data'}</div></div><div class="hit mono"><div class="pct">${v10.length?h10.p+'%':'—'}</div><div>${E(side)}</div><div class="rec">${v10.length?h10.h+'/'+v10.length:'no data'}</div></div><div class="small mono">${E(r.confidence??r.final_score)}</div></div>`}
 window.drawProps=function(){const root=document.getElementById('propRows');if(!root)return;const p=norm(document.getElementById('fPlayer')?.value),st=norm(document.getElementById('fStat')?.value),bk=norm(document.getElementById('fBook')?.value),sd=String(document.getElementById('fSide')?.value||'').toUpperCase(),search=norm(document.getElementById('fSearch')?.value);let rows=window.propsRaw().filter(r=>(!window.activeGame||norm(r.game)===norm(window.activeGame))&&(!p||norm(r.player).includes(p))&&(!st||norm(r.stat)===st)&&(!bk||rowBooks(r).includes(bk))&&(!sd||rowSide(r)===sd)&&(!search||JSON.stringify(r).toLowerCase().includes(search)));root.innerHTML=rows.map(window.propRow).join('')||'<div class="empty mono">No props match.</div>';const count=document.getElementById('propCount');if(count)count.textContent=`Showing ${rows.length} of ${window.propsRaw().length} unique props`}
 window.setGame=function(g){window.activeGame=g;window.render('props')};
})();</script>'''
def replace_block(html,start,end,replacement):
 i=html.find(start)
 if i<0:return html
 j=html.find(end,i)
 if j<0:return html
 return html[:i]+replacement.strip()+html[j+len(end):]
def verified_history():
 try: payload=json.load(LOGS.open(encoding='utf-8')) if LOGS.exists() else {}
 except Exception: payload={}
 groups=defaultdict(list)
 for r in payload.get('records',[]):
  if not isinstance(r,dict) or r.get('did_not_play') is True: continue
  player=' '.join(str(r.get('player') or '').strip().lower().split())
  if not player: continue
  scoring=r.get('scoring') if isinstance(r.get('scoring'),dict) else {};box=r.get('boxscore') if isinstance(r.get('boxscore'),dict) else {}
  groups[player].append({'date':r.get('game_date'),'opponent':r.get('opponent'),'pts':scoring.get('total_pts'),'reb':box.get('reb'),'ast':box.get('ast'),'threes':scoring.get('three_pm'),'stl':box.get('stl'),'blk':box.get('blk'),'tov':box.get('tov')})
 for rows in groups.values(): rows.sort(key=lambda x:str(x.get('date') or ''),reverse=True);del rows[10:]
 return groups
def refresh_clv():
 try:
  perf=json.load(PERFORMANCE.open(encoding='utf-8')) if PERFORMANCE.exists() else {};target=str(perf.get('target_date') or '')
  if target:
   from wnba_alt_closing_line_tracker import snapshot,resolve,report
   snapshot(target);resolve(target);report(target)
  from wnba_alt_performance_clv_context import main as attach
  attach()
 except Exception as exc:print('Streak CLV warning:',exc)
def main():
 if not HTML.exists():raise SystemExit('docs/index.html missing')
 refresh_clv();html=HTML.read_text(encoding='utf-8')
 html=replace_block(html,'<style id="v4-consolidated-navigation-style">','</style>',CSS) if 'id="v4-consolidated-navigation-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-consolidated-navigation-script">','</script>',SCRIPT) if 'id="v4-consolidated-navigation-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 data='<script id="v4-verified-player-history-data">window.VERIFIED_PLAYER_HISTORY='+json.dumps(verified_history(),separators=(',',':'),allow_nan=False)+'</script>'
 html=replace_block(html,'<script id="v4-verified-player-history-data">','</script>',data) if 'id="v4-verified-player-history-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<script id="v4-real-last-five-script">','</script>',REAL_L5) if 'id="v4-real-last-five-script"' in html else html.replace('</body>',REAL_L5+'</body>')
 HTML.write_text(html,encoding='utf-8')
 try:
  from patch_dashboard_v4_alt_clv import main as patch
  patch()
 except Exception as exc:print('Streak CLV dashboard warning:',exc)
 print('Canonical router, shared Player Props API, and stable runtime helpers installed')
if __name__=='__main__':main()
