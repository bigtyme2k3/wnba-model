"""
patch_terminal_ui.py
--------------------
Injects a professional terminal panel into docs/index.html.
The patch is intentionally additive and safe: it loads dashboard JSON files via
fetch and appends a terminal section without replacing the existing dashboard.
"""
from __future__ import annotations

import os

HTML_PATH="docs/index.html"
MARK="<!-- WNBA_TERMINAL_UI_PATCH -->"

SCRIPT=f'''
{MARK}
<style>
#terminal-ui{{margin:24px 16px;padding:18px;border:1px solid #1f2a44;border-radius:22px;background:linear-gradient(135deg,#09111f,#0b0b13);color:#e5e7eb;font-family:Courier New,monospace}}
#terminal-ui h2{{letter-spacing:.08em;margin:0 0 8px}}
.term-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}}
.term-card{{background:#0f172a;border:1px solid #26334f;border-radius:16px;padding:14px;min-height:80px}}
.term-label{{font-size:12px;letter-spacing:.18em;color:#94a3b8;text-transform:uppercase}}
.term-value{{font-size:28px;font-weight:900;color:#34d399;margin-top:8px}}
.term-list{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.term-row{{background:#0b1020;border:1px solid #26334f;border-radius:14px;padding:12px}}
.term-score{{float:right;color:#34d399;font-size:22px;font-weight:900}}
.term-bad{{color:#f87171}} .term-warn{{color:#facc15}} .term-good{{color:#34d399}}
@media(max-width:900px){{.term-grid{{grid-template-columns:1fr 1fr}}.term-list{{grid-template-columns:1fr}}}}
</style>
<section id="terminal-ui">
  <h2>WNBA Intelligence Terminal</h2>
  <div class="term-label">Consensus · Matchups · Source Health · Self Learning</div>
  <div class="term-grid" id="terminalMetrics"></div>
  <div class="term-list" id="terminalTop"></div>
  <div class="term-list" id="terminalSources" style="margin-top:12px"></div>
</section>
<script>
(async function(){{
  const safe=(v,d='—')=>v===undefined||v===null||v===''?d:v;
  async function j(path){{try{{const r=await fetch(path+'?v='+Date.now());return await r.json();}}catch(e){{return {{}}}}}}
  const data=await j('data/dashboard/terminal_ui.json');
  const summary=data.terminal_summary||{{}};
  const cons=data.consensus||{{}};
  const health=data.source_health||{{}};
  const learning=data.learning||{{}};
  const top=cons.top_consensus||[];
  document.getElementById('terminalMetrics').innerHTML=[
    ['BET SIGNALS', summary.bet_count||0],
    ['LEAN SIGNALS', summary.lean_count||0],
    ['SOURCE OK', summary.source_ok||0],
    ['HISTORY ROWS', summary.history_records||0],
    ['GRADED ROWS', learning.graded_records||0],
    ['TARGET DATE', data.target_date||'—'],
    ['TOP SCORE', top[0]?.consensus_score||'—'],
    ['TOP PLAY', (top[0]?.player||'—')+' '+(top[0]?.stat||'')]
  ].map(x=>`<div class="term-card"><div class="term-label">${{x[0]}}</div><div class="term-value">${{x[1]}}</div></div>`).join('');
  document.getElementById('terminalTop').innerHTML=(top.slice(0,10).map(r=>`<div class="term-row"><span class="term-score">${{safe(r.consensus_score)}}</span><b>${{safe(r.player)}} ${{safe(r.stat)}} ${{safe(r.signal)}}</b><br><span class="term-label">${{safe(r.game)}} · Line ${{safe(r.line)}} · Agreement ${{safe(r.engine_agreement)}} · ${{safe(r.recommendation)}}</span></div>`).join(''))||'<div class="term-row">No consensus rows yet.</div>';
  const sources=health.sources||{{}};
  document.getElementById('terminalSources').innerHTML=Object.values(sources).map(s=>{{const st=s.status||'missing'; const cls=st==='ok'||st==='optional'?'term-good':st==='degraded'?'term-warn':'term-bad'; return `<div class="term-row"><b>${{safe(s.label)}}</b><span class="term-score ${{cls}}">${{st}}</span></div>`}}).join('')||'<div class="term-row">No source health yet.</div>';
}})();
</script>
'''

def main():
    if not os.path.exists(HTML_PATH):
        print("No docs/index.html found")
        return
    html=open(HTML_PATH,encoding="utf-8").read()
    if MARK in html:
        print("Terminal UI already patched")
        return
    if "</body>" in html:
        html=html.replace("</body>", SCRIPT+"\n</body>",1)
    else:
        html+=SCRIPT
    open(HTML_PATH,"w",encoding="utf-8").write(html)
    print("✅ Terminal UI patch applied")

if __name__=="__main__": main()
