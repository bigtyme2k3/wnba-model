import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="game-command-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function pct(v){let n=Number(v);return isNaN(n)?'—':n+'%'}
  function cardMetric(k,v,s=''){return `<article class="gcc-metric"><span>${k}</span><b>${safe(v)}</b>${s?`<small>${s}</small>`:''}</article>`}
  function propRow(p){return `<article class="gcc-mini-row" onclick="openPlayerDetail&&openPlayerDetail('${String(p.player||'').replace(/'/g,"\\'")}','${String(p.stat||'').replace(/'/g,"\\'")}')"><div><b>${safe(p.player)} ${safe(p.stat)}</b><span>${safe(p.signal)} · ${safe(p.best_book_title||p.best_book)}</span></div><strong>${safe(p.confidence_v2||p.score)}<small>/100</small></strong></article>`}
  function betRow(b){return `<article class="gcc-mini-row"><div><b>${safe(b.play||b.player)}</b><span>${safe(b.best_book_title||b.best_book)} · EV ${safe(b.ev_pct)}%</span></div><strong>${safe(b.score)}<small>/100</small></strong></article>`}
  function corrRow(c){return `<article class="gcc-corr"><b>${safe(c.a)}</b><span>${safe(c.b)}</span><strong>${safe(c.correlation)}</strong></article>`}
  function openCenter(game){
    const modal=document.createElement('div');modal.className='gcc-modal';
    const props=(game.top_props||[]).map(propRow).join('')||'<div class="empty mini">No ranked props for this game.</div>';
    const bets=(game.top_bets||[]).map(betRow).join('')||'<div class="empty mini">No best bets for this game.</div>';
    const corr=(game.correlations||[]).map(corrRow).join('')||'<div class="empty mini">No same-game correlations yet.</div>';
    const slips=(game.related_slips||[]).map(s=>`<article class="gcc-slip"><b>${safe(s.label)}</b><span>${safe(s.legs)} legs · ${safe(s.ev_pct)}% EV · ${safe(s.combined_american)}</span></article>`).join('')||'<div class="empty mini">No optimized slips for this game yet.</div>';
    modal.innerHTML=`<div class="gcc-back" onclick="this.closest('.gcc-modal').remove()"></div><section class="gcc-panel"><button class="gcc-close" onclick="this.closest('.gcc-modal').remove()">×</button><header class="gcc-head"><div><div class="gcc-kicker">Game Command Center</div><h2>${safe(game.game)}</h2><p>${safe(game.matchup_note)}</p></div><div class="gcc-score"><span>Command</span><b>${safe(game.command_score)}</b></div></header><section class="gcc-grid">${cardMetric('Home Win',pct(game.win_probability_home),game.home)}${cardMetric('Away Win',pct(game.win_probability_away),game.away)}${cardMetric('Projected',`${safe(game.projected_score?.away)} - ${safe(game.projected_score?.home)}`)}${cardMetric('Pace',game.pace,game.pace_label)}${cardMetric('Total',game.vegas_total)}${cardMetric('Home Spread',game.home_spread)}${cardMetric('Props',game.market_summary?.props)}${cardMetric('Avg EV',safe(game.market_summary?.avg_ev)+'%')}</section><section class="gcc-sections"><article class="gcc-card"><h3>Top Props</h3>${props}</article><article class="gcc-card"><h3>Best Bets</h3>${bets}</article><article class="gcc-card"><h3>Same-Game Correlations</h3>${corr}</article><article class="gcc-card"><h3>Optimized Slips</h3>${slips}</article></section></section>`;
    document.body.appendChild(modal);
  }
  window.openGameCommandCenter=function(gameKey){const g=(DATA.game_command_center||[]).find(x=>x.game===gameKey); if(g)openCenter(g)};
  function render(){
    const games=DATA.game_command_center||[]; if(!games.length)return;
    const block=`<section id="game-command-block"><div class="section-title">Game Command Center</div><div class="gcc-list">${games.map(g=>`<article class="gcc-game" onclick="openGameCommandCenter('${String(g.game).replace(/'/g,"\\'")}')"><div><b>${safe(g.game)}</b><span>${safe(g.pace_label)} pace · ${safe(g.market_summary?.props)} props · ${safe(g.market_summary?.best_bets)} best bets</span></div><div class="gcc-game-score"><strong>${safe(g.command_score)}</strong><small>command</small></div></article>`).join('')}</div></section>`;
    const el=document.getElementById('tab-games'); if(el && !document.getElementById('game-command-block')){const w=document.createElement('div');w.innerHTML=block;el.appendChild(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,700);
})();
</script>
'''

CSS = r'''
<style id="game-command-ui-v1-css">
.gcc-list{display:flex;flex-direction:column;gap:10px;margin-bottom:20px}.gcc-game{display:flex;justify-content:space-between;gap:14px;align-items:center;background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:14px;cursor:pointer}.gcc-game:hover{border-color:rgba(96,165,250,.35);background:#111827}.gcc-game b{display:block;font-size:16px}.gcc-game span{display:block;color:#7b879b;font-size:12px;margin-top:4px}.gcc-game-score{text-align:right}.gcc-game-score strong{display:block;font-size:24px;color:#00e5a0}.gcc-game-score small{font-size:10px;color:#64748b;text-transform:uppercase}.gcc-modal{position:fixed;inset:0;z-index:9999}.gcc-back{position:absolute;inset:0;background:rgba(0,0,0,.74);backdrop-filter:blur(6px)}.gcc-panel{position:absolute;right:0;top:0;height:100%;width:min(900px,96vw);overflow:auto;background:#080b13;border-left:1px solid rgba(255,255,255,.1);box-shadow:-22px 0 70px #000;padding:22px}.gcc-close{float:right;position:sticky;top:0;width:38px;height:38px;border-radius:12px;background:#111827;color:#e2e8f0;border:1px solid rgba(255,255,255,.12);font-size:24px}.gcc-head{display:flex;justify-content:space-between;gap:14px;margin:12px 0 18px}.gcc-kicker{color:#60a5fa;font-size:11px;text-transform:uppercase;letter-spacing:1.5px;font-weight:900}.gcc-head h2{margin:5px 0;font-size:30px}.gcc-head p{margin:0;color:#7b879b}.gcc-score{text-align:right}.gcc-score span{display:block;color:#7b879b;font-size:11px;text-transform:uppercase}.gcc-score b{font-size:36px;color:#00e5a0}.gcc-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.gcc-metric{background:#0d1220;border:1px solid rgba(255,255,255,.07);border-radius:16px;padding:12px}.gcc-metric span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.gcc-metric b{display:block;font-size:22px;margin-top:5px}.gcc-metric small{display:block;color:#7b879b;font-size:11px;margin-top:3px}.gcc-sections{display:grid;grid-template-columns:1fr 1fr;gap:12px}.gcc-card{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.gcc-card h3{margin:0 0 12px}.gcc-mini-row{display:flex;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.06);cursor:pointer}.gcc-mini-row b{display:block}.gcc-mini-row span{display:block;color:#7b879b;font-size:11px;margin-top:3px}.gcc-mini-row strong{color:#00e5a0;font-size:20px}.gcc-mini-row small{font-size:10px;color:#64748b}.gcc-corr,.gcc-slip{display:grid;grid-template-columns:1fr 1fr 60px;gap:8px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.06)}.gcc-corr span,.gcc-slip span{color:#7b879b;font-size:11px}.gcc-corr strong{color:#f5c518;text-align:right}.gcc-slip{display:block}.empty.mini{font-size:12px;color:#7b879b;padding:10px}@media(max-width:840px){.gcc-grid,.gcc-sections{grid-template-columns:1fr 1fr}.gcc-head{flex-direction:column}.gcc-score{text-align:left}}@media(max-width:520px){.gcc-grid,.gcc-sections{grid-template-columns:1fr}.gcc-panel{width:100vw}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="game-command-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="game-command-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ game command UI patch applied')

if __name__=='__main__':
    main()
