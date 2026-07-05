import os
import re

HTML = 'docs/index.html'

PATCH = '''
<script id="props-ui-fix">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function fmt(v){try{return fmtTime(v)}catch(e){return v||'—'}}
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
  function boxes(p){let vals=arr(p.last5_vals).slice(0,5),opps=arr(p.last5_opps).slice(0,5),line=Number(p.line),sig=p.signal;if(!vals.length)return'—';return '<div class="l5-wrap">'+vals.map((v,i)=>{let hit=sig?(sig==='UNDER'?v<line:v>line):null,cls=hit===null?'l5-neutral':hit?'l5-hit':'l5-miss';return `<div class="l5-box"><div class="l5-num ${cls}">${v}</div><div class="l5-opp">${safe(opps[i],'')}</div></div>`}).join('')+'</div>'}
  function rank(r){r=Number(r||8);return r<=5?'rank-tough':r<=10?'rank-mid':'rank-easy'}
  function draw(){
    let curGame=window.propsGame||propsGame||'ALL',curStat=window.propsStat||propsStat||'ALL';
    let props=(DATA.props||DATA.player_points||DATA.props_board||[]).filter(p=>p.line!==null&&p.line!==undefined&&p.line!==''&&p.market_status!=='NO MARKET'&&p.injury_status!=='OUT'&&p.injury_status!=='DOUBTFUL');
    let cards='<article class="props-game all '+(curGame==='ALL'?'active':'')+'" onclick="setPropsGame(\'ALL\')"><div class="game-time">ALL</div><div class="team-line">All Players</div></article>'+(DATA.games||[]).map(g=>{let k=key(g);return `<article class="props-game ${curGame===k?'active':''}" onclick="setPropsGame('${k.replace(/'/g,"\\'")}')"><div class="game-time">${fmt(g.tip)}</div><div class="team-line">${g.away.abbr} @ ${g.home.abbr}</div><div class="board-sub">${k}</div></article>`}).join('');
    let stats=['ALL','PTS','REB','AST','3PM','PRA'];
    let filters=stats.map(s=>`<button class="filter-btn ${curStat===s?'active':''}" onclick="setPropsStat('${s}')">${s}</button>`).join('');
    let rows=props.map(p=>Object.assign({},p,{_game:rowGame(p)})).filter(p=>(curGame==='ALL'||p._game===curGame)&&(curStat==='ALL'||String(p.stat).toUpperCase()===curStat));
    rows.sort((a,b)=>(b.conf==='HIGH')-(a.conf==='HIGH')||(b.conf==='MED')-(a.conf==='MED')||Math.abs(b.edge||0)-Math.abs(a.edge||0));
    let table=rows.length?`<div class="props-scroll"><div class="props-table"><div class="props-head"><div>Player</div><div>Stat</div><div>Best Line</div><div>Over</div><div>Under</div><div>Projected</div><div>Last 5</div><div>L5 Hit</div><div>L10 Hit</div><div>H2H L5</div><div>Opp Rank</div></div>${rows.map(p=>`<article class="prop-row ${p.conf||'LOW'}"><div><div class="player-name">${safe(p.player)}</div><div class="player-meta">${safe(p.best_book_title||p.best_book,'Best book —')} · ${safe(p.injury_status,'ACTIVE')} · ${safe(p._game)}</div></div><div><span class="stat-pill ${p.conf==='HIGH'?'high':''}">${safe(p.stat)}</span></div><div class="board-value">${safe(p.best_line,p.line)} @ ${safe(p.best_odds,p.odds)}</div><div class="signal-over">${p.signal==='OVER'?'OVER':'—'}</div><div class="signal-under">${p.signal==='UNDER'?'UNDER':'—'}</div><div class="${p.line?'proj-bright':'proj-dim'}">${safe(p.pred)}</div><div>${boxes(p)}</div><div>${p.signal?pct(p.last5_hit)+' '+p.signal:'—'}</div><div>${p.signal?pct(p.last10_hit)+' '+p.signal:'—'}</div><div>${arr(p.h2h_last5).length?arr(p.h2h_last5).join(', '):'—'}</div><div class="${rank(p.opp_rank)}">${safe(p.opp_rank)}</div></article>`).join('')}</div></div>`:'<div class="empty">No sportsbook props for this selected game/stat filter. Try ALL or another stat.</div>';
    let el=document.getElementById('tab-props');if(el)el.innerHTML=`<div class="section-title">Today's Games</div><div class="props-games">${cards}</div><div class="section-title">Filters</div><div class="filter-bar">${filters}</div><div class="section-title">Props Table</div>${table}`;
  }
  window.setPropsGame=function(k){window.propsGame=k;try{propsGame=k}catch(e){} draw()};
  window.setPropsStat=function(s){window.propsStat=s;try{propsStat=s}catch(e){} draw()};
  window.renderProps=draw;
  try{renderProps=draw;setPropsGame=window.setPropsGame;setPropsStat=window.setPropsStat}catch(e){}
})();
</script>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=html.replace('No props available — PrizePicks lines post closer to tip off','No sportsbook props for this selected game/stat filter. Try ALL or another stat.')
    html=html.replace('PrizePicks','sportsbook')
    html=re.sub(r'<script id="props-ui-fix">.*?</script>','',html,flags=re.S)
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ props UI patch applied')

if __name__=='__main__':
    main()
