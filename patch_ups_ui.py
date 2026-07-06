import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="ups-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function gradeCls(g){return String(g||'').replace('+','plus').toLowerCase()}
  function playRow(p){return `<article class="ups-row" onclick="openPlayerDetail&&openPlayerDetail('${String(p.player||'').replace(/'/g,"\\'")}','${String(p.stat||'').replace(/'/g,"\\'")}')"><div><b>${safe(p.player)} ${safe(p.stat)} ${safe(p.signal)}</b><span>${safe(p.game)} · ${safe(p.best_book_title||p.best_book)} · ${safe(p.readiness?.label||p.readiness_score)}</span><div class="ups-badges">${(p.ups_badges||[]).slice(0,4).map(b=>`<em>${b}</em>`).join('')}</div></div><div class="ups-score grade-${gradeCls(p.ups_grade)}"><small>${safe(p.ups_grade)}</small><strong>${safe(p.ups_score)}</strong></div></article>`}
  function factor(f){return `<li class="${f.agrees?'yes':'no'}"><span>${safe(f.name)}</span><b>${f.agrees?'✓':'×'}</b></li>`}
  function openUPS(p){
    const modal=document.createElement('div');modal.className='ups-modal';
    const factors=(p.model_agreement?.factors||[]).map(factor).join('')||'<li>No agreement factors.</li>';
    const reasons=(p.prediction_breakdown||[]).map(r=>`<li>${r}</li>`).join('')||'<li>No explanation generated.</li>';
    modal.innerHTML=`<div class="ups-back" onclick="this.closest('.ups-modal').remove()"></div><section class="ups-panel"><button onclick="this.closest('.ups-modal').remove()">×</button><header><div><div class="ups-kicker">Universal Prediction Score</div><h2>${safe(p.player)} ${safe(p.stat)}</h2><p>${safe(p.game)} · ${safe(p.signal)} · ${safe(p.best_book_title||p.best_book)}</p></div><div class="ups-hero-score grade-${gradeCls(p.ups_grade)}"><span>${safe(p.ups_grade)}</span><b>${safe(p.ups_score)}</b></div></header><div class="ups-metrics"><article><span>EV</span><b>${safe(p.ev_pct)}%</b></article><article><span>Edge</span><b>${safe(p.edge)}</b></article><article><span>Ready</span><b>${safe(p.readiness_score)}</b></article><article><span>Agree</span><b>${safe(p.model_agreement?.label)}</b></article></div><div class="ups-badges big">${(p.ups_badges||[]).map(b=>`<em>${b}</em>`).join('')}</div><div class="ups-split"><article><h3>Model Agreement</h3><ul class="ups-factors">${factors}</ul></article><article><h3>Prediction Breakdown</h3><ul class="ups-reasons">${reasons}</ul></article></div></section>`;
    document.body.appendChild(modal);
  }
  window.openUPSDetail=openUPS;
  function render(){
    const ups=DATA.unified_prediction_score||{}; if(!ups.props_scored)return;
    const top=(ups.top_ups||[]).slice(0,8);
    const block=`<section id="ups-block"><div class="section-title">Universal Prediction Score</div><div class="ups-hero"><div><h2>UPS Decision Layer</h2><p>One 0-100 score combining edge, EV, confidence, readiness, agreement, injury risk, and market value.</p></div><div class="ups-avg"><span>Avg UPS</span><b>${safe(ups.avg_ups)}</b></div></div><div class="ups-grade-grid">${Object.entries(ups.top_grades||{}).map(([k,v])=>`<article class="grade-${gradeCls(k)}"><span>${k}</span><b>${v}</b></article>`).join('')}</div><div class="ups-list">${top.map(playRow).join('')||'<div class="empty">No scored props yet.</div>'}</div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('ups-block')){const w=document.createElement('div');w.innerHTML=block;el.appendChild(w.firstElementChild);document.querySelectorAll('.ups-row').forEach((row,i)=>row.addEventListener('contextmenu',e=>{e.preventDefault();openUPS(top[i])}))}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1000);
})();
</script>
'''

CSS = r'''
<style id="ups-ui-v1-css">
.ups-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(0,229,160,.12),rgba(96,165,250,.08));border:1px solid rgba(0,229,160,.18);border-radius:22px;padding:17px;margin-bottom:12px}.ups-hero h2{margin:0 0 5px}.ups-hero p{margin:0;color:#8b95a8}.ups-avg{text-align:right}.ups-avg span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.ups-avg b{font-size:34px;color:#00e5a0}.ups-grade-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:12px}.ups-grade-grid article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:14px;padding:10px;text-align:center}.ups-grade-grid span{display:block;color:#64748b;font-size:11px}.ups-grade-grid b{font-size:24px}.ups-list{display:flex;flex-direction:column;gap:8px;margin-bottom:20px}.ups-row{display:flex;justify-content:space-between;gap:12px;background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:16px;padding:12px;cursor:pointer}.ups-row b,.ups-row span{display:block}.ups-row span{font-size:11px;color:#7b879b;margin-top:3px}.ups-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.ups-badges em{font-style:normal;font-size:10px;border-radius:999px;background:#ffffff10;padding:4px 7px;color:#cbd5e1}.ups-badges.big em{font-size:12px}.ups-score{text-align:right}.ups-score small{display:block;font-size:11px;color:#64748b}.ups-score strong{font-size:28px}.grade-aplus strong,.grade-aplus b,.grade-a strong,.grade-a b{color:#00e5a0}.grade-bplus strong,.grade-bplus b{color:#60a5fa}.grade-b strong,.grade-b b{color:#f5c518}.grade-c strong,.grade-c b{color:#fb923c}.grade-avoid strong,.grade-avoid b{color:#f87171}.ups-modal{position:fixed;inset:0;z-index:9999}.ups-back{position:absolute;inset:0;background:rgba(0,0,0,.74);backdrop-filter:blur(6px)}.ups-panel{position:absolute;right:0;top:0;height:100%;width:min(760px,96vw);overflow:auto;background:#080b13;border-left:1px solid rgba(255,255,255,.1);box-shadow:-22px 0 70px #000;padding:22px}.ups-panel>button{float:right;position:sticky;top:0;width:38px;height:38px;border-radius:12px;background:#111827;color:#e2e8f0;border:1px solid rgba(255,255,255,.12);font-size:24px}.ups-panel header{display:flex;justify-content:space-between;gap:14px;margin:12px 0 18px}.ups-kicker{color:#60a5fa;font-size:11px;text-transform:uppercase;letter-spacing:1.5px;font-weight:900}.ups-panel h2{margin:5px 0;font-size:30px}.ups-panel p{margin:0;color:#7b879b}.ups-hero-score{text-align:right}.ups-hero-score span{display:block;color:#7b879b;font-size:11px;text-transform:uppercase}.ups-hero-score b{font-size:40px}.ups-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.ups-metrics article{background:#0d1220;border:1px solid rgba(255,255,255,.07);border-radius:16px;padding:12px}.ups-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase}.ups-metrics b{display:block;font-size:22px;margin-top:5px}.ups-split{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px}.ups-split article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.ups-split h3{margin:0 0 10px}.ups-factors,.ups-reasons{margin:0;padding-left:18px;line-height:1.55;color:#cbd5e1}.ups-factors li{display:flex;justify-content:space-between;gap:10px}.ups-factors li.yes b{color:#00e5a0}.ups-factors li.no b{color:#f87171}@media(max-width:840px){.ups-grade-grid{grid-template-columns:1fr 1fr 1fr}.ups-metrics,.ups-split{grid-template-columns:1fr 1fr}.ups-hero{flex-direction:column;align-items:flex-start}.ups-avg,.ups-hero-score{text-align:left}}@media(max-width:520px){.ups-grade-grid,.ups-metrics,.ups-split{grid-template-columns:1fr}.ups-panel{width:100vw}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="ups-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="ups-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ UPS UI patch applied')

if __name__=='__main__':
    main()
