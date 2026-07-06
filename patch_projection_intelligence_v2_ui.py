import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="projection-intelligence-v2-ui">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function esc(s){return String(s||'').replace(/'/g,"\\'")}
  function item(p, risk=''){
    const notes=(p.notes||[]).slice(0,2).join(' · ');
    return `<article class="pi2-row ${risk}" onclick="openPlayerDetail&&openPlayerDetail('${esc(p.player)}','${esc(p.stat)}')"><div><b>${safe(p.player)} ${safe(p.stat)} ${safe(p.signal)}</b><span>${safe(p.game)} · Line ${safe(p.line)} · Median ${safe(p.median)} · Floor ${safe(p.floor)} · Ceiling ${safe(p.ceiling)}</span><em>${notes||'Projection band created.'}</em></div><strong>${safe(p.projection_quality)}<small>${safe(p.projection_grade)}</small></strong></article>`
  }
  function stat(x){return `<article class="pi2-stat"><b>${safe(x.stat)}</b><span>${safe(x.count)} props</span><strong>${safe(x.avg_quality)}</strong><small>${safe(x.avg_hit_probability)}% hit prob</small></article>`}
  function render(){
    const pi=DATA.projection_intelligence_v2||{}; if(!pi.summary)return;
    const s=pi.summary||{};
    const block=`<section id="projection-intelligence-v2-block"><div class="section-title">Projection Intelligence v2</div><div class="pi2-hero"><div><h2>Floor / Median / Ceiling Engine</h2><p>Converts raw projections into probability bands using context, pace, usage, matchup, volatility, and line edge.</p></div><div class="pi2-big"><span>Avg Quality</span><b>${safe(s.avg_projection_quality)}</b></div></div><div class="pi2-metrics"><article><span>Props Scored</span><b>${safe(s.props_scored,0)}</b></article><article><span>A Grade</span><b>${safe(s.a_grade_count,0)}</b></article><article><span>60%+ Hit Prob</span><b>${safe(s.high_hit_probability_count,0)}</b></article><article><span>High Vol</span><b>${safe(s.high_volatility_count,0)}</b></article></div><div class="pi2-grid"><section class="pi2-panel"><h3>Best Projection Quality</h3>${(pi.top_projection_quality||[]).slice(0,6).map(x=>item(x)).join('')||'<div class="empty">No projection intelligence yet.</div>'}</section><section class="pi2-panel"><h3>Projection Risk Watch</h3>${(pi.projection_risk_watch||[]).slice(0,6).map(x=>item(x,'risk')).join('')||'<div class="empty">No risk plays flagged.</div>'}</section><section class="pi2-panel full"><h3>By Stat</h3><div class="pi2-stat-grid">${(pi.stat_summary||[]).map(stat).join('')||'<div class="empty">No stat summary.</div>'}</div></section></div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('projection-intelligence-v2-block')){const w=document.createElement('div');w.innerHTML=block;el.appendChild(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1450);
})();
</script>
'''

CSS = r'''
<style id="projection-intelligence-v2-css">
.pi2-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(96,165,250,.13),rgba(168,85,247,.10));border:1px solid rgba(96,165,250,.2);border-radius:24px;padding:18px;margin-bottom:12px}.pi2-hero h2{margin:0 0 6px;font-size:28px}.pi2-hero p{margin:0;color:#9aa4b2;line-height:1.45}.pi2-big{text-align:right}.pi2-big span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.pi2-big b{font-size:38px;color:#60a5fa}.pi2-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}.pi2-metrics article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:12px}.pi2-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.pi2-metrics b{display:block;font-size:22px;margin-top:5px}.pi2-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}.pi2-panel{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.pi2-panel.full{grid-column:1/-1}.pi2-panel h3{margin:0 0 10px}.pi2-row{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid rgba(255,255,255,.06);padding:10px 0;cursor:pointer}.pi2-row b,.pi2-row span,.pi2-row em{display:block}.pi2-row span{font-size:11px;color:#7b879b;margin-top:3px}.pi2-row em{font-style:normal;color:#94a3b8;font-size:11px;margin-top:5px}.pi2-row strong{font-size:26px;color:#60a5fa;text-align:right}.pi2-row.risk strong{color:#f87171}.pi2-row strong small{display:block;font-size:10px;color:#94a3b8}.pi2-stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.pi2-stat{background:#080b13;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:10px}.pi2-stat b,.pi2-stat span,.pi2-stat strong,.pi2-stat small{display:block}.pi2-stat span,.pi2-stat small{color:#7b879b;font-size:11px}.pi2-stat strong{font-size:22px;color:#60a5fa;margin-top:5px}@media(max-width:900px){.pi2-grid{grid-template-columns:1fr}.pi2-stat-grid{grid-template-columns:1fr 1fr}.pi2-hero{flex-direction:column;align-items:flex-start}.pi2-big{text-align:left}}@media(max-width:520px){.pi2-metrics,.pi2-stat-grid{grid-template-columns:1fr 1fr}.pi2-hero h2{font-size:23px}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="projection-intelligence-v2-ui">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="projection-intelligence-v2-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('projection intelligence v2 UI patch applied')

if __name__=='__main__':
    main()
