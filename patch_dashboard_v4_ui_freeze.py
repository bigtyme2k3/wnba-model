from __future__ import annotations

import re
from pathlib import Path

HTML = Path('docs/index.html')
STYLE_ID = 'v4-ui-freeze-style'
SCRIPT_ID = 'v4-ui-freeze-script'

STYLE = r'''<style id="v4-ui-freeze-style">
.inGameInjuryWrap{margin:14px 0;border:1px solid #263854;border-radius:14px;background:#08111f;padding:12px}
.inGameInjuryHead{display:flex;justify-content:space-between;gap:12px;align-items:center;font-weight:900}
.inGameInjuryGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin-top:10px}
.inGameInjuryCard{border:1px solid #20304b;border-radius:12px;padding:10px;background:#091321}
.inGameInjuryRow{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid #1b293e}.inGameInjuryRow:last-child{border-bottom:0}
.inGameInjuryOut{color:#ff7188}.inGameInjuryQ{color:#ffd06b}.inGameInjuryGood{color:#3de6b0}
.altPropsStack{display:grid;gap:16px}.uiFreezeUnavailable{padding:24px;border:1px solid #263854;border-radius:14px;background:#08111f;color:#9aabc5}
[data-v4-legacy-content="hidden"]{display:none!important}
.canonGate{display:inline-flex;gap:7px;align-items:center;border:1px solid #235444;background:#08261e;color:#72d8b3;border-radius:999px;padding:5px 9px;font-size:11px;margin:0 0 12px}.canonGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.canonCard{background:#0b1423;border:1px solid #263854;border-radius:15px;padding:13px}.canonCard h3{margin:3px 0 9px}.canonMetrics{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.canonMetric{border:1px solid #1d2c43;background:#08111f;border-radius:10px;padding:8px}.canonMetric b{display:block;margin-top:3px}.canonGood{color:#34d399}.canonWarn{color:#ffd166}.canonTable{width:100%;border-collapse:collapse}.canonTable th,.canonTable td{padding:8px;border-bottom:1px solid #1d2c43;text-align:left;vertical-align:top}.canonScroll{overflow:auto;max-height:72vh}.canonNote{color:#8190aa;font-size:11px;margin:6px 0 12px}.canonPill{display:inline-block;border:1px solid #304365;border-radius:999px;padding:4px 7px;margin:2px 4px 2px 0;font-size:11px}
</style>'''

