import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="minutes-usage-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function esc(s){return String(s||'').replace(/'/g,"\\'")}
  function row(p, cls=''){
    const reasons=(p.risk_reasons||p.notes||[]).slice(0,2).join(' · ');
    return `<article class="mu-row ${cls}" onclick="openPlayerDetail&&openPlayerDetail('${esc(p.player)}','${esc(p.stat)}')"><div><b>${safe(p.player)} ${safe(p.stat)} ${safe(p.signal)}</b><span>${safe(p.role_bucket)} · Min ${safe(p.projected_minutes)} · Range ${safe(p.minutes_range)} · Usage ${safe(p.projected_usage)} (${safe(p.usage_change)})</span><em>${reasons||'Minutes/usage profile reviewed.'}</em></div><strong>${safe(p.minutes_usage_score)}<small>${safe(p.minutes_usage_grade)}</small></strong></article>`
  }
  function stat(x){return `<article class="mu-stat"><b>${safe(x.stat||x.player)}</b><span>${safe(x.count)} props</span><strong>${safe(x.avg_minutes_usage_score)}</strong></article>`}
  function render(){
    const mu=DATA.minutes_usage_intelligence||{}; if(!mu.summary)return;
    const s=mu.summary||{};
    const block=`<section id="minutes-usage-block"><div class="section-title">Minutes & Usage Intelligence</div><div class="mu-hero"><div><h2>Role Stability Engine</h2><p>Grades whether today's minutes, usage, and rotation context are trustworthy enough to support the prop projection.</p></div><div class="mu-big"><span>Avg Role Score</span><b>${safe(s.avg_minutes_usage_score)}</b></div></div><div class="mu-metrics"><article><span>Props Scored</span><b>${safe(s.props_scored,0)}</b></article><article><span>Trust</span><b>${safe(s.trust_count,0)}</b></article><article><span>Reduce</span><b>${safe(s.reduce_count,0)}</b></article><article><span>High Risk</span><b>${safe(s.high_rotation_risk_count,0)}</b></article></div><div class="mu-grid"><section class="mu-panel"><h3>Best Minutes / Usage Profiles</h3>${(mu.top_minutes_usage||[]).slice(0,6).map(x=>row(x)).join('')||'<div class="empty">No role profiles yet.</div>'}</section><section class="mu-panel"><h3>Rotation Risk Watch</h3>${(mu.rotation_risk_watch||[]).slice(0,6).map(x=>row(x,'risk')).join('')||'<div class="empty">No rotation risk flagged.</div>'}</section><section class="mu-panel full"><h3>By Stat</h3><div class="mu-stat-grid">${(mu.stat_summary||[]).map(stat).join('')||'<div class="empty">No stat summary.</div>'}</div></section></div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('minutes-usage-block')){const w=document.createElement('div');w.innerHTML=block;el.appendChild(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1500);
})();
</script>
'''

CSS = r'''
<style id="minutes-usage-ui-v1-css">
.mu-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(52,211,153,.13),rgba(245,158,11,.10));border:1px solid rgba(52,211,153,.2);border-radius:24px;padding:18px;margin-bottom:12px}.mu-hero h2{margin:0 0 6px;font-size:28px}.mu-hero p{margin:0;color:#9aa4b2;line-height:1.45}.mu-big{text-align:right}.mu-big span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.mu-big b{font-size:38px;color:#34d399}.mu-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}.mu-metrics article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:12px}.mu-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.mu-metrics b{display:block;font-size:22px;margin-top:5px}.mu-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}.mu-panel{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.mu-panel.full{grid-column:1/-1}.mu-panel h3{margin:0 0 10px}.mu-row{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid rgba(255,255,255,.06);padding:10px 0;cursor:pointer}.mu-row b,.mu-row span,.mu-row em{display:block}.mu-row span{font-size:11px;color:#7b879b;margin-top:3px}.mu-row em{font-style:normal;color:#94a3b8;font-size:11px;margin-top:5px}.mu-row strong{font-size:26px;color:#34d399;text-align:right}.mu-row.risk strong{color:#f87171}.mu-row strong small{display:block;font-size:10px;color:#94a3b8}.mu-stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.mu-stat{background:#080b13;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:10px}.mu-stat b,.mu-stat span,.mu-stat strong{display:block}.mu-stat span{color:#7b879b;font-size:11px}.mu-stat strong{font-size:22px;color:#34d399;margin-top:5px}@media(max-width:900px){.mu-grid{grid-template-columns:1fr}.mu-stat-grid{grid-template-columns:1fr 1fr}.mu-hero{flex-direction:column;align-items:flex-start}.mu-big{text-align:left}}@media(max-width:520px){.mu-metrics,.mu-stat-grid{grid-template-columns:1fr 1fr}.mu-hero h2{font-size:23px}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="minutes-usage-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="minutes-usage-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('minutes usage UI patch applied')

if __name__=='__main__':
    main()
