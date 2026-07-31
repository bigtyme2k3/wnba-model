from __future__ import annotations

import csv
import json
from pathlib import Path

HTML = Path("docs/index.html")
CURRENT = Path("data/dashboard/wnba_results_grading.json")
PERFORMANCE = Path("data/history/best_bets_performance.csv")
PHASE5 = Path("data/dashboard/wnba_phase5_learning.json")
STYLE_ID = "v4-results-ux-style"
SCRIPT_ID = "v4-results-ux-script"

STYLE = r'''<style id="v4-results-ux-style">
.resultsUxSummary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin-bottom:14px}.resultsUxKpi{border:1px solid var(--line);background:#081321;border-radius:14px;padding:13px}.resultsUxKpi strong{display:block;color:var(--green);font-size:23px;margin-top:4px}.resultsUxStatus{border:1px solid #2c405e;border-radius:14px;padding:14px;margin-bottom:14px}.resultsUxStatus.waiting{border-color:#7b6131;color:#f0c773}.resultsUxTabs{display:flex;gap:8px;overflow:auto;margin-bottom:12px}.resultsUxTab{border:1px solid #2a3d5d;background:#0a1423;color:#b9c8df;border-radius:999px;padding:8px 12px;font-weight:900;white-space:nowrap}.resultsUxTab.active{border-color:var(--green);color:var(--green);background:rgba(0,227,155,.1)}.resultsUxGrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.resultsUxCard{border:1px solid var(--line);background:#08101c;border-radius:14px;padding:13px}.resultsUxCard.win{border-color:rgba(0,227,155,.42)}.resultsUxCard.loss{border-color:rgba(255,77,103,.42)}.resultsUxCard.pending{border-color:rgba(255,209,102,.35)}.resultsUxTop{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.resultsUxOutcome{font-weight:950}.resultsUxOutcome.win{color:var(--green)}.resultsUxOutcome.loss{color:var(--red)}.resultsUxOutcome.push{color:var(--gold)}.resultsUxMeta{color:var(--muted);font-size:11px;margin-top:4px}.resultsUxChips{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.resultsUxEmpty{text-align:center;color:var(--muted);padding:35px;border:1px dashed #2a3d5d;border-radius:14px}.resultsUxTable{overflow:auto;border:1px solid var(--line);border-radius:14px}.resultsUxTable table{min-width:760px}.resultsUxBreakdown{display:grid;grid-template-columns:1fr 1fr;gap:14px}.resultsUxBar{height:8px;background:#172237;border-radius:999px;overflow:hidden;margin-top:6px}.resultsUxBar span{display:block;height:100%;background:linear-gradient(90deg,#ff6b81,#ffd166,#00e39b)}
@media(max-width:900px){.resultsUxSummary{grid-template-columns:1fr 1fr}.resultsUxGrid,.resultsUxBreakdown{grid-template-columns:1fr}}
</style>'''

