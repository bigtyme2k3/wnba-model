import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="decision-center-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function propCard(p, cls=''){return `<article class="dc-prop ${cls}" onclick="openPlayerDetail&&openPlayerDetail('${String(p.player||'').replace(/'/g,"\\'")}','${String(p.stat||'').replace(/'/g,"\\'")}')"><div><b>${safe(p.player)} ${safe(p.stat)} ${safe(p.signal)}</b><span>${safe(p.game)} · ${safe(p.best_book_title||p.best_book)} · Line ${safe(p.line)}</span></div><strong>${safe(p.ups_score)}<small>${safe(p.ups_grade)}</small></strong></article>`}
  function trapCard(p){return `<article class="dc-trap"><div><b>${safe(p.player)} ${safe(p.stat)}</b><span>${safe(p.game)}</span><em>${(p.trap_reasons||[]).join(' · ')}</em></div><strong>${safe(p.ups_score)}</strong></article>`}
  function focus(items,key,label){return (items||[]).map(x=>`<span>${safe(x[key])} <b>${safe(x.count)}</b></span>`).join('')||`<span>${label}</span>`}
  function render(){
    const dc=DATA.decision_center||{}; if(!dc.summary)return;
    const s=dc.summary||{};
    const block=`<section id="decision-center-block"><div class="section-title">Betting Decision Center</div><div class="dc-hero"><div><h2>Today's Decision Board</h2><p>${(dc.briefing||[]).slice(0,3).join(' ')}</p></div><div class="dc-exposure"><span>Exposure</span><b>${safe(s.recommended_exposure)}</b></div></div><div class="dc-metrics"><article><span>Actionable</span><b>${safe(s.actionable_count,0)}</b></article><article><span>Traps</span><b>${safe(s.trap_count,0)}</b></article><article><span>Avg UPS</span><b>${safe(s.avg_ups_actionable)}</b></article><article><span>Best Market</span><b>${safe(s.best_market)}</b></article><article><span>Best Book</span><b>${safe(s.best_book)}</b></article><article><span>Top Signal</span><b>${safe(s.top_signal)}</b></article></div><div class="dc-grid"><section class="dc-panel"><h3>Best Bet</h3>${dc.best_bet?propCard(dc.best_bet,'best'):'<div class="empty">No best bet passed filters.</div>'}</section><section class="dc-panel"><h3>High EV</h3>${(dc.high_ev||[]).slice(0,5).map(p=>propCard(p,'ev')).join('')||'<div class="empty">No high-EV plays.</div>'}</section><section class="dc-panel"><h3>Safest Plays</h3>${(dc.safest||[]).slice(0,5).map(p=>propCard(p,'safe')).join('')||'<div class="empty">No safe plays yet.</div>'}</section><section class="dc-panel"><h3>Trap Watch</h3>${(dc.traps||[]).slice(0,5).map(trapCard).join('')||'<div class="empty">No traps flagged.</div>'}</section></div><div class="dc-focus"><article><span>Market Focus</span>${focus(dc.market_focus,'market','No markets')}</article><article><span>Book Focus</span>${focus(dc.book_focus,'book','No books')}</article></div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('decision-center-block')){const w=document.createElement('div');w.innerHTML=block;el.prepend(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1100);
})();
</script>
'''

CSS = r'''
<style id="decision-center-ui-v1-css">
.dc-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(96,165,250,.12),rgba(245,197,24,.07));border:1px solid rgba(96,165,250,.18);border-radius:22px;padding:17px;margin-bottom:12px}.dc-hero h2{margin:0 0 6px;font-size:28px}.dc-hero p{margin:0;color:#9aa4b2;line-height:1.45}.dc-exposure{text-align:right}.dc-exposure span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.dc-exposure b{font-size:28px;color:#00e5a0}.dc-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:12px}.dc-metrics article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:12px}.dc-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.dc-metrics b{display:block;font-size:20px;margin-top:5px}.dc-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}.dc-panel{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.dc-panel h3{margin:0 0 10px}.dc-prop,.dc-trap{display:flex;justify-content:space-between;gap:10px;align-items:center;border-bottom:1px solid rgba(255,255,255,.06);padding:10px 0;cursor:pointer}.dc-prop b,.dc-trap b{display:block}.dc-prop span,.dc-trap span{display:block;color:#7b879b;font-size:11px;margin-top:3px}.dc-prop strong{font-size:26px;color:#00e5a0;text-align:right}.dc-prop strong small{display:block;font-size:10px;color:#94a3b8}.dc-prop.best{background:rgba(0,229,160,.06);margin:-4px -6px 6px;padding:12px 8px;border-radius:14px;border-bottom:0}.dc-prop.ev strong{color:#60a5fa}.dc-prop.safe strong{color:#f5c518}.dc-trap em{display:block;font-style:normal;color:#f87171;font-size:11px;margin-top:5px}.dc-trap strong{color:#f87171;font-size:22px}.dc-focus{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}.dc-focus article{background:#0d1220;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:13px}.dc-focus article>span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}.dc-focus article span:not(:first-child){display:inline-block;background:#ffffff10;border-radius:999px;padding:5px 8px;margin:3px;color:#cbd5e1}.dc-focus b{color:#00e5a0}@media(max-width:900px){.dc-metrics{grid-template-columns:1fr 1fr 1fr}.dc-grid,.dc-focus{grid-template-columns:1fr}.dc-hero{flex-direction:column;align-items:flex-start}.dc-exposure{text-align:left}}@media(max-width:520px){.dc-metrics{grid-template-columns:1fr 1fr}.dc-hero h2{font-size:23px}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="decision-center-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="decision-center-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ decision center UI patch applied')

if __name__=='__main__':
    main()
