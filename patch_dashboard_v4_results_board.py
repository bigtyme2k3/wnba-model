from __future__ import annotations

import json
from pathlib import Path

DASHBOARD = Path("docs/index.html")
RESULTS = Path("data/dashboard/wnba_results_grading.json")
STYLE_MARKER = "sprint25-results-board-style"
SCRIPT_MARKER = "sprint25-results-board-script"

STYLE = r'''<style id="sprint25-results-board-style">
.resultsKpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin:14px 0}.resultsKpi{border:1px solid var(--line);background:#081321;border-radius:14px;padding:13px}.resultsKpi b{display:block;color:var(--green);font-size:24px}.resultsStatus{border:1px solid #2c405e;border-radius:14px;padding:14px;margin:12px 0}.resultsStatus.waiting{border-color:#7b6131;color:#f0c773}.missingActuals{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.missingRow{border:1px solid var(--line);background:#08101c;border-radius:12px;padding:12px}.resultsNote{color:var(--muted);font-size:12px;margin-top:10px}@media(max-width:900px){.resultsKpis{grid-template-columns:1fr 1fr}.missingActuals{grid-template-columns:1fr}}
</style>'''

SCRIPT = r'''<script id="sprint25-results-board-script">
(function(){
 const GRADING=__RESULTS__;
 const n=v=>{const x=Number(v);return Number.isFinite(x)?x:0};
 const money=v=>{const x=n(v);return `${x<0?'-':''}$${Math.abs(x).toFixed(2)}`};
 const pct=v=>`${n(v).toFixed(1)}%`;
 const cleanStatus=v=>String(v||'unknown').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
 const uniqueMissing=()=>{const map=new Map();A(GRADING?.missing_actuals).forEach(x=>{const key=`${x.player||'Unknown'}|${x.reason||'Actual unavailable'}`;if(!map.has(key))map.set(key,x)});return [...map.values()];};
 window.results=function(){
   const r=GRADING||{},s=r.summary||{},missing=uniqueMissing(),waiting=String(r.status||'').includes('waiting');
   return `<div class="section"><h2 class="mono">Results & Grading</h2><div class="small mono">Archived recommendations remain pending until verified game and player actuals are available.</div>
   <div class="resultsStatus ${waiting?'waiting':''}"><b class="mono">${E(cleanStatus(r.status))}</b><div class="small mono">Target date ${E(r.target_date||'-')} · Actual source ${E(r.actual_source||'not available yet')}</div></div>
   <div class="resultsKpis"><div class="resultsKpi mono"><span>Record</span><b>${E(n(s.win))}-${E(n(s.loss))}-${E(n(s.push))}</b></div><div class="resultsKpi mono"><span>Win rate</span><b>${E(pct(s.win_rate))}</b></div><div class="resultsKpi mono"><span>Pending</span><b>${E(n(s.pending))}</b></div><div class="resultsKpi mono"><span>Graded run</span><b>${E(n(s.graded_this_run))}</b></div><div class="resultsKpi mono"><span>P/L</span><b>${E(money(s.profit_loss))}</b></div><div class="resultsKpi mono"><span>ROI</span><b>${E(pct(s.roi))}</b></div></div>
   <div class="grid2"><div><h3 class="mono">Archive</h3><div class="gameCard"><div class="row"><span>Archived predictions</span><b class="mono">${E(n(r.archived_predictions))}</b></div><div class="row"><span>Actual rows loaded</span><b class="mono">${E(n(r.actual_rows))}</b></div><div class="row"><span>Total stake</span><b class="mono">${E(money(s.total_stake))}</b></div></div></div><div><h3 class="mono">Missing Actuals</h3><div class="missingActuals">${missing.slice(0,12).map(x=>`<div class="missingRow"><b>${E(x.player||'Unknown player')}</b><div class="small mono">${E(x.reason||'Actual unavailable')}</div></div>`).join('')||'<div class="empty mono">No missing actuals.</div>'}</div>${missing.length>12?`<div class="resultsNote mono">${E(missing.length-12)} more unique missing-player records are retained in the grading artifact.</div>`:''}</div></div></div>`;
 };
 try{render('games')}catch(e){}
})();
</script>'''


def load_results() -> dict:
    try:
        value = json.loads(RESULTS.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        print(f"[warn] unable to load results grading: {exc}")
        return {}


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    if STYLE_MARKER not in html:
        html = html.replace("</head>", STYLE + "</head>", 1)
    if SCRIPT_MARKER not in html:
        script = SCRIPT.replace("__RESULTS__", json.dumps(load_results(), separators=(",", ":"), ensure_ascii=False))
        html = html.replace("</body>", script + "</body>", 1)
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Sprint 25 Results grading board applied")


if __name__ == "__main__":
    main()
