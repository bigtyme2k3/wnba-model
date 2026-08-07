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
</style>'''

SCRIPT = r'''<script id="v4-ui-freeze-script">(function(){
const NAV=[
 ['games','Games'],['game-performance','Game Performance'],['matchups','Matchups'],['props','Player Props'],['alt-props','ALT Props'],
 ['sportsbooks','Sportsbooks'],['best','Best Bets'],['ai','AI Center'],['live','Live'],['remaining','Remaining Season'],
 ['results','Results'],['portfolio','Portfolio'],['health','Data Health']
];
const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');
const invoke=(label,fns)=>{for(const fn of fns){try{if(typeof fn==='function'){const out=fn();if(typeof out==='string'&&out.trim())return out}}catch(e){console.error(label,e)}}return `<div class="section"><h2>${esc(label)}</h2><div class="uiFreezeUnavailable">${esc(label)} is not available in this build.</div></div>`};
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
function matchupFallback(){const C=window.WNBA_CANONICAL_DAILY||{};const games=Array.isArray(C.games)?C.games:[];return `<div class="section"><h2 class="mono">Matchups</h2><div class="small mono">Current slate matchup overview.</div><div class="grid">${games.map(g=>`<div class="card"><b>${esc(g.game)}</b><div class="small mono">Spread ${esc(g.spread)} · Total ${esc(g.total)}</div></div>`).join('')||'<div class="uiFreezeUnavailable">No current-slate games.</div>'}</div></div>`}
function altProps(){const parts=[];if(typeof window.altLadders==='function')parts.push(window.altLadders());if(typeof window.altStreaks==='function')parts.push(window.altStreaks());if(typeof window.altPerformance==='function')parts.push(window.altPerformance());const unique=[];for(const p of parts){if(p&&typeof p==='string'&&!unique.includes(p))unique.push(p)}return `<div class="altPropsStack">${unique.join('')||'<div class="section"><h2>ALT Props</h2><div class="uiFreezeUnavailable">ALT props are unavailable.</div></div>'}</div>`}
function injurySummary(){const D=window.WNBA_INJURY_DATA||{};const C=window.WNBA_CANONICAL_DAILY||{};const injuries=Array.isArray(D.injuries)?D.injuries:[];const games=Array.isArray(C.games)?C.games:[];if(!injuries.length)return '';
 const cards=games.map(g=>{const teams=[g.away_team,g.home_team].filter(Boolean);const rows=injuries.filter(x=>teams.includes(x.team));if(!rows.length)return `<div class="inGameInjuryCard"><b>${esc(g.game)}</b><div class="small mono inGameInjuryGood">No listed injuries</div></div>`;return `<div class="inGameInjuryCard"><b>${esc(g.game)}</b>${rows.map(x=>{const s=String(x.severity||x.status||'').toUpperCase();const cls=['OUT','DOUBTFUL'].includes(s)?'inGameInjuryOut':s==='QUESTIONABLE'?'inGameInjuryQ':'inGameInjuryGood';return `<div class="inGameInjuryRow"><span>${esc(x.player)} <span class="small mono">${esc(x.team)}</span></span><b class="${cls}">${esc(s||'LISTED')}</b></div>`}).join('')}</div>`}).join('');
 return `<div class="inGameInjuryWrap" id="games-injury-intelligence"><div class="inGameInjuryHead"><span>Injuries & Availability</span><span class="small mono">${esc(D.target_date||C.target_date||'')}</span></div><div class="inGameInjuryGrid">${cards}</div></div>`}
function decorateGames(){const root=ensureRoot();if(!root||document.getElementById('games-injury-intelligence'))return;const html=injurySummary();if(!html)return;const section=root.querySelector('.section')||root.firstElementChild;if(section)section.insertAdjacentHTML('afterbegin',html);else root.insertAdjacentHTML('afterbegin',html)}
window.render=function(view='games'){
 const aliases={today:'games',gameperf:'game-performance',alt:'alt-props',altstreaks:'alt-props',altperf:'alt-props',books:'sportsbooks',injuries:'games',performance:'game-performance'};view=aliases[view]||view;if(!NAV.some(x=>x[0]===view))view='games';chrome(view);document.body.classList.toggle('show-system-health',view==='health');const root=ensureRoot();if(!root)return;let html='';
 if(view==='games')html=invoke('Games',[window.gamesV25,window.games]);
 else if(view==='game-performance')html=invoke('Game Performance',[window.fullGamePerformance,window.projectionPerformance,window.gamePerformance]);
 else if(view==='matchups')html=invoke('Matchups',[window.matchups,window.matchupIntelligence,matchupFallback]);
 else if(view==='props')html=invoke('Player Props',[window.WNBA_CANONICAL_PROPS,window.props]);
 else if(view==='alt-props')html=altProps();
 else if(view==='sportsbooks')html=invoke('Sportsbooks',[window.sportsbooks,window.books,window.marketIntelligence]);
 else if(view==='best')html=invoke('Best Bets',[window.best,window.bestBets,window.topPlays]);
 else if(view==='ai')html=invoke('AI Center',[window.ai]);
 else if(view==='live')html=invoke('Live',[window.live,window.liveCenter,window.liveOdds]);
 else if(view==='remaining')html=invoke('Remaining Season',[window.remainingSeasonIntelligence,window.remainingSeason]);
 else if(view==='results')html=invoke('Results',[window.results]);
 else if(view==='portfolio')html=invoke('Portfolio',[window.portfolio]);
 else if(view==='health')html=invoke('Data Health',[window.health]);
 root.innerHTML=html;if(view==='props'&&typeof window.drawProps==='function')setTimeout(()=>{try{window.drawProps()}catch(e){}},0);if(view==='games')setTimeout(decorateGames,0);window.scrollTo(0,0)
};
window.WNBA_V4_UI_FREEZE={version:'1.1',tabs:NAV.map(x=>x[0]),injuries_location:'games',alt_props_tab:true,dynamic_root:true};
ensureRoot();window.render('games');
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
    print({'status':'PASS','tabs':13,'alt_props':True,'injuries_in_games':True,'standalone_injuries':False,'dynamic_root':True})


if __name__ == '__main__':
    main()
