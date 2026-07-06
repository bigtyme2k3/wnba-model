import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="market-timing-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function esc(s){return String(s||'').replace(/'/g,"\\'")}
  function play(p, cls=''){
    const reasons=(p.reasons||[]).slice(0,2).join(' · ');
    return `<article class="mt-row ${cls}" onclick="openPlayerDetail&&openPlayerDetail('${esc(p.player)}','${esc(p.stat)}')"><div><b>${safe(p.player)} ${safe(p.stat)} ${safe(p.signal)}</b><span>${safe(p.timing_action)} · ${safe(p.sportsbook)} · CLV ${safe(p.expected_clv)} · Urgency ${safe(p.urgency_score)}</span><em>${reasons||'Timing reviewed.'}</em></div><strong>${safe(p.timing_confidence)}<small>${safe(p.expected_line_direction)}</small></strong></article>`
  }
  function book(x){return `<article class="mt-book"><b>${safe(x.sportsbook)}</b><span>${safe(x.count)} props</span><strong>${safe(x.avg_expected_clv)}</strong><small>${safe(x.bet_now_count)} playable</small></article>`}
  function render(){
    const mt=DATA.market_timing_intelligence||{}; if(!mt.summary)return;
    const s=mt.summary||{};
    const block=`<section id="market-timing-block"><div class="section-title">Market Timing Intelligence</div><div class="mt-hero"><div><h2>Bet Now / Wait Engine</h2><p>Uses expected CLV, sportsbook speed, context, volatility, injury risk, and projection quality to decide timing.</p></div><div class="mt-big"><span>Avg CLV</span><b>${safe(s.avg_expected_clv)}</b></div></div><div class="mt-metrics"><article><span>Bet Now</span><b>${safe(s.bet_now_count,0)}</b></article><article><span>Bet Soon</span><b>${safe(s.bet_soon_count,0)}</b></article><article><span>Wait</span><b>${safe(s.wait_count,0)}</b></article><article><span>Monitor</span><b>${safe(s.monitor_count,0)}</b></article></div><div class="mt-grid"><section class="mt-panel"><h3>Best Timing Plays</h3>${(mt.best_timing_plays||[]).slice(0,6).map(x=>play(x)).join('')||'<div class="empty">No timing plays yet.</div>'}</section><section class="mt-panel"><h3>Monitor / Wait List</h3>${(mt.monitor_list||[]).slice(0,6).map(x=>play(x,'watch')).join('')||'<div class="empty">No monitor plays.</div>'}</section><section class="mt-panel full"><h3>Sportsbook Timing</h3><div class="mt-book-grid">${(mt.sportsbook_timing||[]).map(book).join('')||'<div class="empty">No book timing summary.</div>'}</div></section></div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('market-timing-block')){const w=document.createElement('div');w.innerHTML=block;el.appendChild(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1550);
})();
</script>
'''

CSS = r'''
<style id="market-timing-ui-v1-css">
.mt-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(245,197,24,.14),rgba(16,185,129,.10));border:1px solid rgba(245,197,24,.22);border-radius:24px;padding:18px;margin-bottom:12px}.mt-hero h2{margin:0 0 6px;font-size:28px}.mt-hero p{margin:0;color:#9aa4b2;line-height:1.45}.mt-big{text-align:right}.mt-big span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.mt-big b{font-size:38px;color:#f5c518}.mt-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}.mt-metrics article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:12px}.mt-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.mt-metrics b{display:block;font-size:22px;margin-top:5px}.mt-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}.mt-panel{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.mt-panel.full{grid-column:1/-1}.mt-panel h3{margin:0 0 10px}.mt-row{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid rgba(255,255,255,.06);padding:10px 0;cursor:pointer}.mt-row b,.mt-row span,.mt-row em{display:block}.mt-row span{font-size:11px;color:#7b879b;margin-top:3px}.mt-row em{font-style:normal;color:#94a3b8;font-size:11px;margin-top:5px}.mt-row strong{font-size:26px;color:#f5c518;text-align:right}.mt-row.watch strong{color:#60a5fa}.mt-row strong small{display:block;font-size:10px;color:#94a3b8}.mt-book-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.mt-book{background:#080b13;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:10px}.mt-book b,.mt-book span,.mt-book strong,.mt-book small{display:block}.mt-book span,.mt-book small{color:#7b879b;font-size:11px}.mt-book strong{font-size:22px;color:#f5c518;margin-top:5px}@media(max-width:900px){.mt-grid{grid-template-columns:1fr}.mt-book-grid{grid-template-columns:1fr 1fr}.mt-hero{flex-direction:column;align-items:flex-start}.mt-big{text-align:left}}@media(max-width:520px){.mt-metrics,.mt-book-grid{grid-template-columns:1fr 1fr}.mt-hero h2{font-size:23px}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="market-timing-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="market-timing-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('market timing UI patch applied')

if __name__=='__main__':
    main()
