import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="market-heatmap-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function cls(g){return String(g||'').toLowerCase()}
  function tile(x,type){return `<article class="mh-tile ${cls(x.grade)}"><div class="mh-top"><b>${safe(x.name)}</b><span>${safe(x.grade)}</span></div><div class="mh-score">${safe(x.opportunity_score)}</div><div class="mh-bars"><span style="width:${Math.min(100,Number(x.opportunity_score)||0)}%"></span></div><div class="mh-meta"><span>${safe(x.count,0)} props</span><span>${safe(x.avg_ev,0)}% EV</span><span>${safe(x.strong_count,0)} strong</span></div></article>`}
  function topRows(items){return (items||[]).slice(0,5).map(p=>`<article class="mh-row" onclick="openPlayerDetail&&openPlayerDetail('${String(p.player||'').replace(/'/g,"\\'")}','${String(p.stat||'').replace(/'/g,"\\'")}')"><div><b>${safe(p.player)} ${safe(p.stat)}</b><span>${safe(p.game)} · ${safe(p.best_book_title||p.best_book)}</span></div><strong>${safe(p.ev_pct)}%</strong></article>`).join('')||'<div class="empty mini">No top props yet.</div>'}
  function render(){
    const h=DATA.market_heatmap||{}; if(!h.summary)return;
    const markets=(h.ranked_markets||[]).slice(0,10);
    const books=(h.ranked_books||[]).slice(0,6);
    const games=(h.ranked_games||[]).slice(0,6);
    const best=markets[0]||{};
    const html=`<section id="market-heatmap-block"><div class="section-title">Market Heat Map</div><div class="mh-hero"><div><h2>Best Market: ${safe(h.summary.best_market)}</h2><p>Quick view of where today's strongest edges are clustering.</p></div><div class="mh-hero-score"><span>Opportunity</span><b>${safe(best.opportunity_score)}</b></div></div><div class="mh-grid">${markets.map(tile).join('')}</div><div class="mh-split"><article class="mh-panel"><h3>Best Sportsbooks</h3>${books.map(x=>tile(x,'book')).join('')}</article><article class="mh-panel"><h3>Best Games</h3>${games.map(x=>tile(x,'game')).join('')}</article><article class="mh-panel wide"><h3>Top Props From Best Market</h3>${topRows(best.top)}</article></div></section>`;
    const el=document.getElementById('tab-games'); if(el && !document.getElementById('market-heatmap-block')){const w=document.createElement('div');w.innerHTML=html;el.appendChild(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,800);
})();
</script>
'''

CSS = r'''
<style id="market-heatmap-ui-v1-css">
.mh-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(251,146,60,.12),rgba(96,165,250,.08));border:1px solid rgba(251,146,60,.18);border-radius:22px;padding:17px;margin-bottom:12px}.mh-hero h2{margin:0 0 5px}.mh-hero p{margin:0;color:#8b95a8}.mh-hero-score{text-align:right}.mh-hero-score span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.mh-hero-score b{font-size:34px;color:#fb923c}.mh-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:14px}.mh-tile{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:16px;padding:12px}.mh-tile.hot{border-color:rgba(0,229,160,.35);box-shadow:inset 0 0 0 1px rgba(0,229,160,.12)}.mh-tile.warm{border-color:rgba(245,197,24,.28)}.mh-tile.cold{opacity:.7}.mh-top{display:flex;justify-content:space-between;gap:8px;align-items:center}.mh-top b{font-size:14px}.mh-top span{font-size:9px;color:#64748b;text-transform:uppercase}.mh-score{font-size:28px;font-weight:900;margin:8px 0;color:#eaf2ff}.mh-bars{height:7px;background:#ffffff10;border-radius:999px;overflow:hidden}.mh-bars span{display:block;height:100%;background:linear-gradient(90deg,#60a5fa,#00e5a0);border-radius:999px}.mh-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}.mh-meta span{font-size:10px;color:#7b879b}.mh-split{display:grid;grid-template-columns:1fr 1fr;gap:12px}.mh-panel{background:#0d1220;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:14px}.mh-panel h3{margin:0 0 10px}.mh-panel .mh-tile{margin-bottom:8px}.mh-panel.wide{grid-column:1/-1}.mh-row{display:flex;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.06);cursor:pointer}.mh-row b{display:block}.mh-row span{display:block;color:#7b879b;font-size:11px;margin-top:3px}.mh-row strong{font-size:20px;color:#00e5a0}@media(max-width:900px){.mh-grid{grid-template-columns:1fr 1fr}.mh-split{grid-template-columns:1fr}.mh-hero{flex-direction:column;align-items:flex-start}.mh-hero-score{text-align:left}}@media(max-width:480px){.mh-grid{grid-template-columns:1fr}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="market-heatmap-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="market-heatmap-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ market heat map UI patch applied')

if __name__=='__main__':
    main()
