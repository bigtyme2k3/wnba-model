import os
import re

HTML = 'docs/index.html'

PATCH = r'''
<script id="slip-optimizer-ui-v1">
(function(){
  function safe(v,d='—'){return v===null||v===undefined||v===''||String(v)==='nan'?d:v}
  function pct(v){return typeof v==='number'?Math.round(v*10)/10+'%':'—'}
  function slipCard(s,i){
    const riskClass=(s.risk||'MED').toLowerCase();
    const legs=(s.plays||[]).map((p,idx)=>`<div class="slip-leg"><span>${idx+1}</span><div><b>${safe(p.play)}</b><small>${safe(p.game)} · ${safe(p.book)} · ${safe(p.odds)}</small></div></div>`).join('');
    return `<article class="slip-card ${riskClass}"><div class="slip-top"><div><div class="slip-label">${safe(s.label)}</div><div class="slip-sub">${safe(s.legs)} legs · ${safe(s.risk)} risk</div></div><div class="slip-odds">${safe(s.combined_american)}</div></div><div class="slip-metrics"><div><span>Model</span><b>${safe(s.model_prob_pct)}%</b></div><div><span>EV</span><b class="${Number(s.ev_pct)>0?'good':'bad'}">${safe(s.ev_pct)}%</b></div><div><span>Score</span><b>${safe(s.avg_score)}</b></div><div><span>Corr</span><b>${safe(s.correlation_penalty)}</b></div></div><div class="slip-legs">${legs}</div><div class="slip-reason">${safe(s.reason)}</div></article>`
  }
  window.renderBets=function(){
    const bets=(DATA.best_bets||[]);
    const slips=(DATA.slip_optimizer||{}).slips||[];
    const slipHtml=slips.length?slips.map(slipCard).join(''):'<div class="empty">No optimized slips yet. Need positive-EV eligible bets.</div>';
    const rows=bets.length?bets.map((b,i)=>`<article class="board-row best-bet-row"><div class="rank">${String(i+1).padStart(2,'0')}</div><div><span class="tag">${safe(b.type)}</span></div><div><div class="board-main">${safe(b.play)}</div><div class="board-sub">${safe(b.game)} · ${safe(b.score_label)} · Score ${safe(b.score)} · Grade ${safe(b.grade)}</div></div><div><div class="board-label">Best Book</div><div class="board-value">${safe(b.best_book_title||b.best_book)}</div><div class="board-sub">${safe(b.available_books,0)} books</div></div><div><div class="board-label">EV / Fair</div><div class="board-value ${Number(b.ev_pct)>0?'good':'bad'}">${safe(b.ev_pct)}%</div><div class="board-sub">Fair ${safe(b.fair_odds)} · ${safe(b.model_prob_pct)}%</div></div><div><span class="edge-badge">${safe(b.best_line,b.market_line)} @ ${safe(b.best_odds,b.odds)}</span><div class="board-sub">Kelly ${safe(b.units,0)}u</div></div></article>`).join(''):'<div class="empty">No actionable positive-EV plays yet.</div>';
    const shop=(DATA.line_shopping||[]).slice(0,12).map(s=>`<article class="board-row shop-row"><div><span class="tag">${safe(s.market_type)}</span></div><div><div class="board-main">${safe(s.player)||safe(s.side)} ${safe(s.stat,'')}</div><div class="board-sub">${safe(s.game)}</div></div><div><div class="board-label">Best</div><div class="board-value">${safe(s.book_title||s.book_key)}</div></div><div><div class="board-label">Line</div><div class="board-value">${safe(s.line)} @ ${safe(s.odds)}</div></div></article>`).join('')||'<div class="note">Line shopping appears after The Odds API returns per-book lines.</div>';
    const el=document.getElementById('tab-bets');
    if(el) el.innerHTML=`<div class="section-title">Slip Optimizer</div><div class="slip-grid">${slipHtml}</div><div class="section-title">Best Bets + Best Sportsbook</div><div class="board">${rows}</div><div class="section-title">Line Shopping Snapshot</div><div class="board">${shop}</div>`;
  };
  const oldSwitch=window.switchTab;
  window.switchTab=function(name,btn){if(typeof oldSwitch==='function')oldSwitch(name,btn);if(name==='bets')setTimeout(window.renderBets,0)};
})();
</script>
'''

CSS = r'''
<style id="slip-optimizer-ui-v1-css">
  .slip-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:18px}.slip-card{background:linear-gradient(180deg,#111827,#0d1220);border:1px solid var(--border);border-radius:18px;padding:15px;box-shadow:0 10px 30px #00000030}.slip-card.low{box-shadow:inset 3px 0 0 var(--high)}.slip-card.med{box-shadow:inset 3px 0 0 var(--med)}.slip-card.high{box-shadow:inset 3px 0 0 var(--under)}.slip-top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.slip-label{font-size:15px;font-weight:900}.slip-sub{font-size:11px;color:#7b879b;margin-top:4px}.slip-odds{font-size:22px;font-weight:900;color:#eaf2ff}.slip-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:13px 0}.slip-metrics div{background:#ffffff08;border-radius:12px;padding:8px}.slip-metrics span{display:block;font-size:9px;letter-spacing:1.2px;color:#64748b;text-transform:uppercase}.slip-metrics b{display:block;margin-top:4px}.slip-legs{display:flex;flex-direction:column;gap:7px}.slip-leg{display:flex;gap:9px;align-items:flex-start;background:#080b13;border-radius:12px;padding:8px}.slip-leg>span{width:20px;height:20px;border-radius:50%;background:#1b2742;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:900}.slip-leg b{font-size:12px}.slip-leg small{display:block;color:#7b879b;font-size:10px;margin-top:3px}.slip-reason{font-size:11px;color:#8b95a8;margin-top:11px;line-height:1.35}.best-bet-row{grid-template-columns:42px 80px 1.3fr 150px 120px 120px!important}.shop-row{grid-template-columns:90px 1fr 120px 100px!important}.rank{font-weight:900;color:#8ab4ff}@media(max-width:840px){.slip-grid{grid-template-columns:1fr}.best-bet-row,.shop-row{grid-template-columns:1fr 1fr!important}.best-bet-row>div:nth-child(3),.shop-row>div:nth-child(2){grid-column:1/-1}}
</style>
'''

def main():
    if not os.path.exists(HTML):
        raise SystemExit('missing docs/index.html')
    html=open(HTML,encoding='utf-8').read()
    html=re.sub(r'<script id="slip-optimizer-ui-v1">.*?</script>','',html,flags=re.S)
    html=re.sub(r'<style id="slip-optimizer-ui-v1-css">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',CSS+'\n</head>') if '</head>' in html else html.replace('</body>',CSS+'\n</body>')
    html=html.replace('</body>',PATCH+'\n</body>')
    open(HTML,'w',encoding='utf-8').write(html)
    print('✅ slip optimizer UI patch applied')

if __name__=='__main__':
    main()