SCRIPT = r'''<script id="v4-ui-freeze-script">(function(){
const NAV=[
 ['games','Games'],['game-performance','Game Performance'],['matchups','Matchups'],['props','Player Props'],['alt-props','ALT Props'],
 ['sportsbooks','Sportsbooks'],['best','Best Bets'],['ai','AI Center'],['live','Live'],['remaining','Remaining Season'],
 ['results','Results'],['portfolio','Portfolio'],['health','Data Health']
];
const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');
const invoke=(label,fns)=>{for(const fn of fns){try{if(typeof fn==='function'){const out=fn();if(typeof out==='string'&&out.trim())return out}}catch(e){console.error(label,e)}}return `<div class="section"><h2>${esc(label)}</h2><div class="uiFreezeUnavailable">${esc(label)} is not available in this build.</div></div>`};
const C=()=>window.WNBA_CANONICAL_DAILY||{};
const P2=()=>window.WNBA_SPRINT2_PHASE2||{};
const currentGames=()=>Array.isArray(C().games)?C().games:[];
const currentProps=()=>Array.isArray(C().props)?C().props:[];
const target=()=>String(C().target_date||P2().target_date||'');
const gate=()=>`<div class="canonGate">CURRENT SLATE · ${esc(target())}</div>`;
const unavailable=(label,msg='No current-slate data is available.')=>`<div class="section">${gate()}<h2 class="mono">${esc(label)}</h2><div class="uiFreezeUnavailable">${esc(msg)}</div></div>`;
function ensureRoot(){
 let root=document.getElementById('root');if(root)return root;
 const tabs=document.getElementById('tabs');if(!tabs)return null;
 root=document.createElement('div');root.id='root';root.setAttribute('data-v4-router-root','true');
 const parent=tabs.parentElement||document.body;parent.insertBefore(root,tabs.nextSibling);
 let node=root.nextSibling;
 while(node){const next=node.nextSibling;if(node.nodeType===1&&!['SCRIPT','STYLE'].includes(node.tagName))node.setAttribute('data-v4-legacy-content','hidden');node=next;}
 return root;
}
function chrome(view){const tabs=document.getElementById('tabs');if(tabs)tabs.innerHTML=NAV.map(([id,label])=>`<button class="tab ${id===view?'a':''}" data-view="${id}" onclick="window.render('${id}')">${label}</button>`).join('')}
function syncHeader(){const d=C();if(!d.target_date)return;const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;while(n=walker.nextNode()){if(/Slate\s+\d{4}-\d{2}-\d{2}/.test(n.nodeValue))n.nodeValue=n.nodeValue.replace(/Slate\s+\d{4}-\d{2}-\d{2}/,'Slate '+d.target_date);if(/Updated\s+[^\n]+/.test(n.nodeValue)&&d.generated_at_utc){const dt=new Date(d.generated_at_utc);const stamp=isNaN(dt)?d.generated_at_utc:dt.toLocaleString();n.nodeValue=n.nodeValue.replace(/Updated\s+[^\n]+/,'Updated '+stamp)}}}
function p2Games(){const D=P2();return D.target_date===target()&&Array.isArray(D.games)?D.games:[]}
function canonicalMatchups(){const games=p2Games();if(!games.length)return unavailable('Matchups');return `<div class="section">${gate()}<h2 class="mono">Matchups</h2><div class="canonNote mono">Only games from the canonical ${esc(target())} slate are allowed in this view.</div><div class="canonGrid">${games.map(g=>{const p=g.projection||{},m=g.market||{},e=g.edge||{},r=g.recommendation||{};return `<div class="canonCard"><div class="label mono">MATCHUP</div><h3 class="mono">${esc(g.game)}</h3><div class="canonMetrics"><div class="canonMetric">Projected<b>${esc(g.away_team)} ${esc(p.away_score??'—')} · ${esc(g.home_team)} ${esc(p.home_score??'—')}</b></div><div class="canonMetric">Win Probability<b>${esc(g.home_team)} ${p.home_win_probability==null?'—':(Number(p.home_win_probability)*100).toFixed(1)+'%'}</b></div><div class="canonMetric">Spread<b>Book ${esc(m.home_spread??'—')} · Model ${esc(p.model_home_spread??'—')}</b><span class="canonGood">Edge ${esc(e.spread??'—')}</span></div><div class="canonMetric">Total<b>Book ${esc(m.total??'—')} · Model ${esc(p.total??'—')}</b><span class="canonGood">Edge ${esc(e.total??'—')}</span></div><div class="canonMetric">Pace<b>${esc(g.pace_index??'—')} ${esc(g.pace_label??'')}</b></div><div class="canonMetric">Model<b>${esc(r.spread||'PASS')} · ${esc(r.total||'PASS')}</b>Grade ${esc(g.model_grade||'—')} · Conf ${esc(g.confidence??'—')}</div></div></div>`}).join('')}</div></div>`}
function canonicalSportsbooks(){const rows=currentProps().filter(r=>!r.game||currentGames().some(g=>g.game===r.game));if(!rows.length)return unavailable('Sportsbooks');return `<div class="section">${gate()}<h2 class="mono">Sportsbooks · Current Slate</h2><div class="canonNote mono">Canonical Odds API only. Off-slate markets are quarantined from this view.</div><div class="canonScroll"><table class="canonTable"><thead><tr><th>Player</th><th>Game</th><th>Stat</th><th>Line</th><th>Best Over</th><th>Best Under</th></tr></thead><tbody>${rows.slice(0,500).map(r=>`<tr><td><b>${esc(r.player)}</b><div class="small mono">${esc(r.team)}</div></td><td>${esc(r.game)}</td><td>${esc(r.stat)}</td><td>${esc(r.line)}</td><td>${esc(r.best_over_book)} ${esc(r.best_over_price)}</td><td>${esc(r.best_under_book)} ${esc(r.best_under_price)}</td></tr>`).join('')}</tbody></table></div></div>`}
function canonicalAltProps(){const rows=currentProps().filter(r=>!r.game||currentGames().some(g=>g.game===r.game));const groups={};rows.forEach(r=>{const k=[r.game,r.player,r.stat].join('|');(groups[k]||(groups[k]=[])).push(r)});const ladders=Object.values(groups).filter(a=>new Set(a.map(x=>String(x.line))).size>1).sort((a,b)=>b.length-a.length);if(!ladders.length)return unavailable('ALT Props','No verified current-slate alternate ladders are available.');return `<div class="section">${gate()}<h2 class="mono">ALT Props</h2><div class="canonNote mono">Current-slate ladders reconstructed only from canonical sportsbook rows.</div><div class="canonGrid">${ladders.slice(0,60).map(a=>`<div class="canonCard"><div class="label mono">${esc(a[0].game)}</div><h3 class="mono">${esc(a[0].player)} · ${esc(a[0].stat)}</h3>${a.sort((x,y)=>Number(x.line)-Number(y.line)).map(r=>`<div class="canonMetric" style="margin-top:6px"><b>Line ${esc(r.line)}</b><span class="canonPill">O ${esc(r.best_over_book)} ${esc(r.best_over_price)}</span><span class="canonPill">U ${esc(r.best_under_book)} ${esc(r.best_under_price)}</span></div>`).join('')}</div>`).join('')}</div></div>`}
function currentBetCandidates(){const out=[];p2Games().forEach(g=>{const r=g.recommendation||{},e=g.edge||{},m=g.market||{},p=g.projection||{};if(r.spread&&r.spread!=='PASS')out.push({game:g.game,type:'SPREAD',pick:r.spread,edge:Math.abs(Number(e.spread||0)),detail:`Book ${m.home_spread??'—'} · Model ${p.model_home_spread??'—'}`,confidence:g.confidence,grade:g.model_grade});if(r.total&&r.total!=='PASS')out.push({game:g.game,type:'TOTAL',pick:r.total,edge:Math.abs(Number(e.total||0)),detail:`Book ${m.total??'—'} · Model ${p.total??'—'}`,confidence:g.confidence,grade:g.model_grade})});return out.sort((a,b)=>(b.edge-a.edge)||((b.confidence||0)-(a.confidence||0)))}
function canonicalBest(){const bets=currentBetCandidates();if(!bets.length)return unavailable('Best Bets','No current-slate game recommendations cleared the Phase 2 recommendation thresholds.');return `<div class="section">${gate()}<h2 class="mono">Best Bets · Current Slate</h2><div class="canonNote mono">Stale player recommendations are blocked. These are current Phase 2 game candidates only.</div><div class="canonGrid">${bets.map((b,i)=>`<div class="canonCard"><div class="label mono">${i<3?'TOP CURRENT EDGE':'CURRENT EDGE'} · ${esc(b.type)}</div><h3 class="mono">${esc(b.pick)}</h3><div>${esc(b.game)}</div><div class="canonPill canonGood">Edge ${b.edge.toFixed(1)}</div><div class="canonPill">Confidence ${esc(b.confidence??'—')}</div><div class="canonPill">Grade ${esc(b.grade??'—')}</div><div class="canonNote">${esc(b.detail)}</div></div>`).join('')}</div></div>`}
function canonicalAI(){const games=p2Games();if(!games.length)return unavailable('AI Center');return `<div class="section">${gate()}<h2 class="mono">AI Center · Current Slate</h2><div class="canonNote mono">Explanations are generated from current Phase 2 projections; stale prior-slate watchlists are blocked.</div><div class="canonGrid">${games.map(g=>{const p=g.projection||{},m=g.market||{},e=g.edge||{},r=g.recommendation||{},reasons=[];reasons.push(`Projected ${g.away_team} ${p.away_score??'—'} · ${g.home_team} ${p.home_score??'—'}`);if(r.spread&&r.spread!=='PASS')reasons.push(`Spread lean ${r.spread}: model/market gap ${e.spread??'—'}`);else reasons.push('Spread does not clear the current recommendation threshold');if(r.total&&r.total!=='PASS')reasons.push(`Total lean ${r.total}: model/market gap ${e.total??'—'}`);else reasons.push('Total does not clear the current recommendation threshold');reasons.push(`Pace ${g.pace_index??'—'} ${g.pace_label??''}; rest advantage home ${g.rest_advantage_home??'—'}d; injury adjusted ${g.injury_adjusted?'yes':'no'}`);return `<div class="canonCard"><div class="label mono">GRADE ${esc(g.model_grade||'—')} · CONF ${esc(g.confidence??'—')}</div><h3 class="mono">${esc(g.game)}</h3>${reasons.map(x=>`<div class="canonMetric" style="margin-top:6px">${esc(x)}</div>`).join('')}</div>`}).join('')}</div></div>`}
function canonicalLive(){const games=currentGames().filter(g=>/IN_PROGRESS|LIVE/i.test(String(g.status||'')));if(!games.length)return unavailable('Live','No canonical current-slate games are live right now.');return `<div class="section">${gate()}<h2 class="mono">Live</h2><div class="canonGrid">${games.map(g=>`<div class="canonCard"><h3 class="mono">${esc(g.game)}</h3><div class="canonPill canonGood">${esc(g.status)}</div><div class="canonNote">Live recommendations remain gated to verified live-state inputs.</div></div>`).join('')}</div></div>`}
function canonicalPortfolio(){const bets=currentBetCandidates();if(!bets.length)return unavailable('Portfolio','No current-slate candidates are available for portfolio construction.');return `<div class="section">${gate()}<h2 class="mono">Portfolio · Current Slate</h2><div class="canonNote mono">Old-slate stakes are blocked. Phase 2 has not assigned bankroll stakes to these candidates yet.</div><div class="canonGrid">${bets.map(b=>`<div class="canonCard"><h3 class="mono">${esc(b.pick)}</h3><div>${esc(b.game)}</div><div class="canonPill">${esc(b.type)}</div><div class="canonPill canonGood">Edge ${b.edge.toFixed(1)}</div><div class="canonPill">Stake pending</div></div>`).join('')}</div></div>`}
function injurySummary(){const D=window.WNBA_INJURY_DATA||{};const injuries=Array.isArray(D.injuries)&&String(D.target_date||'')===target()?D.injuries:[];const games=currentGames();if(!injuries.length)return '';
 const cards=games.map(g=>{const teams=[g.away_team,g.home_team].filter(Boolean);const rows=injuries.filter(x=>teams.includes(x.team));if(!rows.length)return `<div class="inGameInjuryCard"><b>${esc(g.game)}</b><div class="small mono inGameInjuryGood">No listed injuries</div></div>`;return `<div class="inGameInjuryCard"><b>${esc(g.game)}</b>${rows.map(x=>{const s=String(x.severity||x.status||'').toUpperCase();const cls=['OUT','DOUBTFUL'].includes(s)?'inGameInjuryOut':s==='QUESTIONABLE'?'inGameInjuryQ':'inGameInjuryGood';return `<div class="inGameInjuryRow"><span>${esc(x.player)} <span class="small mono">${esc(x.team)}</span></span><b class="${cls}">${esc(s||'LISTED')}</b></div>`}).join('')}</div>`}).join('');
 return `<div class="inGameInjuryWrap" id="games-injury-intelligence"><div class="inGameInjuryHead"><span>Injuries & Availability</span><span class="small mono">${esc(target())}</span></div><div class="inGameInjuryGrid">${cards}</div></div>`}
function decorateGames(){const root=ensureRoot();if(!root||document.getElementById('games-injury-intelligence'))return;const html=injurySummary();if(!html)return;const section=root.querySelector('.section')||root.firstElementChild;if(section)section.insertAdjacentHTML('afterbegin',html);else root.insertAdjacentHTML('afterbegin',html)}
window.render=function(view='games'){
 const aliases={today:'games',gameperf:'game-performance',alt:'alt-props',altstreaks:'alt-props',altperf:'alt-props',books:'sportsbooks',injuries:'games',performance:'game-performance'};view=aliases[view]||view;if(!NAV.some(x=>x[0]===view))view='games';chrome(view);document.body.classList.toggle('show-system-health',view==='health');const root=ensureRoot();if(!root)return;let html='';
 if(view==='games')html=invoke('Games',[window.gamesV25,window.games]);
 else if(view==='game-performance')html=invoke('Game Performance',[window.fullGamePerformance,window.projectionPerformance,window.gamePerformance]);
 else if(view==='matchups')html=canonicalMatchups();
 else if(view==='props')html=invoke('Player Props',[window.WNBA_CANONICAL_PROPS]);
 else if(view==='alt-props')html=canonicalAltProps();
 else if(view==='sportsbooks')html=canonicalSportsbooks();
 else if(view==='best')html=canonicalBest();
 else if(view==='ai')html=canonicalAI();
 else if(view==='live')html=canonicalLive();
 else if(view==='remaining')html=invoke('Remaining Season',[window.remainingSeasonIntelligence,window.remainingSeason]);
 else if(view==='results')html=invoke('Results',[window.results]);
 else if(view==='portfolio')html=canonicalPortfolio();
 else if(view==='health')html=invoke('Data Health',[window.health]);
 root.innerHTML=html;if(view==='props'&&typeof window.drawProps==='function')setTimeout(()=>{try{window.drawProps()}catch(e){}},0);if(view==='games')setTimeout(decorateGames,0);syncHeader();window.scrollTo(0,0)
};
window.WNBA_V4_UI_FREEZE={version:'1.2',tabs:NAV.map(x=>x[0]),injuries_location:'games',alt_props_tab:true,dynamic_root:true,current_slate_gate:true};
ensureRoot();syncHeader();window.render('games');
})();</script>'''


def replace_element(html: str, tag: str, element_id: str, replacement: str) -> str:
    pattern = rf'<{tag} id="{re.escape(element_id)}">.*?</{tag}>'
    html, count = re.subn(pattern, replacement, html, count=1, flags=re.S)
    if count:
        return html
    anchor = '</head>' if tag == 'style' else '</body>'
    return html.replace(anchor, replacement + '\n' + anchor, 1)


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    html = HTML.read_text(encoding='utf-8')
    html = replace_element(html, 'style', STYLE_ID, STYLE)
    html = replace_element(html, 'script', SCRIPT_ID, SCRIPT)
    HTML.write_text(html, encoding='utf-8')
    print({'status':'PASS','tabs':13,'alt_props':True,'injuries_in_games':True,'standalone_injuries':False,'dynamic_root':True,'current_slate_gate':True})


if __name__ == '__main__':
    main()
