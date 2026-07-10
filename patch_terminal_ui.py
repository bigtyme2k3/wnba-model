"""Inject or replace the intelligence terminal in docs/index.html."""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any

HTML_PATH = "docs/index.html"
DATA_PATH = "data/dashboard/terminal_ui.json"
START = "<!-- WNBA_TERMINAL_UI_PATCH_START -->"
END = "<!-- WNBA_TERMINAL_UI_PATCH_END -->"
OLD = "<!-- WNBA_TERMINAL_UI_PATCH -->"


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def load_data() -> dict[str, Any]:
    try:
        with open(DATA_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
        return clean(value) if isinstance(value, dict) else {}
    except Exception as exc:
        print(f"Warning: terminal bundle unavailable: {exc}")
        return {}


def script(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    return f'''
{START}
<style>
#terminal-ui{{margin:34px 16px 24px;padding:18px;border:1px solid #1f2a44;border-radius:22px;background:linear-gradient(135deg,#09111f,#0b0b13);color:#e5e7eb;font-family:Courier New,monospace}}
#terminal-ui h2{{letter-spacing:.08em;margin:0 0 8px}}
.term-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}}
.term-card{{background:#0f172a;border:1px solid #26334f;border-radius:16px;padding:14px;min-height:80px}}
.term-label{{font-size:12px;letter-spacing:.16em;color:#94a3b8;text-transform:uppercase}}
.term-value{{font-size:28px;font-weight:900;color:#34d399;margin-top:8px}}
.term-list{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}}
.term-row{{background:#0b1020;border:1px solid #26334f;border-radius:14px;padding:12px;min-height:48px}}
.term-score{{float:right;color:#34d399;font-size:22px;font-weight:900;margin-left:10px}}
.term-bad{{color:#f87171}}.term-warn{{color:#facc15}}.term-good{{color:#34d399}}
.term-section-title{{margin-top:20px;font-size:18px;font-weight:900;letter-spacing:.12em}}
.term-empty{{color:#94a3b8}}
.term-hidden{{display:none!important}}
@media(max-width:900px){{.term-grid{{grid-template-columns:1fr 1fr}}.term-list{{grid-template-columns:1fr}}}}
</style>
<section id="terminal-ui">
  <h2>WNBA Intelligence Terminal</h2>
  <div class="term-label">Final Decisions · Portfolio · Monte Carlo · Market · Source Health</div>
  <div class="term-grid" id="terminalMetrics"></div>
  <div id="terminalFinalSection"><div class="term-section-title">Final Decisions</div><div class="term-list" id="terminalFinal"></div></div>
  <div id="terminalCardSection"><div class="term-section-title">Top Betting Card</div><div class="term-list" id="terminalCard"></div></div>
  <div class="term-section-title">Validation Guardrails</div>
  <div class="term-list" id="terminalGuards"></div>
  <div id="terminalSourcesSection"><div class="term-section-title">Source Health</div><div class="term-list" id="terminalSources"></div></div>
</section>
<script>
(function(){{
  const data={payload};
  const safe=(v,d='—')=>v===undefined||v===null||v===''?d:v;
  const num=v=>Number.isFinite(Number(v))?Number(v):0;
  const summary=data.terminal_summary||{{}};
  const decision=data.decision_final||{{}};
  const portfolio=data.portfolio_v2||{{}};
  const health=data.source_health||{{}};
  const mc=data.monte_carlo||{{}};
  const market=data.market_engine||{{}};
  const finalRows=decision.top_decisions||data.consensus?.top_consensus||[];
  const card=portfolio.recommended_card||decision.portfolio_card||[];
  const sourceTotal=num(summary.source_total||health.summary?.sources);
  const metrics=[
    ['FINAL BETS',num(summary.final_bets||summary.bet_count)],
    ['FINAL LEANS',num(summary.final_leans||summary.lean_count)],
    ['MC ROWS',num(summary.mc_rows||mc.summary?.rows)],
    ['MC 60%+',num(summary.mc_prob_60_plus||mc.summary?.prob_60_plus)],
    ['CARD SIZE',num(summary.portfolio_card_size||card.length)],
    ['CARD STAKE','$'+num(summary.portfolio_total_stake)],
    ['MARKETS',num(summary.market_rows||market.summary?.markets||market.summary?.rows)],
    ['SOURCE OK',sourceTotal?`${{num(summary.source_ok)}}/${{sourceTotal}}`:num(summary.source_ok)]
  ];
  document.getElementById('terminalMetrics').innerHTML=metrics.map(x=>`<div class="term-card"><div class="term-label">${{x[0]}}</div><div class="term-value">${{x[1]}}</div></div>`).join('');

  const finalEl=document.getElementById('terminalFinal');
  if(finalRows.length){{
    finalEl.innerHTML=finalRows.slice(0,12).map(r=>`<div class="term-row"><span class="term-score">${{safe(r.final_score,r.consensus_score)}}</span><b>${{safe(r.final_action,r.recommendation)}} · ${{safe(r.player)}} ${{safe(r.stat)}} ${{safe(r.signal)}}</b><br><span class="term-label">${{safe(r.game)}} · Line ${{safe(r.line)}} · MC ${{r.simulation_probability!=null?Math.round(Number(r.simulation_probability)*100)+'%':'—'}} · Move ${{safe(r.market_move)}} · ${{safe(r.decision_reason,'')}}</span></div>`).join('');
  }}else{{document.getElementById('terminalFinalSection').classList.add('term-hidden')}}

  const cardEl=document.getElementById('terminalCard');
  if(card.length){{
    cardEl.innerHTML=card.slice(0,10).map(r=>`<div class="term-row"><span class="term-score">$${{safe(r.recommended_stake,0)}}</span><b>${{safe(r.player)}} ${{safe(r.stat)}} ${{safe(r.signal)}}</b><br><span class="term-label">${{safe(r.game)}} · Portfolio ${{safe(r.portfolio_score)}} · Consensus ${{safe(r.consensus_score)}} · Risk ${{safe(r.risk_band)}}</span></div>`).join('');
  }}else{{document.getElementById('terminalCardSection').classList.add('term-hidden')}}

  const oddsStatus=health.sources?.odds_layer?.status||'missing';
  const guards=[
    ['Odds Layer',oddsStatus,oddsStatus==='ok'?'term-good':'term-warn'],
    ['Monte Carlo Rows',num(mc.summary?.rows),num(mc.summary?.rows)>0?'term-good':'term-bad'],
    ['Final Decisions',num(decision.summary?.rows),num(decision.summary?.rows)>0?'term-good':'term-bad'],
    ['Market Snapshots',num(market.summary?.markets||market.summary?.rows),num(market.summary?.markets||market.summary?.rows)>0?'term-good':'term-warn'],
    ['Source Health',sourceTotal?`${{num(health.summary?.ok_or_optional)}}/${{sourceTotal}}`:'—',num(health.summary?.degraded_or_missing)<=2?'term-good':'term-warn']
  ];
  document.getElementById('terminalGuards').innerHTML=guards.map(g=>`<div class="term-row"><b>${{g[0]}}</b><span class="term-score ${{g[2]}}">${{g[1]}}</span></div>`).join('');

  const sources=health.sources||{{}};
  const sourceRows=Object.values(sources);
  if(sourceRows.length){{
    document.getElementById('terminalSources').innerHTML=sourceRows.map(s=>{{const st=s.status||'missing';const cls=st==='ok'||st==='optional'?'term-good':st==='degraded'?'term-warn':'term-bad';return `<div class="term-row"><b>${{safe(s.label)}}</b><span class="term-score ${{cls}}">${{st}}</span></div>`}}).join('');
  }}else{{document.getElementById('terminalSourcesSection').classList.add('term-hidden')}}
}})();
</script>
{END}
'''


def main() -> None:
    if not os.path.exists(HTML_PATH):
        print("No docs/index.html found")
        return
    html = open(HTML_PATH, encoding="utf-8").read()
    block = script(load_data())
    html = re.sub(re.escape(START) + r".*?" + re.escape(END), block, html, flags=re.S)
    if START not in html:
        if OLD in html:
            html = re.sub(re.escape(OLD) + r".*?</script>", block, html, count=1, flags=re.S)
        elif "</body>" in html:
            html = html.replace("</body>", block + "\n</body>", 1)
        else:
            html += block
    open(HTML_PATH, "w", encoding="utf-8").write(html)
    print(f"Terminal UI embedded from {DATA_PATH}")


if __name__ == "__main__":
    main()
