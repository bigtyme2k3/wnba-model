import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="daily-action-report-v2-ui">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function esc(s){return String(s||'').replace(/'/g,"\\'")}
  function card(p, cls=''){
    const reasons=(p.reasons||[]).slice(0,2).join(' · ');
    return `<article class="dar2-row ${cls}" onclick="openPlayerDetail&&openPlayerDetail('${esc(p.player)}','${esc(p.stat)}')"><div><b>${safe(p.player)} ${safe(p.stat)} ${safe(p.signal)}</b><span>${safe(p.final_action)} · ${safe(p.sportsbook)} · Line ${safe(p.line)} · CLV ${safe(p.expected_clv)}</span><em>${reasons||'Daily report reviewed.'}</em></div><strong>${safe(p.final_score)}<small>${safe(p.risk_level)}</small></strong></article>`
  }
  function render(){
    const r=DATA.daily_action_report_v2||{}; if(!r.summary)return;
    const s=r.summary||{};
    const top=s.top_action||{};
    const warnings=(r.warnings||[]).map(w=>`<li>${w}</li>`).join('')||'<li>No major warnings.</li>';
    const block=`<section id="daily-action-report-v2-block"><div class="section-title">Daily Action Report v2</div><div class="dar2-hero"><div><h2>Today’s Betting Command Center</h2><p>${safe(r.operating_note,'One clean summary of what to bet, wait on, and avoid.')}</p></div><div class="dar2-big"><span>Avg Score</span><b>${safe(s.avg_final_score)}</b></div></div><div class="dar2-top"><div><span>Top Action</span><b>${safe(top.player)} ${safe(top.stat)} ${safe(top.signal)}</b><small>${safe(top.final_action)} · ${safe(top.sportsbook)} · Score ${safe(top.final_score)}</small></div></div><div class="dar2-metrics"><article><span>Bet Now</span><b>${safe(s.bet_now,0)}</b></article><article><span>Bet Soon</span><b>${safe(s.bet_soon,0)}</b></article><article><span>Lean</span><b>${safe(s.lean,0)}</b></article><article><span>Monitor/Wait</span><b>${safe(s.monitor_or_wait,0)}</b></article><article><span>Pass/Avoid</span><b>${safe(s.pass_or_avoid,0)}</b></article></div><div class="dar2-grid"><section class="dar2-panel"><h3>What To Bet</h3>${(r.what_to_bet||[]).slice(0,6).map(x=>card(x)).join('')||'<div class="empty">No actionable bets.</div>'}</section><section class="dar2-panel"><h3>What To Wait On</h3>${(r.what_to_wait_on||[]).slice(0,6).map(x=>card(x,'wait')).join('')||'<div class="empty">Nothing to wait on.</div>'}</section><section class="dar2-panel"><h3>What To Avoid</h3>${(r.what_to_avoid||[]).slice(0,6).map(x=>card(x,'avoid')).join('')||'<div class="empty">No avoids.</div>'}</section><section class="dar2-panel"><h3>Warnings</h3><ul>${warnings}</ul><div class="dar2-mini"><b>Best Book:</b> ${safe(s.best_book)}<br><b>Best Stat Group:</b> ${safe(s.best_stat_group)}</div></section></div></section>`;
    const el=document.getElementById('tab-games'); if(el&&!document.getElementById('daily-action-report-v2-block')){const w=document.createElement('div');w.innerHTML=block;el.prepend(w.firstElementChild)}
  }
  const oldSwitch=window.switchTab;window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='games')setTimeout(render,0)};
  setTimeout(render,1200);
})();
</script>
'''

CSS = r'''
<style id="daily-action-report-v2-css">
.dar2-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:linear-gradient(135deg,rgba(245,197,24,.17),rgba(20,184,166,.10));border:1px solid rgba(245,197,24,.24);border-radius:26px;padding:18px;margin-bottom:12px}.dar2-hero h2{margin:0 0 6px;font-size:29px}.dar2-hero p{margin:0;color:#9aa4b2;line-height:1.45}.dar2-big{text-align:right}.dar2-big span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.dar2-big b{font-size:42px;color:#f5c518}.dar2-top{background:#0d0f1a;border:1px solid rgba(245,197,24,.18);border-radius:18px;padding:14px;margin-bottom:10px}.dar2-top span,.dar2-top small{display:block;color:#94a3b8}.dar2-top b{display:block;font-size:20px;margin:4px 0}.dar2-metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:12px}.dar2-metrics article{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:12px}.dar2-metrics span{display:block;color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px}.dar2-metrics b{display:block;font-size:22px;margin-top:5px}.dar2-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}.dar2-panel{background:#0d0f1a;border:1px solid rgba(255,255,255,.07);border-radius:18px;padding:15px}.dar2-panel h3{margin:0 0 10px}.dar2-panel ul{margin:0;padding-left:18px;color:#cbd5e1;line-height:1.55}.dar2-mini{margin-top:12px;color:#cbd5e1;font-size:13px}.dar2-row{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid rgba(255,255,255,.06);padding:10px 0;cursor:pointer}.dar2-row b,.dar2-row span,.dar2-row em{display:block}.dar2-row span{font-size:11px;color:#7b879b;margin-top:3px}.dar2-row em{font-style:normal;color:#94a3b8;font-size:11px;margin-top:5px}.dar2-row strong{font-size:26px;color:#34d399;text-align:right}.dar2-row.wait strong{color:#60a5fa}.dar2-row.avoid strong{color:#f87171}.dar2-row strong small{display:block;font-size:10px;color:#94a3b8}@media(max-width:900px){.dar2-grid{grid-template-columns:1fr}.dar2-metrics{grid-template-columns:1fr 1fr}.dar2-hero{flex-direction:column;align-items:flex-start}.dar2-big{text-align:left}}@media(max-width:520px){.dar2-hero h2{font-size:23px}.dar2-metrics{grid-template-columns:1fr 1fr}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="daily-action-report-v2-ui">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="daily-action-report-v2-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('daily action report v2 UI patch applied')

if __name__=='__main__':
    main()
