import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="results-review-center-ui">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function esc(s){return String(s||'').replace(/'/g,"\\'")}
  function pick(p, cls=''){
    const reasons=(p.reasons||[]).slice(0,2).join(' · ');
    return `<article class="rrc-row ${cls}" onclick="openPlayerDetail&&openPlayerDetail('${esc(p.player)}','${esc(p.stat)}')"><div><b>${safe(p.player)} ${safe(p.stat)} ${safe(p.signal)}</b><span>${safe(p.status)} · Proj ${safe(p.projection)} · Actual ${safe(p.actual)} · P/L ${safe(p.profit_units)}</span><em>${reasons||'Result reviewed.'}</em></div><strong>${safe(p.projection_error)}<small>ERR</small></strong></article>`
  }
  function render(){
    const rr=DATA.results_review_center||{}; if(!rr.summary)return;
    const s=rr.summary||{};
    const lessons=(rr.lessons||[]).map(x=>`<li>${x}</li>`).join('')||'<li>No lessons yet.</li>';
    const block=`<section id="results-review-center-block"><div class="section-title">Results Review Center</div><div class="rrc-hero"><div><h2>Yesterday’s Model Review</h2><p>Grades recommended bets, profit/loss, biggest misses, best calls, and what the model learned.</p></div><div class="rrc-big"><span>Units</span><b>${safe(s.profit_units,0)}</b></div></div><div class="rrc-metrics"><article><span>Completed</span><b>${safe(s.completed_bets,0)}</b></article><article><span>Wins</span><b>${safe(s.wins,0)}</b></article><article><span>Losses</span><b>${safe(s.losses,0)}</b></article><article><span>Hit Rate</span><b>${safe(s.hit_rate)}%</b></article><article><span>Pending</span><b>${safe(s.pending_bets,0)}</b></article></div><div class="rrc-grid"><section class="rrc-panel"><h3>Lessons</h3><ul>${lessons}</ul></section><section class="rrc-panel"><h3>Best Calls</h3>${(rr.best_calls||[]).slice(0,5).map(x=>pick(x,'win')).join('')||'<div class="empty">No completed wins yet.</div>'}</section><section class="rrc-panel"><h3>Biggest Misses</h3>${(rr.biggest_misses||[]).slice(0,5).map(x=>pick(x,'loss')).join('')||'<div class="empty">No misses yet.</div>'}</section><section class="rrc-panel"><h3>Pending</h3>${(rr.pending||[]).slice(0,5).map(x=>pick(x,'pending')).join('')||'<div class="empty">No pending bets.</div>'}</section></div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('results-review-center-block')){const w=document.createElement('div');w.innerHTML=block;el.prepend(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1250);
})();
</script>
'''

CSS = r'''
<style id="results-review-center-css">
.rrc-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(99,102,241,.15),rgba(20,184,166,.10));border:1px solid rgba(99,102,241,.25);border-radius:26px;padding:18px;margin-bottom:12px}.rrc-hero h2{margin:0 0 6px;font-size:29px}.rrc-hero p{margin:0;color:#9aa4b2;line-height:1.45}.rrc-big{text-align:right}.rrc-big span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.rrc-big b{font-size:42px;color:#a5b4fc}.rrc-metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:12px}.rrc-metrics article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:12px}.rrc-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.rrc-metrics b{display:block;font-size:22px;margin-top:5px}.rrc-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}.rrc-panel{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.rrc-panel h3{margin:0 0 10px}.rrc-panel ul{margin:0;padding-left:18px;color:#cbd5e1;line-height:1.55}.rrc-row{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid rgba(255,255,255,.06);padding:10px 0;cursor:pointer}.rrc-row b,.rrc-row span,.rrc-row em{display:block}.rrc-row span{font-size:11px;color:#7b879b;margin-top:3px}.rrc-row em{font-style:normal;color:#94a3b8;font-size:11px;margin-top:5px}.rrc-row strong{font-size:24px;color:#a5b4fc;text-align:right}.rrc-row.win strong{color:#34d399}.rrc-row.loss strong{color:#f87171}.rrc-row.pending strong{color:#60a5fa}.rrc-row strong small{display:block;font-size:10px;color:#94a3b8}@media(max-width:900px){.rrc-grid{grid-template-columns:1fr}.rrc-metrics{grid-template-columns:1fr 1fr}.rrc-hero{flex-direction:column;align-items:flex-start}.rrc-big{text-align:left}}@media(max-width:520px){.rrc-hero h2{font-size:23px}.rrc-metrics{grid-template-columns:1fr 1fr}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="results-review-center-ui">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="results-review-center-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('results review center UI patch applied')

if __name__=='__main__':
    main()
