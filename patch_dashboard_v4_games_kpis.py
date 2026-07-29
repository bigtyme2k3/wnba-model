from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path("docs/index.html")
SCRIPT_ID = "dashboard-games-kpi-fix-script"

SCRIPT = r'''<script id="dashboard-games-kpi-fix-script">
(function(){
 const arr=v=>Array.isArray(v)?v:[];
 const num=v=>{const x=Number(v);return Number.isFinite(x)?x:0};
 const activeBestCount=()=>{
   if(typeof window.dashboardActiveBestBets==='function')return arr(window.dashboardActiveBestBets()).length;
   return arr(DATA.cross_market?.portfolio).length;
 };
 const activeUnits=()=>{
   const rows=typeof window.dashboardActiveBestBets==='function'?arr(window.dashboardActiveBestBets()):arr(DATA.cross_market?.portfolio);
   return rows.reduce((s,r)=>s+num(r.recommended_units_final??r.recommended_units),0);
 };
 window.kpis=function(){
   const s=DATA.master?.summary||{};
   const today=arr(DATA.today_games).length;
   const active=activeBestCount();
   const units=activeUnits();
   return `<div class="grid">
     <div class="card"><div class="label mono">Odds</div><div class="big mono">${s.sportsbook_markets?'Loaded':'Missing'}</div><div class="small mono">${S(s.sportsbook_markets,0)} markets</div></div>
     <div class="card"><div class="label mono">Props</div><div class="big mono">${S(s.props,0)}</div><div class="small mono">player prop rows</div></div>
     <div class="card"><div class="label mono">Games Today</div><div class="big mono">${today}</div><div class="small mono">scheduled matchups</div></div>
     <div class="card"><div class="label mono">Players</div><div class="big mono">${S(s.players,0)}</div><div class="small mono">tracked players</div></div>
     <div class="card"><div class="label mono">Active Recommendations</div><div class="big mono">${active}</div><div class="small mono">BET/LEAN plays · ${units.toFixed(2)} units</div></div>
   </div>`;
 };
 try{render('games')}catch(e){}
})();
</script>'''


def replace_or_insert(html: str, element_id: str, block: str, closing: str) -> str:
    pattern = re.compile(rf'<script id="{re.escape(element_id)}">.*?</script>', re.S)
    if pattern.search(html):
        return pattern.sub(block, html, count=1)
    return html.replace(closing, block + closing, 1)


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    html = replace_or_insert(html, SCRIPT_ID, SCRIPT, "</body>")
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Games tab KPI fix applied")


if __name__ == "__main__":
    main()
