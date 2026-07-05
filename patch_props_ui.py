import os
import re

HTML = 'docs/index.html'

PATCH = '''
<script id="props-ui-fix">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function fmt(v){try{return fmtTime(v)}catch(e){return v||'—'}}
  function state(name, fallback){return Object.prototype.hasOwnProperty.call(window,name)?window[name]:fallback}
  function key(g){return g.away.name+' @ '+g.home.name}
  function rowGame(p){
    if(p.game && String(p.game).includes(' @ ')) return String(p.game).trim();
    let raw=[p.game,p.opp,p.team,p.home_team,p.away_team].map(x=>String(x||'')).join(' ').toUpperCase().replace(/[^A-Z0-9]/g,'');
    for(let g of (DATA.games||[])){
      let vals=[g.away.name,g.home.name,g.away.abbr,g.home.abbr].map(x=>String(x||'').toUpperCase().replace(/[^A-Z0-9]/g,''));
      if((raw.includes(vals[0])||raw.includes(vals[2]))&&(raw.includes(vals[1])||raw.includes(vals[3]))) return key(g);
    }
    return p.game||p.opp||'UNKNOWN';
  }
  function pct(x){return typeof x==='number'?Math.round(x*100)+'%':'—'}
  function arr(v){if(Array.isArray(v))return v;if(!v)return[];try{let x=JSON.parse(v);return Array.isArray(x)?x:[]}catch(e){return[]}}
  function boxes(p){
    let vals=arr(p.last5_vals).slice(0,5),opps=arr(p.last5_opps).slice(0,5),line=Number(p.line),sig=p.signal;
    if(!vals.length)return'—';
    return '<div class="l5-wrap betsy">'+vals.map((v,i)=>{let hit=sig?(sig==='UNDER'?v<line:sig==='OVER'?v>line:sig==='YES'?v==1:v==0):null,cls=hit===null?'l5-neutral':hit?'l5-hit':'l5-miss';return `<div class="l5-box"><div class="l5-num ${cls}">${v}</div><div class="l5-opp">${safe(opps[i],'')}</div></div>`}).join('')+'</div>'
  }
  function rank(r){r=Number(r||8);return r<=5?'rank-tough':r<=10?'rank-mid':'rank-easy'}
  function statLine(p){return p.stat==='DD'||p.stat==='TD'?'YES':safe(p.best_line,p.line)}
  function projected(p){return p.stat==='DD'||p.stat==='TD'?Math.round((p.pred||0)*100)+'%':safe(p.pred)}
  function showOver(p){
    if(p.stat==='DD'||p.stat==='TD') return p.signal==='YES'?`YES ${safe(p.yes_price||p.best_odds||p.odds,'')}`:safe(p.yes_price,'—');
    let val=safe(p.over_price || (p.signal==='OVER'?p.best_odds:null),'—');
    return p.signal==='OVER'?`OVER ${val}`:val;
  }
  function showUnder(p){
    if(p.stat==='DD'||p.stat==='TD') return p.signal==='NO'?`NO ${safe(p.no_price||p.best_odds||p.odds,'')}`:safe(p.no_price,'—');
    let val=safe(p.under_price || (p.signal==='UNDER'?p.best_odds:null),'—');
    return p.signal==='UNDER'?`UNDER ${val}`:val;
  }
  function sortRows(rows, sortKey){
    if(sortKey==='OVER') rows=rows.filter(p=>p.signal==='OVER'||p.signal==='YES').sort((a,b)=>(b.ev||0)-(a.ev||0));
    else if(sortKey==='UNDER') rows=rows.filter(p=>p.signal==='UNDER'||p.signal==='NO').sort((a,b)=>(b.ev||0)-(a.ev||0));
    else if(sortKey==='PROJECTED') rows=rows.sort((a,b)=>(Number(b.pred)||0)-(Number(a.pred)||0));
    else if(sortKey==='L5') rows=rows.sort((a,b)=>(Number(b.last5_hit)||0)-(Number(a.last5_hit)||0));
    else rows=rows.sort((a,b)=>(b.conf==='HIGH')-(a.conf==='HIGH')||(b.conf==='MED')-(a.conf==='MED')||Math.abs(b.edge||0)-Math.abs(a.edge||0));
    return rows;
  }
  function draw(){
    let curGame=state('propsGame','ALL'),curStat=state('propsStat','ALL'),curSort=state('propsSort','EDGE');
    let props=(DATA.props||DATA.player_points||DATA.props_board||[]).filter(p=>p.line!==null&&p.line!==undefined&&p.line!==''&&p.market_status!=='NO MARKET'&&p.injury_status!=='OUT'&&p.injury_status!=='DOUBTFUL');
    let cards='<article class="props-game all '+(curGame==='ALL'?'active':'')+'" onclick="setPropsGame(\'ALL\')"><div class="game-time">ALL</div><div class="team-line">All Players</div></article>'+(DATA.games||[]).map(g=>{let k=key(g);return `<article class="props-game ${curGame===k?'active':''}" onclick="setPropsGame('${k.replace(/'/g,"\\'")}')"><div class="game-time">${fmt(g.tip)}</div><div class="team-line">${g.away.abbr} @ ${g.home.abbr}</div><div class="board-sub">${k}</div></article>`}).join('');
    let stats=['ALL','PTS','REB','AST','3PM','PRA','PA','PR','RA','DD','TD'];
    let labels={PA:'PTS+AST',PR:'PTS+REB',RA:'REB+AST',DD:'2X2',TD:'3X2'};
    let filters=stats.map(s=>`<button class="filter-btn ${curStat===s?'active':''}" onclick="setPropsStat('${s}')">${labels[s]||s}</button>`).join('');
    let sorts=[['EDGE','Best Edge'],['OVER','Over'],['UNDER','Under'],['PROJECTED','Projected'],['L5','Last 5 Hit']];
    let sortbar=sorts.map(([k,l])=>`<button class="filter-btn sort-btn ${curSort===k?'active':''}" onclick="setPropsSort('${k}')">${l}</button>`).join('');
    let rows=props.map(p=>Object.assign({},p,{_game:rowGame(p)})).filter(p=>(curGame==='ALL'||p._game===curGame)&&(curStat==='ALL'||String(p.stat).toUpperCase()===curStat));
    rows=sortRows(rows,curSort);
    let table=rows.length?`<div class="props-scroll"><div class="props-table props-table-v2"><div class="props-head"><div>Player</div><div>Stat</div><div>Line</div><div>Over / Yes</div><div>Under / No</div><div>Projected</div><div>Last 5</div><div>L5 Hit</div><div>L10 Hit</div><div>H2H L5</div><div>Opp Rank</div></div>${rows.map(p=>`<article class="prop-row ${p.conf||'LOW'}"><div><div class="player-name">${safe(p.player)}</div><div class="player-meta">${safe(p.best_book_title||p.best_book,'Best book —')} · ${safe(p.injury_status,'ACTIVE')} · ${safe(p._game)}</div></div><div><span class="stat-pill ${p.conf==='HIGH'?'high':''}">${safe(p.stat)}</span></div><div class="board-value">${statLine(p)}</div><div class="signal-over">${showOver(p)}</div><div class="signal-under">${showUnder(p)}</div><div class="${p.line?'proj-bright':'proj-dim'}">${projected(p)}</div><div>${boxes(p)}</div><div class="hit-cell ${p.signal==='OVER'||p.signal==='YES'?'signal-over':p.signal==='UNDER'||p.signal==='NO'?'signal-under':''}"><span class="hit-pct">${p.signal?pct(p.last5_hit):'—'}</span><span class="hit-sig">${p.signal||''}</span></div><div class="hit-cell ${p.signal==='OVER'||p.signal==='YES'?'signal-over':p.signal==='UNDER'||p.signal==='NO'?'signal-under':''}"><span class="hit-pct">${p.signal?pct(p.last10_hit):'—'}</span><span class="hit-sig">${p.signal||''}</span></div><div>${arr(p.h2h_last5).length?arr(p.h2h_last5).join(', '):'—'}</div><div class="${rank(p.opp_rank)}">${safe(p.opp_rank)}</div></article>`).join('')}</div></div>`:'<div class="empty">No sportsbook props for this selected game/stat filter. Try ALL or another stat.</div>';
    let el=document.getElementById('tab-props');if(el)el.innerHTML=`<div class="section-title">Today's Games</div><div class="props-games">${cards}</div><div class="section-title">Filters</div><div class="filter-bar">${filters}</div><div class="section-title sort-title">Sort Props</div><div class="filter-bar props-sort-bar">${sortbar}</div><div class="section-title">Props Table</div>${table}`;
  }
  window.setPropsGame=function(k){window.propsGame=k;draw()};
  window.setPropsStat=function(s){window.propsStat=s;draw()};
  window.setPropsSort=function(s){window.propsSort=s;draw()};
  window.renderProps=draw;
  try{renderProps=draw;setPropsGame=window.setPropsGame;setPropsStat=window.setPropsStat}catch(e){}
  const oldSwitch=window.switchTab;
  window.switchTab=function(name,btn){
    if(typeof oldSwitch==='function') oldSwitch(name,btn);
    if(name==='props') setTimeout(draw,0);
  };
  setTimeout(function(){
    const el=document.getElementById('tab-props');
    if(el && el.classList && el.classList.contains('active')) draw();
  },0);
})();
</script>
'''

