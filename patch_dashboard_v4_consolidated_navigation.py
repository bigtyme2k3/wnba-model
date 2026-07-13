from __future__ import annotations

import json
from pathlib import Path

HTML = Path("docs/index.html")
PERFORMANCE = Path("data/dashboard/wnba_alt_performance.json")

CSS = r'''
<style id="v4-consolidated-navigation-style">
.navSectionNote{margin:0 0 14px;color:#7e8ba3;font-size:12px}
.modelCenterGrid{display:grid;grid-template-columns:1fr;gap:16px}
.performanceJump{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}
.performanceJump button{border:1px solid #263854;background:#08101c;color:#cbd7f1;border-radius:999px;padding:8px 12px;font-weight:800}
@media(min-width:1100px){.modelCenterGrid{grid-template-columns:1fr 1fr}}
</style>
'''

SCRIPT = r'''
<script id="v4-consolidated-navigation-script">
(function(){
  const NAV=[['today','Today'],['props','Player Props'],['alt','ALT Streaks'],['best','Best Bets'],['performance','Performance'],['model','Model Center']];
  function safe(fn,fallback=''){try{return typeof fn==='function'?fn():fallback}catch(err){return `<div class="section"><div class="empty mono">Section unavailable: ${String(err)}</div></div>`}}
  function setChrome(view){const tabs=document.getElementById('tabs');if(tabs)tabs.innerHTML=NAV.map(([id,label])=>`<button class="tab ${id===view?'a':''}" data-view="${id}" onclick="render('${id}')">${label}</button>`).join('');const sub=document.getElementById('sub');if(sub&&typeof S==='function'&&typeof fmt==='function')sub.textContent=`Slate ${S(DATA.master?.target_date,'-')} · Updated ${fmt(DATA.generated_at_utc)}`;const badge=document.getElementById('badge');if(badge&&typeof S==='function'&&typeof summary==='function')badge.textContent=`V4 · ${S(summary().sportsbook_markets,0)} odds markets`}
  function performanceView(){const altPerf=safe(window.altPerformance,'<div class="section"><div class="empty mono">ALT Performance is collecting data.</div></div>');const resultView=safe(window.results||results);const portfolioView=safe(window.portfolio||portfolio);return `<div class="section"><h2 class="mono">Performance Center</h2><div class="navSectionNote mono">Results, ALT validation, certified CLV, ROI, and bankroll allocation in one place.</div><div class="performanceJump"><button onclick="document.getElementById('alt-performance-block')?.scrollIntoView({behavior:'smooth'})">ALT Performance</button><button onclick="document.getElementById('results-block')?.scrollIntoView({behavior:'smooth'})">Results</button><button onclick="document.getElementById('portfolio-block')?.scrollIntoView({behavior:'smooth'})">Portfolio</button></div></div><div id="alt-performance-block">${altPerf}</div><div id="results-block">${resultView}</div><div id="portfolio-block">${portfolioView}</div>`}
  function modelView(){const pointsView=safe(window.pointsProjection,'<div class="section"><div class="empty mono">Points Projection v2 unavailable.</div></div>');const minutesView=safe(window.minutesProjection,'<div class="section"><div class="empty mono">Minutes Projection v2 unavailable.</div></div>');const aiView=safe(window.ai||ai);const healthView=safe(window.health||health);return `<div class="section"><h2 class="mono">Model Center</h2><div class="navSectionNote mono">Projection Engine v2, simulation, AI diagnostics, production health, and pipeline status.</div></div><div>${pointsView}</div><div>${minutesView}</div><div class="modelCenterGrid"><div>${aiView}</div><div>${healthView}</div></div>`}
  window.render=function(view='today'){const aliases={games:'today',results:'performance',portfolio:'performance',ai:'model',health:'model',altperf:'performance',books:'props'};view=aliases[view]||view;if(!NAV.some(([id])=>id===view))view='today';setChrome(view);const root=document.getElementById('root');if(!root)return;if(view==='today')root.innerHTML=safe(window.games||games);else if(view==='props'){root.innerHTML=safe(window.props||props);if(typeof drawProps==='function')drawProps()}else if(view==='alt')root.innerHTML=safe(window.altStreaks,'<div class="section"><div class="empty mono">ALT Streaks unavailable.</div></div>');else if(view==='best')root.innerHTML=safe(window.best||best);else if(view==='performance')root.innerHTML=performanceView();else if(view==='model')root.innerHTML=modelView();window.scrollTo(0,0)};
  window.render('today');
})();
</script>
'''

def replace_block(html: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start=html.find(start_marker)
    if start<0:return html
    end=html.find(end_marker,start)
    if end<0:return html
    return html[:start]+replacement.strip()+html[end+len(end_marker):]

def refresh_clv_context() -> None:
    try:
        performance=json.load(PERFORMANCE.open(encoding="utf-8")) if PERFORMANCE.exists() else {}
        target=str(performance.get("target_date") or "")
        if target:
            from wnba_alt_closing_line_tracker import report,resolve,snapshot
            snapshot(target);resolve(target);report(target)
        from wnba_alt_performance_clv_context import main as attach_clv
        attach_clv()
    except Exception as exc:print("ALT CLV context warning:",exc)

def main() -> None:
    if not HTML.exists():raise SystemExit("docs/index.html missing")
    refresh_clv_context();html=HTML.read_text(encoding="utf-8")
    if PERFORMANCE.exists():
        try:
            payload=json.load(PERFORMANCE.open(encoding="utf-8"));data_script=f'<script id="v4-alt-performance-data">DATA.alt_performance={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
            if 'id="v4-alt-performance-data"' in html:html=replace_block(html,'<script id="v4-alt-performance-data">','</script>',data_script)
        except Exception as exc:print("ALT Performance data refresh warning:",exc)
    html=replace_block(html,'<style id="v4-consolidated-navigation-style">','</style>',CSS) if 'id="v4-consolidated-navigation-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace_block(html,'<script id="v4-consolidated-navigation-script">','</script>',SCRIPT) if 'id="v4-consolidated-navigation-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding="utf-8")
    try:
        from patch_dashboard_v4_alt_clv import main as patch_clv
        patch_clv()
    except Exception as exc:print("ALT CLV dashboard warning:",exc)
    print("V4 navigation consolidated with Points and Minutes Projection v2")

if __name__=="__main__":main()
