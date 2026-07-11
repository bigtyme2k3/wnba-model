"""Replace the raw Results JSON tab with readable graded-bet, ROI, CLV and calibration cards."""
from __future__ import annotations
import json,re
from pathlib import Path

HTML=Path('docs/index.html')
PHASE5=Path('data/dashboard/wnba_phase5_learning.json')
BACKTEST=Path('data/dashboard/wnba_phase5_backtest.json')

def load(path):
 try:return json.load(path.open(encoding='utf-8')) if path.exists() else {}
 except Exception:return {}

def main():
 if not HTML.exists():return
 html=HTML.read_text(encoding='utf-8')
 payload=json.dumps({'phase5':load(PHASE5),'backtest':load(BACKTEST)},separators=(',',':'),ensure_ascii=False).replace('</','<\\/')
 marker=f'<script>window.WNBA_RESULTS_DATA={payload};</script>'
 html=re.sub(r'<script>window\.WNBA_RESULTS_DATA=.*?</script>','',html,flags=re.S)
 html=html.replace('</head>',marker+'</head>',1)
 fn=r'''function results(){let d=window.WNBA_RESULTS_DATA||{},p=d.phase5||{},perf=p.performance||{},cal=p.calibration||{},bt=d.backtest||{},graded=A(p.recent_graded||p.graded_bets||[]), fmtPct=v=>v===null||v===undefined?'—':(Number(v)*100).toFixed(1)+'%', outcomeClass=o=>o==='WIN'?'term-good':o==='LOSS'?'term-bad':'term-warn';let cards=`<div class="grid"><div class="card"><div class="label mono">Graded Bets</div><div class="big mono">${S(perf.graded,0)}</div></div><div class="card"><div class="label mono">Win Rate</div><div class="big mono">${fmtPct(perf.win_rate)}</div></div><div class="card"><div class="label mono">ROI</div><div class="big mono">${fmtPct(perf.roi)}</div></div><div class="card"><div class="label mono">Units</div><div class="big mono">${S(perf.units_profit,0)}</div></div><div class="card"><div class="label mono">Avg CLV</div><div class="big mono">${S(perf.average_clv,'—')}</div></div><div class="card"><div class="label mono">CLV Samples</div><div class="big mono">${S(perf.clv_samples,0)}</div></div><div class="card"><div class="label mono">Calibration</div><div class="big mono">${E(S(bt.learning_status,p.status||'collecting'))}</div></div><div class="card"><div class="label mono">Backtest Rows</div><div class="big mono">${S(bt.binary_rows,0)}</div></div></div>`;let rows=graded.map(r=>`<div class="gameCard"><div class="row"><div><b class="mono">${E(r.player)} ${E(r.stat)} ${E(r.signal)}</b><div class="small mono">${E(S(r.game))} · ${E(S(r.sportsbook))} ${E(S(r.american_odds))}</div></div><div class="score mono ${outcomeClass(r.outcome)}">${E(S(r.outcome))}</div></div><span class="chip mono">Line ${E(S(r.line))}</span><span class="chip mono">Actual ${E(S(r.actual))}</span><span class="chip mono">CLV ${E(S(r.clv))}</span></div>`).join('');let bins=A(cal.bins).filter(x=>x.n>0).map(x=>`<tr><td>${E(x.bin)}</td><td>${x.n}</td><td>${fmtPct(x.predicted_rate)}</td><td>${fmtPct(x.actual_rate)}</td><td>${x.wins}-${x.losses}</td></tr>`).join('');let stats=A(bt.performance_by_stat).slice(0,15).map(x=>`<tr><td>${E(x.stat)}</td><td>${x.n}</td><td>${fmtPct(x.win_rate)}</td><td>${fmtPct(x.roi)}</td><td>${S(x.units,0)}</td></tr>`).join('');return cards+`<div class="grid2"><div class="section"><h2 class="mono">Graded Bets</h2>${rows||'<div class="empty mono">Waiting for completed wagers.</div>'}</div><div class="section"><h2 class="mono">Calibration</h2><table><thead><tr><th>Confidence</th><th>N</th><th>Expected</th><th>Actual</th><th>Record</th></tr></thead><tbody>${bins}</tbody></table><h2 class="mono" style="margin-top:24px">Performance by Stat</h2><table><thead><tr><th>Stat</th><th>N</th><th>Win%</th><th>ROI</th><th>Units</th></tr></thead><tbody>${stats}</tbody></table></div></div>`}'''
 html=re.sub(r'function results\(\)\{.*?\nfunction health\(\)',fn+'\nfunction health()',html,flags=re.S)
 HTML.write_text(html,encoding='utf-8')
 print('Readable Results tab installed')
if __name__=='__main__':main()
