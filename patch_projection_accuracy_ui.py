import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="projection-accuracy-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function row(a){return `<article class="pa-row"><div><b>${safe(a.player)} ${safe(a.stat)}</b><span>${safe(a.game)} · Proj ${safe(a.projection)} · Actual ${safe(a.actual)} · Error ${safe(a.error)}</span><em>${(a.miss_reasons||[]).slice(0,2).join(' · ')}</em></div><strong class="grade-${safe(a.grade).toLowerCase()}">${safe(a.grade)}</strong></article>`}
  function stat(k,v){return `<article class="pa-stat"><b>${safe(k)}</b><span>${safe(v.count,0)} props</span><strong>${safe(v.mae)} MAE</strong><small>${safe(v.hit_rate)}% hit</small></article>`}
  function render(){
    const pa=DATA.projection_accuracy||{}; if(!pa.summary)return;
    const s=pa.summary||{};
    const lessons=(pa.lessons||[]).map(x=>`<li>${x}</li>`).join('')||'<li>No lessons yet.</li>';
    const stats=Object.entries(pa.stat_summary||{}).map(([k,v])=>stat(k,v)).join('')||'<div class="empty">No stat summary yet.</div>';
    const block=`<section id="projection-accuracy-block"><div class="section-title">Projection Accuracy Lab</div><div class="pa-hero"><div><h2>Miss Report</h2><p>Audits completed props and explains where projection errors came from.</p></div><div class="pa-big"><span>MAE</span><b>${safe(s.mae)}</b></div></div><div class="pa-metrics"><article><span>Audited</span><b>${safe(s.audited_props,0)}</b></article><article><span>Hit Rate</span><b>${safe(s.hit_rate)}%</b></article><article><span>Bias</span><b>${safe(s.bias)}</b></article><article><span>Results Rows</span><b>${safe(s.actual_rows_available,0)}</b></article></div><div class="pa-grid"><section class="pa-panel"><h3>Lessons</h3><ul>${lessons}</ul></section><section class="pa-panel"><h3>By Stat</h3><div class="pa-stat-grid">${stats}</div></section><section class="pa-panel"><h3>Worst Misses</h3>${(pa.worst_misses||[]).slice(0,6).map(row).join('')||'<div class="empty">No misses found yet.</div>'}</section><section class="pa-panel"><h3>Best Calls</h3>${(pa.best_calls||[]).slice(0,6).map(row).join('')||'<div class="empty">No graded wins found yet.</div>'}</section></div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('projection-accuracy-block')){const w=document.createElement('div');w.innerHTML=block;el.appendChild(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1300);
})();
</script>
'''

CSS = r'''
<style id="projection-accuracy-ui-v1-css">
.pa-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(245,197,24,.11),rgba(96,165,250,.08));border:1px solid rgba(245,197,24,.18);border-radius:24px;padding:18px;margin-bottom:12px}.pa-hero h2{margin:0 0 6px;font-size:28px}.pa-hero p{margin:0;color:#9aa4b2}.pa-big{text-align:right}.pa-big span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.pa-big b{font-size:38px;color:#f5c518}.pa-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}.pa-metrics article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:12px}.pa-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.pa-metrics b{display:block;font-size:22px;margin-top:5px}.pa-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}.pa-panel{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.pa-panel h3{margin:0 0 10px}.pa-panel ul{margin:0;padding-left:20px;color:#cbd5e1;line-height:1.55}.pa-row{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid rgba(255,255,255,.06);padding:10px 0}.pa-row b,.pa-row span,.pa-row em{display:block}.pa-row span{font-size:11px;color:#7b879b;margin-top:3px}.pa-row em{font-style:normal;color:#f87171;font-size:11px;margin-top:5px}.pa-row strong{font-size:24px}.grade-a{color:#00e5a0}.grade-b{color:#60a5fa}.grade-c{color:#f5c518}.grade-d{color:#f87171}.pa-stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.pa-stat{background:#080b13;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:10px}.pa-stat b,.pa-stat span,.pa-stat strong,.pa-stat small{display:block}.pa-stat span,.pa-stat small{color:#7b879b;font-size:11px}.pa-stat strong{color:#f5c518;margin-top:5px}@media(max-width:900px){.pa-grid{grid-template-columns:1fr}.pa-hero{flex-direction:column;align-items:flex-start}.pa-big{text-align:left}}@media(max-width:520px){.pa-metrics,.pa-stat-grid{grid-template-columns:1fr 1fr}.pa-hero h2{font-size:23px}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="projection-accuracy-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="projection-accuracy-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('projection accuracy UI patch applied')

if __name__=='__main__':
    main()
