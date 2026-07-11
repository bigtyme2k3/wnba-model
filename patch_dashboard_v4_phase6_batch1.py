"""Phase 6 batch 1: simplify Games, remove Sportsbooks, and render one clean card per game."""
from __future__ import annotations
import re
from pathlib import Path

HTML=Path('docs/index.html')
START='/* PHASE6_BATCH1_START */'
END='/* PHASE6_BATCH1_END */'

CSS=r'''
/* PHASE6_BATCH1_START */
.gameSummary{display:grid;grid-template-columns:82px 1fr auto;gap:12px;align-items:center}
.gameTime{font-size:13px;color:var(--muted);font-weight:800}
.gameMatchup{font-size:17px;font-weight:900;line-height:1.25}
.gameBest{margin-top:7px;color:var(--green);font-weight:900}
.gameBest.none{color:var(--muted);font-weight:700}
.gameEdge{font-size:13px;color:var(--muted);margin-left:8px}
.gameStars{font-size:16px;letter-spacing:1px;color:var(--gold);white-space:nowrap}
.gameDetails{display:none;margin-top:13px;padding-top:13px;border-top:1px solid var(--line)}
.gameCard.open .gameDetails{display:block}
.gameCard.simple{cursor:pointer;transition:border-color .15s ease}
.gameCard.simple:hover{border-color:#38527d}
.gameMeta{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}
.detailGrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px}
.detailBox{background:#0a1322;border:1px solid var(--line);border-radius:12px;padding:11px}
.nextTip{display:inline-flex;gap:8px;align-items:center;margin:0 0 12px;color:#cbd7f1;font-size:12px}
.nextTip b{color:var(--green)}
.gamesIntro{margin-bottom:12px;color:var(--muted);font-size:12px}
@media(max-width:900px){
 .gameSummary{grid-template-columns:68px 1fr auto;gap:8px}
 .gameMatchup{font-size:14px}.gameStars{font-size:13px}.detailGrid{grid-template-columns:1fr}
 .tabs .tab[data-tab="books"]{display:none!important}
}
/* PHASE6_BATCH1_END */
'''

