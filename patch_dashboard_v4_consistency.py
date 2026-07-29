from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path("docs/index.html")
STYLE_ID = "dashboard-consistency-recovery-style"
SCRIPT_ID = "dashboard-consistency-recovery-script"

STYLE = r'''<style id="dashboard-consistency-recovery-style">
.kpiWarning{color:#ffd166!important}.consistencyNote{margin:10px 0 0;color:#ffd166;font-size:12px}.consistencyOk{color:#00e39b}
</style>'''

SCRIPT = r'''<script id="dashboard-consistency-recovery-script">
(function(){
 const arr=v=>Array.isArray(v)?v:[];
 const summary=()=>DATA.master?.summary||{};
 const liveCount=()=>{
   try{
     if(typeof buildLiveCard==='function')return buildLiveCard().rows.length;
   }catch(e){}
   const b=arr(DATA.master?.best_bets);
   return b.length;
 };
 window.kpis=function(){
   const s=summary(),best=liveCount(),raw=Number(s.best_bets||0),mismatch=raw!==best;
   return `<div class="grid"><div class="card"><div class="label mono">Odds</div><div class="big mono">${s.sportsbook_markets?'Loaded':'Missing'}</div><div class="small mono">${S(s.sportsbook_markets,0)} markets</div></div><div class="card"><div class="label mono">Props</div><div class="big mono">${S(s.props,0)}</div><div class="small mono">player prop rows</div></div><div class="card"><div class="label mono">Stats</div><div class="big mono">${S(s.players,0)}</div><div class="small mono">players</div></div><div class="card"><div class="label mono">Best Bets</div><div class="big mono ${mismatch?'kpiWarning':''}">${best}</div><div class="small mono">active ranked plays</div>${mismatch?`<div class="consistencyNote mono">Raw summary ${raw} · live card ${best}</div>`:'<div class="consistencyNote consistencyOk mono">Summary synchronized</div>'}</div></div>`;
 };
 const oldRender=window.render;
 window.render=function(t='games'){
   oldRender(t);
   if(t==='games'||t==='health'){
     const root=document.getElementById('root');
     if(root&&root.innerHTML.includes('ranked plays'))root.innerHTML=root.innerHTML.replaceAll('ranked plays','active ranked plays');
   }
 };
 try{window.render('games')}catch(e){}
})();
</script>'''


def replace_or_insert(html: str, element_id: str, block: str, closing: str) -> str:
    pattern = re.compile(rf'<(?:style|script) id="{re.escape(element_id)}">.*?</(?:style|script)>', re.S)
    if pattern.search(html):
        return pattern.sub(block, html, count=1)
    return html.replace(closing, block + closing, 1)


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    html = replace_or_insert(html, STYLE_ID, STYLE, "</head>")
    html = replace_or_insert(html, SCRIPT_ID, SCRIPT, "</body>")
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Dashboard consistency recovery applied")


if __name__ == "__main__":
    main()