CSS = '''
<style id="props-ui-fix-css">
  .filter-bar{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 18px}
  .props-sort-bar{background:rgba(96,165,250,.05);border:1px solid rgba(96,165,250,.12);border-radius:16px;padding:10px}
  .sort-title{color:#8ab4ff!important}
  .sort-btn{border-color:rgba(96,165,250,.25)!important}
  .props-table{min-width:1180px}
  .props-head,.prop-row{grid-template-columns: 240px 80px 95px 120px 120px 105px 240px 105px 105px 120px 85px!important;align-items:center}
  .prop-row{min-height:92px}
  .l5-wrap.betsy{display:flex!important;gap:7px!important;align-items:center!important}
  .l5-box{text-align:center!important;width:auto!important}.l5-num{min-width:34px!important;width:34px!important;height:34px!important;border-radius:7px!important;display:flex!important;align-items:center!important;justify-content:center!important;font-weight:900!important;font-size:13px!important}.l5-opp{font-size:10px!important;opacity:.65!important;margin-top:3px!important}
  .l5-hit{background:rgba(0,229,160,.22)!important;color:#00e5a0!important;border:1px solid rgba(0,229,160,.35)!important}
  .l5-miss{background:rgba(248,113,113,.20)!important;color:#f87171!important;border:1px solid rgba(248,113,113,.28)!important}
  .l5-neutral{background:rgba(148,163,184,.12)!important;color:#94a3b8!important;border:1px solid rgba(148,163,184,.18)!important}
  .hit-cell{font-weight:900!important;line-height:1.15!important;text-align:center!important;font-size:15px!important;text-transform:uppercase!important;display:flex!important;flex-direction:column!important;gap:3px!important;align-items:center!important;justify-content:center!important}
  .hit-pct{font-size:18px!important;letter-spacing:.5px!important}.hit-sig{font-size:12px!important;letter-spacing:1px!important}
  .signal-over{color:#4ade80!important}.signal-under{color:#f87171!important}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=html.replace('No props available — PrizePicks lines post closer to tip off','No sportsbook props for this selected game/stat filter. Try ALL or another stat.')
    html=html.replace('PrizePicks','sportsbook')
    html=re.sub(r'<script id="props-ui-fix">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="props-ui-fix-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ props UI patch applied')

if __name__=='__main__':
    main()