JS=r'''
function decisionRows(){
  const pools=[DATA.market?.markets,DATA.market?.rows,DATA.master?.best_bets,DATA.master?.ranked_plays,DATA.portfolio?.final_decisions,DATA.portfolio?.recommended_card,DATA.master?.props];
  const seen=new Set();
  return pools.flatMap(x=>A(x)).filter(r=>{const k=[r.player,r.game||r.matchup,r.stat||r.market,r.line,r.signal||r.side,r.sportsbook].join('|');if(seen.has(k))return false;seen.add(k);return true});
}
function gameKey(g){return String(g.game_id||game(g)).trim().toLowerCase()}
function uniqueGames(rows){const seen=new Set();return A(rows).filter(g=>{const k=gameKey(g);if(!k||seen.has(k))return false;seen.add(k);return true})}
function isFinalGame(g){const s=String(g.status||'').toUpperCase();return s.includes('FINAL')||((g.away_score!==''&&g.away_score!=null)&&(g.home_score!==''&&g.home_score!=null))}
function gameRows(g){const name=game(g);return decisionRows().filter(r=>String(r.game||r.matchup||'')===name)}
function edgeOf(r){return Number(r.edge_pct??r.edge??r.model_edge??0)||0}
function confOf(r){return Number(r.confidence??r.final_score??r.consensus_score??0)||0}
function validLine(v){return v!==undefined&&v!==null&&v!==''&&Number.isFinite(Number(v))}
function validGamePlay(r){
  const side=String(r.signal||r.side||r.final_action||r.recommendation||'').toUpperCase();
  const action=String(r.final_action||r.recommendation||'').toUpperCase();
  return validLine(r.line??r.consensus_line)&&['OVER','UNDER','YES','NO'].includes(side)&&(edgeOf(r)>0||['BET','LEAN','WATCH'].includes(action));
}
function bestGamePlay(g){
  const rows=gameRows(g).filter(validGamePlay);
  rows.sort((a,b)=>edgeOf(b)-edgeOf(a)||confOf(b)-confOf(a));
  const r=rows[0];
  if(!r)return {label:'No qualified model play',edge:0,confidence:0,row:null};
  const market=String(r.stat||r.market||r.market_type||'PLAY').toUpperCase();
  const side=String(r.signal||r.side).toUpperCase();
  const line=S(r.line??r.consensus_line,'');
  return {label:[side,market,line].filter(Boolean).join(' '),edge:edgeOf(r),confidence:confOf(r),row:r};
}
function stars(c){const n=c>=85?5:c>=75?4:c>=65?3:c>=55?2:c>0?1:0;return n?'★'.repeat(n)+'☆'.repeat(5-n):'—'}
function timeOnly(v){if(!v)return 'TBD';const d=new Date(v);return isNaN(d)?String(v):d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}
function detailPlay(r){if(!r)return '';return `<div class="detailBox"><div class="label mono">Model Play</div><b class="mono">${E(S(r.signal||r.side))} ${E(S(r.stat||r.market))} ${E(S(r.line||r.consensus_line))}</b><div class="small mono">Edge ${edgeOf(r).toFixed(1)}% · Confidence ${confOf(r).toFixed(0)}</div></div>`}
function simpleGameCard(g){
  const best=bestGamePlay(g),rows=gameRows(g).filter(validGamePlay).sort((a,b)=>edgeOf(b)-edgeOf(a)).slice(0,4);
  const icons=[g.travel_flag?'✈️':'',g.back_to_back?'🔄':'',g.injury_flag?'🏥':''].filter(Boolean).join(' ');
  const bestClass=best.row?'gameBest':'gameBest none';
  return `<div class="gameCard simple" onclick="this.classList.toggle('open')"><div class="gameSummary"><div class="gameTime mono">${E(timeOnly(g.start_time||g.commence_time||g.date))}</div><div><div class="gameMatchup mono">${E(game(g))}</div><div class="${bestClass} mono">${E(best.label)}${best.edge?`<span class="gameEdge">+${best.edge.toFixed(1)} edge</span>`:''}</div></div><div class="gameStars" title="Model confidence">${stars(best.confidence)}</div></div><div class="gameMeta"><span class="small mono">${icons||'Tap for details'}</span></div><div class="gameDetails"><div class="detailGrid"><div class="detailBox"><div class="label mono">Market</div><div class="mono">Spread ${validLine(g.spread)?E(S(g.spread)):'—'}</div><div class="mono">Total ${validLine(g.total)?E(S(g.total)):'—'}</div></div><div class="detailBox"><div class="label mono">Game Status</div><div class="mono">${E(S(g.status,'Pregame'))}</div><div class="small mono">${E(fmt(g.start_time||g.commence_time||g.date))}</div></div>${rows.map(detailPlay).join('')}</div></div></div>`
}
function nextTip(t){
  const now=Date.now(),future=t.map(g=>({g,d:new Date(g.start_time||g.commence_time||g.date)})).filter(x=>!isNaN(x.d)&&x.d.getTime()>now).sort((a,b)=>a.d-b.d)[0];
  if(!future)return '';
  const mins=Math.max(0,Math.round((future.d-now)/60000)),h=Math.floor(mins/60),m=mins%60;
  return `<div class="nextTip mono">Next: <b>${E(game(future.g))}</b> in ${h?`${h}h `:''}${m}m</div>`
}
function resultCard(g){return `<div class="gameCard"><div class="row"><div><b class="mono">${E(game(g))}</b><div class="small mono">Final</div></div><div class="score mono">${E(score(g))}</div></div></div>`}
function games(){
  const allToday=uniqueGames(DATA.today_games),upcoming=allToday.filter(g=>!isFinalGame(g)),completedToday=allToday.filter(isFinalGame),previous=uniqueGames(DATA.yesterday_games),results=uniqueGames([...completedToday,...previous]);
  return `<div class="section"><h2 class="mono">Tonight</h2><div class="gamesIntro mono">One best qualified play per game. Tap a card for full details.</div>${nextTip(upcoming)}${upcoming.map(simpleGameCard).join('')||'<div class="empty mono">No remaining games tonight.</div>'}</div><div class="section"><h2 class="mono">Recent Results</h2>${results.map(resultCard).join('')||'<div class="empty mono">No completed results.</div>'}</div>`
}
'''

def main():
    if not HTML.exists():
        print('docs/index.html missing');return
    html=HTML.read_text(encoding='utf-8')
    html=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',html,flags=re.S)
    html=html.replace('</style>',CSS+'\n</style>',1)
    html=html.replace("const tabs=[['games','Games'],['props','Player Props'],['books','Sportsbooks'],['best','Best Bets'],['portfolio','Portfolio'],['ai','AI Center'],['results','Results'],['health','V4 Health']];","const tabs=[['games','Games'],['props','Player Props'],['best','Best Bets'],['portfolio','Portfolio'],['ai','AI Center'],['results','Results'],['health','V4 Health']];")
    html=re.sub(r'function games\(\)\{.*?\}\nfunction propsRaw\(\)',JS+'\nfunction propsRaw()',html,flags=re.S)
    HTML.write_text(html,encoding='utf-8')
    print('Phase 6 batch 1.1 applied: unique active games and qualified plays only')

if __name__=='__main__':main()
