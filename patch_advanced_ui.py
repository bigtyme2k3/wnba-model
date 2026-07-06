import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="advanced-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function metric(label,value,sub=''){return `<article class="adv-metric"><span>${label}</span><b>${safe(value)}</b>${sub?`<small>${sub}</small>`:''}</article>`}
  function matchupCard(m){return `<article class="match-card"><div><div class="board-main">${safe(m.game)}</div><div class="board-sub">${safe(m.matchup_note)}</div></div><div class="match-grid">${metric('Pace',m.pace,m.pace_label)}${metric('Total',m.total)}${metric('Reb Edge',m.rebound_edge)}${metric('Assist Env',m.assist_environment)}${metric('3PM Env',m.three_point_environment)}${metric('Home Spread',m.spread_home)}</div></article>`}
  function corrRow(c){let cls=Number(c.correlation)>0?'good':'bad';return `<article class="corr-row"><div><div class="board-main">${safe(c.a)}</div><div class="board-sub">${safe(c.game)}</div></div><div><div class="board-main">${safe(c.b)}</div><div class="board-sub">${safe(c.label)}</div></div><div class="corr-score ${cls}">${safe(c.correlation)}</div></article>`}
  window.renderGamesAdvanced=function(){
    const match=(DATA.team_matchups||[]).map(matchupCard).join('')||'<div class="empty">No matchup context yet.</div>';
    const corr=(DATA.correlations||[]).slice(0,10).map(corrRow).join('')||'<div class="empty">No correlations detected yet.</div>';
    const health=DATA.advanced_upgrades||{};
    const box=`<div class="section-title">Advanced Model Context</div><section class="adv-health">${metric('Props Upgraded',health.props_upgraded)}${metric('Injuries Loaded',health.injuries_loaded)}${metric('Live Players',health.live_players_loaded)}${metric('Correlations',health.correlations)}</section><div class="section-title">Team Matchup Dashboard</div><div class="match-list">${match}</div><div class="section-title">Correlation Engine</div><div class="corr-list">${corr}</div>`;
    const el=document.getElementById('tab-games');
    if(el && !document.getElementById('advanced-context-block')){
      const wrap=document.createElement('div');wrap.id='advanced-context-block';wrap.innerHTML=box;el.appendChild(wrap);
    }
  };
  const oldSwitch=window.switchTab;
  window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(window.renderGamesAdvanced,0)};
  setTimeout(window.renderGamesAdvanced,500);
})();
</script>
'''

CSS = r'''
<style id="advanced-ui-v1-css">
.adv-health{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}.adv-metric{background:#0d1220;border:1px solid rgba(255,255,255,.07);border-radius:14px;padding:12px}.adv-metric span{display:block;font-size:10px;letter-spacing:1px;text-transform:uppercase;color:#64748b}.adv-metric b{display:block;font-size:21px;margin-top:4px}.adv-metric small{display:block;color:#7b879b;font-size:11px;margin-top:4px}.match-list,.corr-list{display:flex;flex-direction:column;gap:10px}.match-card,.corr-row{background:var(--panel);border:1px solid var(--border);border-radius:18px;padding:14px}.match-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:12px}.corr-row{display:grid;grid-template-columns:1fr 1fr 80px;gap:12px;align-items:center}.corr-score{font-size:22px;font-weight:900;text-align:right}.good{color:#00e5a0!important}.bad{color:#f87171!important}@media(max-width:840px){.adv-health{grid-template-columns:1fr 1fr}.match-grid{grid-template-columns:1fr 1fr}.corr-row{grid-template-columns:1fr}.corr-score{text-align:left}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="advanced-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="advanced-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ advanced UI patch applied')

if __name__=='__main__':
    main()