SCRIPT = r'''<script id="v4-results-ux-script">(function(){
const DATASET=__DATASET__,A=v=>Array.isArray(v)?v:[],E2=v=>typeof window.E==='function'?window.E(v):String(v??''),N=v=>{const n=Number(v);return Number.isFinite(n)?n:0},money=v=>`${N(v)<0?'-':''}$${Math.abs(N(v)).toFixed(2)}`,pct=v=>`${(N(v)*(Math.abs(N(v))<=1?100:1)).toFixed(1)}%`;
const state={view:'overview'};
const rows=()=>A(DATASET.rows),graded=()=>rows().filter(r=>['WIN','LOSS','PUSH'].includes(String(r.outcome||'').toUpperCase())),pending=()=>rows().filter(r=>String(r.outcome||'').toUpperCase()==='PENDING');
const summary=()=>{const g=graded(),w=g.filter(r=>r.outcome==='WIN').length,l=g.filter(r=>r.outcome==='LOSS').length,p=g.filter(r=>r.outcome==='PUSH').length,profit=g.reduce((s,r)=>s+N(r.profit_units??r.profit_loss),0),stake=g.reduce((s,r)=>s+N(r.stake_units??r.stake),0),dec=w+l;return{w,l,p,graded:g.length,pending:pending().length,winRate:dec?w/dec:0,profit,roi:stake?profit/stake:0,stake}};
const card=r=>{const o=String(r.outcome||'PENDING').toUpperCase(),cls=o.toLowerCase(),player=r.player_name||r.player||'Unknown player',stat=r.market||r.stat||'',side=r.side||r.signal||'',line=r.line??'-',actual=r.actual??'-';return `<div class="resultsUxCard ${cls}"><div class="resultsUxTop"><div><b>${E2(player)} ${E2(side)} ${E2(stat)} ${E2(line)}</b><div class="resultsUxMeta mono">${E2(r.slate_date||r.date||'')} · ${E2(r.game||'')} · ${E2(r.sportsbook||'')}</div></div><div class="resultsUxOutcome ${cls}">${E2(o)}</div></div><div class="resultsUxChips"><span class="chip mono">Actual ${E2(actual)}</span><span class="chip mono">Odds ${E2(r.odds??r.american_odds??'-')}</span><span class="chip mono">Stake ${E2(r.stake_units??r.stake??1)}u</span><span class="chip mono">P/L ${E2(r.profit_units??r.profit_loss??'-')}</span>${r.line_clv!==''&&r.line_clv!=null?`<span class="chip mono">CLV ${E2(r.line_clv)}</span>`:''}</div></div>`};
const breakdown=()=>{const byStat=new Map();for(const r of graded()){const k=r.market||r.stat||'Other',x=byStat.get(k)||{n:0,w:0,p:0};x.n++;x.w+=r.outcome==='WIN';x.p+=N(r.profit_units??r.profit_loss);byStat.set(k,x)}const body=[...byStat.entries()].sort((a,b)=>b[1].n-a[1].n).map(([k,x])=>`<tr><td>${E2(k)}</td><td>${x.n}</td><td>${x.n?((x.w/x.n)*100).toFixed(1):'0.0'}%</td><td>${x.p.toFixed(2)}u</td></tr>`).join('');return `<div class="resultsUxTable"><table><thead><tr><th>Stat</th><th>N</th><th>Win%</th><th>P/L</th></tr></thead><tbody>${body||'<tr><td colspan="4">No graded history yet.</td></tr>'}</tbody></table></div>`};
window.setResultsUxView=v=>{state.view=v;window.render('results')};
window.results=function(){const s=summary(),current=DATASET.current||{},waiting=String(current.status||'').includes('waiting');let body='';if(state.view==='graded')body=`<div class="resultsUxGrid">${graded().slice(0,200).map(card).join('')||'<div class="resultsUxEmpty mono">No graded bets yet.</div>'}</div>`;else if(state.view==='pending')body=`<div class="resultsUxGrid">${pending().slice(0,200).map(card).join('')||'<div class="resultsUxEmpty mono">No pending bets.</div>'}</div>`;else body=`<div class="resultsUxBreakdown"><div><h3 class="mono">Performance by Stat</h3>${breakdown()}</div><div><h3 class="mono">Current Slate</h3><div class="resultsUxStatus ${waiting?'waiting':''}"><b class="mono">${E2(String(current.status||'No current grading').replaceAll('_',' '))}</b><div class="resultsUxMeta mono">Target ${E2(current.target_date||'-')} · Actual source ${E2(current.actual_source||'not available yet')}</div></div><div class="resultsUxCard"><div class="row"><span>Archived predictions</span><b>${E2(current.archived_predictions||0)}</b></div><div class="row"><span>Actual rows loaded</span><b>${E2(current.actual_rows||0)}</b></div><div class="row"><span>Graded this run</span><b>${E2(current.summary?.graded_this_run||0)}</b></div></div></div></div>`;return `<div class="section"><h2 class="mono">Results & Performance</h2><div class="small mono">Historical graded recommendations plus the current slate grading status.</div><div class="resultsUxSummary"><div class="resultsUxKpi"><span>Record</span><strong>${s.w}-${s.l}-${s.p}</strong></div><div class="resultsUxKpi"><span>Win rate</span><strong>${pct(s.winRate)}</strong></div><div class="resultsUxKpi"><span>Graded</span><strong>${s.graded}</strong></div><div class="resultsUxKpi"><span>Pending</span><strong>${s.pending}</strong></div><div class="resultsUxKpi"><span>P/L</span><strong>${money(s.profit)}</strong></div><div class="resultsUxKpi"><span>ROI</span><strong>${pct(s.roi)}</strong></div></div><div class="resultsUxTabs"><button class="resultsUxTab ${state.view==='overview'?'active':''}" onclick="setResultsUxView('overview')">Overview</button><button class="resultsUxTab ${state.view==='graded'?'active':''}" onclick="setResultsUxView('graded')">Graded Bets</button><button class="resultsUxTab ${state.view==='pending'?'active':''}" onclick="setResultsUxView('pending')">Pending</button></div>${body}</div>`};
window.WNBA_RESULTS_UX={version:'2.0',rows:rows().length};
})();</script>'''


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def replace_block(html: str, start: str, end: str, replacement: str) -> str:
    s = html.find(start)
    if s < 0:
        return html
    e = html.find(end, s)
    if e < 0:
        return html
    return html[:s] + replacement.strip() + html[e + len(end):]


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    payload = {
        "current": load_json(CURRENT),
        "rows": load_csv(PERFORMANCE),
        "phase5": load_json(PHASE5),
    }
    html = HTML.read_text(encoding="utf-8")
    style = STYLE
    script = SCRIPT.replace("__DATASET__", json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/"))
    if f'id="{STYLE_ID}"' in html:
        html = replace_block(html, f'<style id="{STYLE_ID}">', '</style>', style)
    else:
        html = html.replace('</head>', style + '</head>', 1)
    if f'id="{SCRIPT_ID}"' in html:
        html = replace_block(html, f'<script id="{SCRIPT_ID}">', '</script>', script)
    else:
        html = html.replace('</body>', script + '</body>', 1)
    HTML.write_text(html, encoding="utf-8")
    print(f"Results UX applied with {len(payload['rows'])} historical rows")


if __name__ == "__main__":
    main()
