import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="autonomous-intelligence-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function esc(s){return String(s||'').replace(/'/g,"\\'")}
  function row(p){return `<article class="ai-core-row" onclick="openPlayerDetail&&openPlayerDetail('${esc(p.player)}','${esc(p.stat)}')"><div><b>${safe(p.player)} ${safe(p.stat)} ${safe(p.signal)}</b><span>${safe(p.game)} · ${safe(p.best_book)} · ${safe(p.engines_agree)}/${safe(p.engines_total)} engines</span></div><strong>${safe(p.consensus_score)}<small>${safe(p.recommendation)}</small></strong></article>`}
  function render(){
    const ai=DATA.autonomous_intelligence||{}; if(!ai.summary)return;
    const s=ai.summary||{};
    const report=(ai.agent_report||[]).map(x=>`<li>${x}</li>`).join('')||'<li>No autonomous report yet.</li>';
    const strategies=(ai.strategy_discovery||[]).slice(0,6).map(x=>`<article class="ai-model"><div><b>${safe(x.name)} ${safe(x.direction)}</b><span>${safe(x.matches)} matches · ${safe(x.avg_ev)}% avg EV</span></div><strong>${safe(x.discovery_score)}</strong></article>`).join('')||'<div class="empty">No strategy clusters yet.</div>';
    const models=(ai.model_rankings||[]).slice(0,6).map(x=>`<article class="ai-model"><div><b>${safe(x.engine)}</b><span>${safe(x.positive_pct)}% positive · ${safe(x.votes)} votes</span></div><strong>${safe(x.rank)}</strong></article>`).join('')||'<div class="empty">No model rankings yet.</div>';
    const block=`<section id="autonomous-intelligence-block"><div class="section-title">Autonomous Intelligence Core</div><div class="ai-core-hero"><div><h2>Agent Consensus Layer</h2><p>Compares projection, value, confidence, readiness, strategy, simulation, market consensus, and line movement before surfacing decisions.</p></div><div class="ai-core-top"><span>Top Consensus</span><b>${safe(s.top_consensus_score)}</b></div></div><div class="ai-core-metrics"><article><span>BET</span><b>${safe(s.bet_count,0)}</b></article><article><span>LEAN</span><b>${safe(s.lean_count,0)}</b></article><article><span>WATCH</span><b>${safe(s.watch_count,0)}</b></article><article><span>PASS</span><b>${safe(s.pass_count,0)}</b></article><article><span>Top Player</span><b>${safe(s.top_player)}</b></article><article><span>Top Play</span><b>${safe(s.top_play)}</b></article></div><div class="ai-core-grid"><section class="ai-core-panel"><h3>Executive Report</h3><ul>${report}</ul></section><section class="ai-core-panel"><h3>Top Consensus</h3>${(ai.top_consensus||[]).slice(0,6).map(row).join('')||'<div class="empty">No consensus plays.</div>'}</section><section class="ai-core-panel"><h3>Discovered Angles</h3>${strategies}</section><section class="ai-core-panel"><h3>Model Rankings</h3>${models}</section></div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('autonomous-intelligence-block')){const w=document.createElement('div');w.innerHTML=block;el.prepend(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1200);
})();
</script>
'''

CSS = r'''
<style id="autonomous-intelligence-ui-v1-css">
.ai-core-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(0,229,160,.12),rgba(139,92,246,.10));border:1px solid rgba(0,229,160,.2);border-radius:24px;padding:18px;margin-bottom:12px}.ai-core-hero h2{margin:0 0 6px;font-size:28px}.ai-core-hero p{margin:0;color:#9aa4b2;line-height:1.45}.ai-core-top{text-align:right}.ai-core-top span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.ai-core-top b{font-size:38px;color:#00e5a0}.ai-core-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:12px}.ai-core-metrics article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:12px}.ai-core-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.ai-core-metrics b{display:block;font-size:20px;margin-top:5px}.ai-core-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}.ai-core-panel{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.ai-core-panel h3{margin:0 0 10px}.ai-core-panel ul{margin:0;padding-left:20px;color:#cbd5e1;line-height:1.55}.ai-core-row,.ai-model{display:flex;justify-content:space-between;gap:10px;align-items:center;border-bottom:1px solid rgba(255,255,255,.06);padding:10px 0;cursor:pointer}.ai-core-row b,.ai-model b{display:block}.ai-core-row span,.ai-model span{display:block;color:#7b879b;font-size:11px;margin-top:3px}.ai-core-row strong{font-size:26px;color:#00e5a0;text-align:right}.ai-core-row strong small{display:block;font-size:10px;color:#94a3b8}.ai-model strong{font-size:14px;color:#60a5fa;text-align:right}@media(max-width:900px){.ai-core-metrics{grid-template-columns:1fr 1fr 1fr}.ai-core-grid{grid-template-columns:1fr}.ai-core-hero{flex-direction:column;align-items:flex-start}.ai-core-top{text-align:left}}@media(max-width:520px){.ai-core-metrics{grid-template-columns:1fr 1fr}.ai-core-hero h2{font-size:23px}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="autonomous-intelligence-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="autonomous-intelligence-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('autonomous intelligence UI patch applied')

if __name__=='__main__':
    main()
