"""Injects or replaces the professional terminal panel in docs/index.html."""
from __future__ import annotations
import os, re
HTML_PATH="docs/index.html"
START="<!-- WNBA_TERMINAL_UI_PATCH_START -->"
END="<!-- WNBA_TERMINAL_UI_PATCH_END -->"
OLD="<!-- WNBA_TERMINAL_UI_PATCH -->"
SCRIPT=f'''
{START}
<style>
#terminal-ui{{margin:24px 16px;padding:18px;border:1px solid #1f2a44;border-radius:22px;background:linear-gradient(135deg,#09111f,#0b0b13);color:#e5e7eb;font-family:Courier New,monospace}}
#terminal-ui h2{{letter-spacing:.08em;margin:0 0 8px}}
.term-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}}
.term-card{{background:#0f172a;border:1px solid #26334f;border-radius:16px;padding:14px;min-height:80px}}
.term-label{{font-size:12px;letter-spacing:.18em;color:#94a3b8;text-transform:uppercase}}
.term-value{{font-size:28px;font-weight:900;color:#34d399;margin-top:8px}}
.term-list{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}}
.term-row{{background:#0b1020;border:1px solid #26334f;border-radius:14px;padding:12px}}
.term-score{{float:right;color:#34d399;font-size:22px;font-weight:900}}
.term-bad{{color:#f87171}} .term-warn{{color:#facc15}} .term-good{{color:#34d399}}
.term-section-title{{margin-top:20px;font-size:18px;font-weight:900;letter-spacing:.12em}}
@media(max-width:900px){{.term-grid{{grid-template-columns:1fr 1fr}}.term-list{{grid-template-columns:1fr}}}}
</style>
<section id="terminal-ui">
  <h2>WNBA Intelligence Terminal</h2>
  <div class="term-label">Final Decisions · Portfolio · Monte Carlo · Market · Source Health</div>
  <div class="term-grid" id="terminalMetrics"></div>
  <div class="term-section-title">Final Decisions</div>
  <div class="term-list" id="terminalFinal"></div>
  <div class="term-section-title">Top Betting Card</div>
  <div class="term-list" id="terminalCard"></div>
  <div class="term-section-title">Validation Guardrails</div>
  <div class="term-list" id="terminalGuards"></div>
  <div class="term-section-title">Source Health</div>
  <div class="term-list" id="terminalSources"></div>
</section>
<script>
(async function(){{
  const safe=(v,d='—')=>v===undefined||v===null||v===''?d:v;
  async function j(path){{try{{const r=await fetch(path+'?v='+Date.now());return await r.json();}}catch(e){{return {{}}}}}}
  const data=await j('data/dashboard/terminal_ui.json');
  const summary=data.terminal_summary||{{}};
  const decision=data.decision_final||{{}};
  const portfolio=data.portfolio_v2||{{}};
  const health=data.source_health||{{}};
  const mc=data.monte_carlo||{{}};
  const market=data.market_engine||{{}};
  const finalRows=decision.top_decisions||data.consensus?.top_consensus||[];
  const card=portfolio.recommended_card||decision.portfolio_card||[];
  document.getElementById('terminalMetrics').innerHTML=[
    ['FINAL BETS', summary.final_bets ?? summary.bet_count ?? 0],
    ['FINAL LEANS', summary.final_leans ?? summary.lean_count ?? 0],
    ['MC ROWS', summary.mc_rows||0],
    ['MC 60%+', summary.mc_prob_60_plus||0],
    ['CARD SIZE', summary.portfolio_card_size||0],
    ['CARD STAKE', '$'+safe(summary.portfolio_total_stake,0)],
    ['MARKETS', summary.market_rows||0],
    ['SOURCE OK', summary.source_ok||0]
  ].map(x=>`<div class="term-card"><div class="term-label">${{x[0]}}</div><div class="term-value">${{x[1]}}</div></div>`).join('');
  document.getElementById('terminalFinal').innerHTML=(finalRows.slice(0,12).map(r=>`<div class="term-row"><span class="term-score">${{safe(r.final_score,r.consensus_score)}}</span><b>${{safe(r.final_action,r.recommendation)}} · ${{safe(r.player)}} ${{safe(r.stat)}} ${{safe(r.signal)}}</b><br><span class="term-label">${{safe(r.game)}} · Line ${{safe(r.line)}} · MC ${{safe(r.simulation_probability)}} · Move ${{safe(r.market_move)}} · ${{safe(r.decision_reason,'')}}</span></div>`).join(''))||'<div class="term-row">No final decisions yet.</div>';
  document.getElementById('terminalCard').innerHTML=(card.slice(0,10).map(r=>`<div class="term-row"><span class="term-score">$${{safe(r.recommended_stake,0)}}</span><b>${{safe(r.player)}} ${{safe(r.stat)}} ${{safe(r.signal)}}</b><br><span class="term-label">${{safe(r.game)}} · Portfolio ${{safe(r.portfolio_score)}} · Consensus ${{safe(r.consensus_score)}} · Risk ${{safe(r.risk_band)}}</span></div>`).join(''))||'<div class="term-row">No portfolio card yet.</div>';
  const guards=[];
  const oddsStatus=data.source_health?.sources?.odds_layer?.status || 'unknown';
  guards.push(['Odds Layer', oddsStatus, oddsStatus==='ok'?'term-good':'term-warn']);
  guards.push(['Monte Carlo Rows', mc.summary?.rows||0, (mc.summary?.rows||0)>0?'term-good':'term-bad']);
  guards.push(['Final Decisions', decision.summary?.rows||0, (decision.summary?.rows||0)>0?'term-good':'term-bad']);
  guards.push(['Market Snapshots', market.summary?.markets||0, (market.summary?.markets||0)>0?'term-good':'term-warn']);
  guards.push(['Source Health', `${{health.summary?.ok_or_optional||0}}/${{health.summary?.sources||0}}`, (health.summary?.degraded_or_missing||0)<=2?'term-good':'term-warn']);
  document.getElementById('terminalGuards').innerHTML=guards.map(g=>`<div class="term-row"><b>${{g[0]}}</b><span class="term-score ${{g[2]}}">${{g[1]}}</span></div>`).join('');
  const sources=health.sources||{{}};
  document.getElementById('terminalSources').innerHTML=Object.values(sources).map(s=>{{const st=s.status||'missing'; const cls=st==='ok'||st==='optional'?'term-good':st==='degraded'?'term-warn':'term-bad'; return `<div class="term-row"><b>${{safe(s.label)}}</b><span class="term-score ${{cls}}">${{st}}</span></div>`}}).join('')||'<div class="term-row">No source health yet.</div>';
}})();
</script>
{END}
'''
def main():
    if not os.path.exists(HTML_PATH):
        print('No docs/index.html found'); return
    html=open(HTML_PATH,encoding='utf-8').read()
    html=re.sub(re.escape(START)+r'.*?'+re.escape(END), SCRIPT, html, flags=re.S)
    if START not in html:
        if OLD in html:
            html=re.sub(re.escape(OLD)+r'.*?</script>', SCRIPT, html, count=1, flags=re.S)
        elif '</body>' in html:
            html=html.replace('</body>', SCRIPT+'\n</body>',1)
        else:
            html+=SCRIPT
    open(HTML_PATH,'w',encoding='utf-8').write(html)
    print('Terminal UI upgraded')
if __name__=='__main__': main()
