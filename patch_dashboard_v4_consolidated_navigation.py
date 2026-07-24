from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

HTML=Path('docs/index.html');PERFORMANCE=Path('data/dashboard/wnba_alt_performance.json');LOGS=Path('data/warehouse/wnba_player_game_logs.json')
CSS=r'''<style id="v4-consolidated-navigation-style">.navSectionNote{margin:0 0 14px;color:#7e8ba3;font-size:12px}.performanceJump{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.performanceJump button{border:1px solid #263854;background:#08101c;color:#cbd7f1;border-radius:999px;padding:8px 12px;font-weight:800}.propsStack{display:grid;gap:16px}.streakNote{border:1px solid #263854;border-radius:14px;padding:12px;background:#0a1322}.aiCenterGrid{display:grid;grid-template-columns:1fr;gap:16px}#terminal-ui{display:none!important}body.show-system-health #terminal-ui{display:block!important}@media(min-width:1100px){.aiCenterGrid{grid-template-columns:1fr 1fr}}</style>'''
SCRIPT=r'''<script id="v4-consolidated-navigation-script">(function(){const NAV=[['today','Games'],['gameprops','Game Props'],['props','Player Props'],['altstreaks','ALT Streaks'],['dailyedges','Daily Edges'],['ensemble','Ensemble'],['best','Best Bets'],['portfolio','Portfolio'],['ai','AI Center'],['results','Results'],['health','V4 Health']];function safe(fn,fallback=''){try{return typeof fn==='function'?fn():fallback}catch(err){return `<div class="section"><div class="empty mono">Section unavailable: ${String(err)}</div></div>`}}function chrome(view){const tabs=document.getElementById('tabs');if(tabs)tabs.innerHTML=NAV.map(([id,label])=>`<button class="tab ${id===view?'a':''}" data-view="${id}" onclick="render('${id}')">${label}</button>`).join('')}function propsView(){return `<div class="propsStack">${safe(window.props||props)}</div>`}function altStreaksView(){const body=safe(window.altStreaks);return body||'<div class="section"><div class="empty mono">ALT streak data is not available yet.</div></div>'}function dailyEdgesView(){const body=safe(window.dailyEdges);return body||'<div class="section"><div class="empty mono">Daily edge data is not available yet.</div></div>'}function ensembleView(){const body=safe(window.ensembleIntelligence);return body||'<div class="section"><div class="empty mono">Ensemble intelligence is not available yet.</div></div>'}function aiView(){const ai=safe(window.ai||ai);return `<div class="section"><h2 class="mono">AI Center</h2><div class="navSectionNote mono">Research, explanations, trend discovery, and warehouse questions.</div></div><div class="aiCenterGrid"><div>${ai}</div></div>`}function healthView(){const health=safe(window.health||health);return `<div class="section"><h2 class="mono">System Health</h2><div class="navSectionNote mono">Data freshness, workflow status, source health, API usage, and technical diagnostics.</div></div>${health}`}window.render=function(view='today'){const aliases={games:'today',performance:'results',model:'ai',alt:'altstreaks',edges:'dailyedges',ensembleedges:'ensemble',altperf:'results',books:'props',q1:'gameprops'};view=aliases[view]||view;if(!NAV.some(([id])=>id===view))view='today';document.body.classList.toggle('show-system-health',view==='health');chrome(view);const root=document.getElementById('root');if(!root)return;if(view==='today')root.innerHTML=safe(window.games||games);else if(view==='gameprops')root.innerHTML=safe(window.gameProps);else if(view==='props'){root.innerHTML=propsView();if(typeof window.drawProps==='function')window.drawProps()}else if(view==='altstreaks')root.innerHTML=altStreaksView();else if(view==='dailyedges')root.innerHTML=dailyEdgesView();else if(view==='ensemble')root.innerHTML=ensembleView();else if(view==='best')root.innerHTML=safe(window.bestBets||window.best||best);else if(view==='portfolio')root.innerHTML=safe(window.portfolio||portfolio);else if(view==='ai')root.innerHTML=aiView();else if(view==='results')root.innerHTML=safe(window.results||results);else if(view==='health')root.innerHTML=healthView();window.scrollTo(0,0)};window.render('today')})();</script>'''
REAL_L5=r'''<script id="v4-real-last-five-script">(function(){
 const norm=v=>String(v??'').trim().toLowerCase();const n=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
 function history(r){const rows=(window.VERIFIED_PLAYER_HISTORY||{})[norm(r.player)]||[];const stat=String(r.stat||'').toUpperCase();return rows.map(g=>{const pts=n(g.pts),reb=n(g.reb),ast=n(g.ast),map={PTS:pts,REB:reb,AST:ast,'3PM':n(g.threes),PRA:pts!=null&&reb!=null&&ast!=null?pts+reb+ast:null,PR:pts!=null&&reb!=null?pts+reb:null,PA:pts!=null&&ast!=null?pts+ast:null,RA:reb!=null&&ast!=null?reb+ast:null,STL:n(g.stl),BLK:n(g.blk),TOV:n(g.tov)};return {value:map[stat],opp:g.opponent||'',date:g.date||''}}).filter(x=>x.value!=null).slice(0,10)}
 function rowBooks(r){return [r.book,r.best_book,r.best_over_book,r.best_under_book,r.over_book,r.under_book].filter(Boolean).map(norm)}
 function rowSide(r){return String(r.signal||r.side||'OVER').toUpperCase()}
 window.propRow=function(r){let team=(r.team&&norm(r.team)!=='nan')?r.team:teamFor(r),side=rowSide(r),line=Number(r.line??r.consensus_line??0),games=history(r),v10=games.map(x=>x.value),v5=v10.slice(0,5),h5=v5.length?hit(v5,line,side):{h:0,p:0},h10=v10.length?hit(v10,line,side):{h:0,p:0},avg=v5.length?(v5.reduce((a,b)=>a+b,0)/v5.length).toFixed(1):'—',boxes=v5.length?v5.map((v,i)=>`<div class="box ${isHit(v,line,side)?'':'miss'}"><div class="num mono">${E(v)}</div><div class="opp mono">${E(games[i]?.opp||'-')}</div></div>`).join(''):'<div class="small mono">Verified L5 unavailable</div>';return `<div class="propRow"><div class="player"><div class="logo mono">${E(abbr(team).slice(0,2)||String(r.player||'?').slice(0,2))}</div><div><div class="name">${E(r.player)}</div><div class="team mono">${E(abbr(team))}</div></div></div><div class="stat mono">${E(r.stat)}</div><div class="lineVal mono">${E(r.line??r.consensus_line)}</div><div class="odds mono">${E(r.best_over_price??r.over_price)}</div><div class="odds mono">${E(r.best_under_price??r.under_price)}</div><div class="hist"><div class="boxes">${boxes}</div><div class="avg mono">L5 ${E(r.stat)} avg ${avg}</div></div><div class="hit ${v5.length&&h5.p<50?'bad':''} mono"><div class="pct">${v5.length?h5.p+'%':'—'}</div><div>${E(side)}</div><div class="rec">${v5.length?h5.h+'/'+v5.length:'no data'}</div></div><div class="hit ${v10.length&&h10.p<50?'bad':''} mono"><div class="pct">${v10.length?h10.p+'%':'—'}</div><div>${E(side)}</div><div class="rec">${v10.length?h10.h+'/'+v10.length:'no data'}</div></div><div class="small mono">${E(r.confidence??r.final_score)}</div></div>`}
 window.drawProps=function(){const root=document.getElementById('propRows');if(!root)return;const p=norm(document.getElementById('fPlayer')?.value),st=norm(document.getElementById('fStat')?.value),bk=norm(document.getElementById('fBook')?.value),sd=String(document.getElementById('fSide')?.value||'').toUpperCase(),so=document.getElementById('fSort')?.value||'confidence';let rows=propsRaw().filter(r=>(!activeGame||norm(r.game)===norm(activeGame))&&(!p||norm(r.player).includes(p))&&(!st||norm(r.stat)===st)&&(!bk||rowBooks(r).includes(bk))&&(!sd||rowSide(r)===sd));rows.sort((a,b)=>so==='player'?String(a.player||'').localeCompare(String(b.player||'')):so==='stat'?String(a.stat||'').localeCompare(String(b.stat||'')):Number(b.final_score??b.confidence??0)-Number(a.final_score??a.confidence??0));root.innerHTML=rows.map(window.propRow).join('')||'<div class="empty mono">No props match.</div>'}
 window.setGame=function(g){activeGame=g;window.drawProps()};
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
 print('Dashboard uses warehouse-backed Last 5 stats, normalized filters, Daily Edges, and Ensemble navigation')
if __name__=='__main__':main()
