import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="wnba-context-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function esc(s){return String(s||'').replace(/'/g,"\\'")}
  function ctxRow(p,cls=''){
    const notes=(p.notes||[]).slice(0,2).join(' · ');
    return `<article class="wc-row ${cls}" onclick="openPlayerDetail&&openPlayerDetail('${esc(p.player)}','${esc(p.stat)}')"><div><b>${safe(p.player)} ${safe(p.stat)} ${safe(p.signal)}</b><span>${safe(p.game)} · Min ${safe(p.minutes?.projected)} · Usage ${safe(p.usage?.projected_usage)} · Matchup ${safe(p.matchup?.grade)}</span><em>${notes||'No major context notes.'}</em></div><strong>${safe(p.context_score)}<small>${safe(p.context_grade)}</small></strong></article>`
  }
  function statRow(x){return `<article class="wc-stat"><b>${safe(x.stat)}</b><span>${safe(x.count)} props</span><strong>${safe(x.avg_context_score)}</strong></article>`}
  function render(){
    const wc=DATA.wnba_context_engine||{}; if(!wc.summary)return;
    const s=wc.summary||{};
    const block=`<section id="wnba-context-block"><div class="section-title">WNBA Context Engine</div><div class="wc-hero"><div><h2>Today's Circumstance Score</h2><p>Scores every prop by minutes, usage, pace, matchup, rest, blowout risk, and injury context before trusting the projection.</p></div><div class="wc-big"><span>Avg Context</span><b>${safe(s.avg_context_score)}</b></div></div><div class="wc-metrics"><article><span>Props Scored</span><b>${safe(s.props_scored,0)}</b></article><article><span>High Context</span><b>${safe(s.high_context_count,0)}</b></article><article><span>Low Context</span><b>${safe(s.low_context_count,0)}</b></article></div><div class="wc-grid"><section class="wc-panel"><h3>Best Context Plays</h3>${(wc.top_context||[]).slice(0,6).map(p=>ctxRow(p,'good')).join('')||'<div class="empty">No context scores yet.</div>'}</section><section class="wc-panel"><h3>Context Risk Watch</h3>${(wc.weak_context||[]).slice(0,6).map(p=>ctxRow(p,'risk')).join('')||'<div class="empty">No weak-context plays flagged.</div>'}</section><section class="wc-panel"><h3>Stat Context</h3><div class="wc-stat-grid">${(wc.stat_context||[]).map(statRow).join('')||'<div class="empty">No stat context.</div>'}</div></section><section class="wc-panel"><h3>Game Context</h3><div class="wc-stat-grid">${(wc.game_context||[]).slice(0,8).map(x=>`<article class="wc-stat"><b>${safe(x.game)}</b><span>${safe(x.count)} props</span><strong>${safe(x.avg_context_score)}</strong></article>`).join('')||'<div class="empty">No game context.</div>'}</div></section></div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('wnba-context-block')){const w=document.createElement('div');w.innerHTML=block;el.appendChild(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1350);
})();
</script>
'''

CSS = r'''
<style id="wnba-context-ui-v1-css">
.wc-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(20,184,166,.13),rgba(96,165,250,.08));border:1px solid rgba(20,184,166,.2);border-radius:24px;padding:18px;margin-bottom:12px}.wc-hero h2{margin:0 0 6px;font-size:28px}.wc-hero p{margin:0;color:#9aa4b2;line-height:1.45}.wc-big{text-align:right}.wc-big span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.wc-big b{font-size:38px;color:#14f1c9}.wc-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}.wc-metrics article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:12px}.wc-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.wc-metrics b{display:block;font-size:22px;margin-top:5px}.wc-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}.wc-panel{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.wc-panel h3{margin:0 0 10px}.wc-row{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid rgba(255,255,255,.06);padding:10px 0;cursor:pointer}.wc-row b,.wc-row span,.wc-row em{display:block}.wc-row span{font-size:11px;color:#7b879b;margin-top:3px}.wc-row em{font-style:normal;color:#94a3b8;font-size:11px;margin-top:5px}.wc-row strong{font-size:26px;color:#14f1c9;text-align:right}.wc-row.risk strong{color:#f87171}.wc-row strong small{display:block;font-size:10px;color:#94a3b8}.wc-stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.wc-stat{background:#080b13;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:10px}.wc-stat b,.wc-stat span,.wc-stat strong{display:block}.wc-stat span{color:#7b879b;font-size:11px}.wc-stat strong{font-size:22px;color:#14f1c9;margin-top:5px}@media(max-width:900px){.wc-grid{grid-template-columns:1fr}.wc-hero{flex-direction:column;align-items:flex-start}.wc-big{text-align:left}}@media(max-width:520px){.wc-metrics,.wc-stat-grid{grid-template-columns:1fr}.wc-hero h2{font-size:23px}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="wnba-context-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="wnba-context-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('wnba context UI patch applied')

if __name__=='__main__':
    main()
