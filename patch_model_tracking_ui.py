import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="model-tracking-ui-v2">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function pct(v){return typeof v==='number'?Math.round(v*1000)/10+'%':'—'}
  function rows(obj, limit=12){return Object.entries(obj||{}).slice(0,limit)}
  function card(title, items){return `<article class="stat-card track-card"><div class="stat-title">${title}</div>${items.map(([k,v])=>`<div class="stat-line"><span>${k}</span><span>${safe(v)}</span></div>`).join('')}</article>`}
  function table(title, obj, empty){
    const r=rows(obj,16);
    return `<div class="section-title">${title}</div><div class="tracking-table">${r.length?r.map(([k,v])=>`<article class="track-row"><div><div class="board-main">${k}</div><div class="board-sub">${safe(v.bets,0)} tracked bets</div></div><div><div class="board-label">Record</div><div class="board-value">${safe(v.record)}</div></div><div><div class="board-label">Win %</div><div class="board-value">${pct(v.win_pct)}</div></div><div><div class="board-label">ROI</div><div class="board-value ${Number(v.roi)>0?'good':Number(v.roi)<0?'bad':''}">${pct(v.roi)}</div></div><div><div class="board-label">CLV</div><div class="board-value ${Number(v.avg_clv)>0?'good':Number(v.avg_clv)<0?'bad':''}">${safe(v.avg_clv,0)}</div></div><div><div class="board-label">Avg EV</div><div class="board-value">${safe(v.avg_ev,0)}%</div></div></article>`).join(''):`<div class="empty">${empty}</div>`}</div>`
  }
  function health(h){
    h=h||{};
    const items=[['Odds',`${safe(h.odds)} · ${safe(h.odds_rows,0)} rows`],['Props',`${safe(h.props)} · ${safe(h.props_rows,0)} rows`],['Player Points',`${safe(h.player_points)} · ${safe(h.player_points_rows,0)} rows`],['Line Shop',`${safe(h.line_shopping)} · ${safe(h.line_shopping_rows,0)} rows`],['Injuries',`${safe(h.injuries)} · OUT ${safe(h.injury_out_count,0)} · Q ${safe(h.injury_questionable_count,0)}`]];
    return card('Model Health', items);
  }
  window.renderStats=function(){
    const t=DATA.model_tracking||DATA.tracking||{};
    const recent=(t.recent_10||[]).slice(-10).reverse().map(b=>`<article class="track-row recent"><div><div class="board-main">${safe(b.play||b.player||b.game)}</div><div class="board-sub">${safe(b.date||b.game_date)} · ${safe(b.game)} · ${safe(b.stat||b.type)}</div></div><div><div class="board-label">Result</div><div class="board-value ${b.result==='WIN'?'good':b.result==='LOSS'?'bad':'warn'}">${safe(b.result)}</div></div><div><div class="board-label">Book</div><div class="board-value">${safe(b.best_book||b.book)}</div></div><div><div class="board-label">EV</div><div class="board-value">${safe(b.ev_pct)}%</div></div><div><div class="board-label">CLV</div><div class="board-value">${safe(b.clv,0)}</div></div><div></div></article>`).join('')||'<div class="empty">No recent graded bets yet.</div>';
    const html=`
      <div class="section-title">Model Tracking</div>
      <section class="stats-grid tracking-grid">
        ${card('Overall',[['Record',t.overall||'0-0-0'],['Bets',safe(t.bets,0)],['Win %',pct(t.win_pct)],['ROI',pct(t.roi)],['Units',safe(t.profit_units,0)],['Avg CLV',safe(t.clv_avg,0)]])}
        ${card('Edge Quality',[['Avg EV',safe(t.avg_ev,0)+'%'],['Avg Edge',safe(t.avg_edge,0)],['CLV',safe(t.clv_avg,0)],['Last Update',safe((t.last_updated_utc||'').slice(0,16))]])}
        ${health(t.model_health||{})}
        ${card('Today Data',[['Games',(DATA.games||[]).length],['Best Bets',(DATA.best_bets||[]).length],['Props',(DATA.props||[]).length],['Line Rows',(DATA.line_shopping||[]).length]])}
      </section>
      ${table('Performance by Market',t.by_type,'No graded markets yet.')}
      ${table('Performance by Prop Type',t.by_stat,'No graded prop-type data yet.')}
      ${table('Confidence / Grade Performance',Object.assign({},t.by_conf||{},t.by_grade||{}),'No graded confidence data yet.')}
      ${table('Sportsbook Comparison',t.by_book,'No sportsbook tracking yet.')}
      ${table('Player Performance',t.by_player,'No player-level tracking yet.')}
      ${table('Team Performance',t.by_team,'No team-level tracking yet.')}
      <div class="section-title">Recent Graded Bets</div><div class="tracking-table">${recent}</div>`;
    const el=document.getElementById('tab-stats');if(el)el.innerHTML=html;
  };
})();
</script>
'''

CSS = r'''
<style id="model-tracking-ui-v2-css">
  .tracking-grid{grid-template-columns:repeat(4,1fr)}
  .track-card .stat-line span:last-child{font-weight:900;text-align:right}
  .tracking-table{display:flex;flex-direction:column;gap:9px}
  .track-row{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:14px;display:grid;grid-template-columns:1.4fr .7fr .7fr .7fr .7fr .7fr;gap:10px;align-items:center}
  .track-row.recent{grid-template-columns:1.6fr .6fr .8fr .6fr .6fr .2fr}
  @media(max-width:840px){.tracking-grid{grid-template-columns:1fr 1fr}.track-row,.track-row.recent{grid-template-columns:1fr 1fr}.track-row>div:first-child{grid-column:1/-1}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="model-tracking-ui-v2">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="model-tracking-ui-v2-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ model tracking UI patch applied')

if __name__=='__main__':
    main()
