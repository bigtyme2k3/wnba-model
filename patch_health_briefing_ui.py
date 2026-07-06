import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="health-briefing-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function cls(s){return s==='ok'?'ok':s==='partial'?'warn':s==='warn'?'bad':'idle'}
  function ago(m){return m===null||m===undefined?'—':m<1?'just now':Math.round(m)+'m ago'}
  function healthCard(src){return `<article class="health-card ${cls(src.status)}"><div class="health-dot"></div><div><b>${safe(src.name)}</b><span>${safe(src.note)}</span></div><div class="health-meta"><strong>${safe(src.rows,0)}</strong><small>${ago(src.age_minutes)}</small></div></article>`}
  function briefItem(text){return `<li>${safe(text)}</li>`}
  function betMini(b){return `<article class="brief-bet"><div><b>${safe(b.play||b.player||b.game)}</b><span>${safe(b.game)} · ${safe(b.best_book_title||b.best_book)}</span></div><strong>${safe(b.ev_pct)}%</strong></article>`}
  window.renderHealthBriefing=function(){
    const health=DATA.dashboard_health||{};
    const brief=DATA.daily_briefing||{};
    const srcs=health.sources||[];
    const counts=health.counts||{};
    const top=(brief.top_ev||[]).slice(0,2).map(betMini).join('')||'<div class="note">No top EV plays yet.</div>';
    const block=`<section id="daily-briefing-block" class="brief-wrap"><div class="brief-head"><div><div class="section-title">Daily AI Brief</div><h2>${safe(brief.headline,'Daily AI Brief')}</h2><p>${safe(brief.summary,'Slate summary and model health.')}</p></div><div class="brief-status ${cls(brief.health_status||health.overall_status)}">${safe(brief.health_status||health.overall_status,'ok')}</div></div><div class="brief-grid"><article class="brief-panel"><h3>Morning Report</h3><ul>${(brief.bullets||[]).map(briefItem).join('')||'<li>No briefing generated yet.</li>'}</ul></article><article class="brief-panel"><h3>Top EV Watch</h3>${top}</article><article class="brief-panel"><h3>Slate Counts</h3><div class="count-grid"><div><b>${safe(counts.games,0)}</b><span>Games</span></div><div><b>${safe(counts.props,0)}</b><span>Props</span></div><div><b>${safe(counts.best_bets,0)}</b><span>Best Bets</span></div><div><b>${safe(counts.slips,0)}</b><span>Slips</span></div></div></article></div><div class="section-title">Dashboard Health</div><div class="health-grid">${srcs.map(healthCard).join('')||'<div class="empty">No health data generated yet.</div>'}</div></section>`;
    const el=document.getElementById('tab-games');
    if(el && !document.getElementById('daily-briefing-block')){
      const wrap=document.createElement('div');wrap.innerHTML=block;el.prepend(wrap.firstElementChild);
    }
  };
  function searchRows(q){
    q=String(q||'').trim().toLowerCase();
    if(!q)return [];
    const props=(DATA.props||[]).map(p=>({type:'Prop',title:`${p.player} ${p.stat} ${p.signal||''}`,sub:`${p.game||''} · ${p.best_book_title||p.best_book||''}`,action:`openPlayerDetail('${String(p.player||'').replace(/'/g,"\\'")}','${String(p.stat||'').replace(/'/g,"\\'")}')`}));
    const bets=(DATA.best_bets||[]).map(b=>({type:'Best Bet',title:b.play||b.player||b.game,sub:`${b.game||''} · EV ${b.ev_pct||'—'}%`,action:null}));
    const alerts=(DATA.live_alerts||[]).map(a=>({type:'Alert',title:a.title||a.message||a.type,sub:a.detail||a.game||'',action:null}));
    return props.concat(bets,alerts).filter(x=>(x.title+' '+x.sub+' '+x.type).toLowerCase().includes(q)).slice(0,20);
  }
  window.runUniversalSearch=function(q){
    const box=document.getElementById('universal-search-results'); if(!box)return;
    const results=searchRows(q);
    box.innerHTML=results.length?results.map(r=>`<article class="search-result" ${r.action?`onclick="${r.action}"`:''}><span>${r.type}</span><b>${safe(r.title)}</b><small>${safe(r.sub)}</small></article>`).join(''):'<div class="note">Search players, teams, props, alerts, EV, unders, overs.</div>';
  };
  window.toggleUniversalSearch=function(){const p=document.getElementById('universal-search-panel'); if(p)p.classList.toggle('open')};
  function mountSearch(){
    if(document.getElementById('universal-search-panel'))return;
    const panel=document.createElement('div'); panel.id='universal-search-panel'; panel.innerHTML=`<button class="search-fab" onclick="toggleUniversalSearch()">⌕</button><div class="search-drawer"><div class="search-row"><input placeholder="Search players, teams, high EV, unders..." oninput="runUniversalSearch(this.value)" autofocus><button onclick="toggleUniversalSearch()">×</button></div><div id="universal-search-results" class="search-results"><div class="note">Search players, markets, alerts, and best bets.</div></div></div>`; document.body.appendChild(panel);
  }
  const oldSwitch=window.switchTab;
  window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(window.renderHealthBriefing,0)};
  setTimeout(function(){mountSearch();window.renderHealthBriefing()},600);
})();
</script>
'''

CSS = r'''
<style id="health-briefing-ui-v1-css">
.brief-wrap{margin:0 0 22px}.brief-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;background:linear-gradient(135deg,rgba(96,165,250,.12),rgba(0,229,160,.05));border:1px solid rgba(96,165,250,.18);border-radius:24px;padding:18px;margin-bottom:12px}.brief-head h2{margin:4px 0 6px;font-size:28px}.brief-head p{margin:0;color:#8b95a8}.brief-status{border-radius:999px;padding:8px 12px;text-transform:uppercase;font-weight:900;letter-spacing:1px}.brief-status.ok{background:rgba(0,229,160,.14);color:#00e5a0}.brief-status.warn{background:rgba(245,197,24,.14);color:#f5c518}.brief-status.bad{background:rgba(248,113,113,.14);color:#f87171}.brief-grid{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:12px;margin-bottom:18px}.brief-panel{background:#0d1220;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.brief-panel h3{margin:0 0 10px}.brief-panel ul{margin:0;padding-left:20px;color:#cbd5e1;line-height:1.55}.brief-bet{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.06)}.brief-bet b{display:block}.brief-bet span{display:block;color:#7b879b;font-size:11px}.brief-bet strong{color:#00e5a0;font-size:20px}.count-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.count-grid div{background:#080b13;border-radius:14px;padding:12px}.count-grid b{font-size:24px;display:block}.count-grid span{font-size:10px;color:#7b879b;text-transform:uppercase}.health-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.health-card{position:relative;display:grid;grid-template-columns:12px 1fr auto;gap:10px;align-items:center;background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:16px;padding:12px}.health-dot{width:10px;height:10px;border-radius:50%;background:#64748b}.health-card.ok .health-dot{background:#00e5a0;box-shadow:0 0 14px rgba(0,229,160,.5)}.health-card.warn .health-dot{background:#f5c518}.health-card.bad .health-dot{background:#f87171}.health-card b{display:block}.health-card span{display:block;color:#7b879b;font-size:11px;margin-top:3px}.health-meta{text-align:right}.health-meta strong{display:block}.health-meta small{display:block;color:#64748b}.search-fab{position:fixed;right:18px;bottom:22px;z-index:9998;width:52px;height:52px;border-radius:18px;border:1px solid rgba(96,165,250,.3);background:#14213d;color:#e2e8f0;font-size:26px;box-shadow:0 12px 40px #0008}.search-drawer{position:fixed;right:18px;bottom:86px;width:min(460px,calc(100vw - 32px));max-height:65vh;overflow:auto;background:#080b13;border:1px solid rgba(255,255,255,.12);border-radius:22px;box-shadow:0 22px 70px #000;z-index:9998;padding:12px;display:none}#universal-search-panel.open .search-drawer{display:block}.search-row{display:flex;gap:8px}.search-row input{flex:1;background:#0d1220;color:#e2e8f0;border:1px solid rgba(255,255,255,.1);border-radius:14px;padding:12px}.search-row button{background:#111827;color:#e2e8f0;border:1px solid rgba(255,255,255,.1);border-radius:14px;width:42px}.search-results{display:flex;flex-direction:column;gap:8px;margin-top:10px}.search-result{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:14px;padding:10px;cursor:pointer}.search-result span{color:#60a5fa;font-size:10px;text-transform:uppercase;letter-spacing:1px}.search-result b{display:block;margin:4px 0}.search-result small{display:block;color:#7b879b}@media(max-width:840px){.brief-grid,.health-grid{grid-template-columns:1fr}.brief-head{flex-direction:column}.brief-head h2{font-size:23px}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="health-briefing-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="health-briefing-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ health briefing UI patch applied')

if __name__=='__main__':
    main()
