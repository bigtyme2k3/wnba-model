from __future__ import annotations

import json
from pathlib import Path

HTML=Path('docs/index.html');PERFORMANCE=Path('data/dashboard/wnba_alt_performance.json')
CSS=r'''<style id="v4-consolidated-navigation-style">.navSectionNote{margin:0 0 14px;color:#7e8ba3;font-size:12px}.modelCenterGrid{display:grid;grid-template-columns:1fr;gap:16px}.performanceJump{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.performanceJump button{border:1px solid #263854;background:#08101c;color:#cbd7f1;border-radius:999px;padding:8px 12px;font-weight:800}@media(min-width:1100px){.modelCenterGrid{grid-template-columns:1fr 1fr}}</style>'''
SCRIPT=r'''<script id="v4-consolidated-navigation-script">(function(){const NAV=[['today','Today'],['props','Player Props'],['alt','ALT Streaks'],['best','Best Bets'],['performance','Performance'],['model','Model Center']];function safe(fn,fallback=''){try{return typeof fn==='function'?fn():fallback}catch(err){return `<div class="section"><div class="empty mono">Section unavailable: ${String(err)}</div></div>`}}function chrome(view){const tabs=document.getElementById('tabs');if(tabs)tabs.innerHTML=NAV.map(([id,label])=>`<button class="tab ${id===view?'a':''}" data-view="${id}" onclick="render('${id}')">${label}</button>`).join('')}function performanceView(){const alt=safe(window.altPerformance);const resultsView=safe(window.results||results);const portfolioView=safe(window.portfolio||portfolio);return `<div class="section"><h2 class="mono">Performance Center</h2><div class="navSectionNote mono">Results, ALT validation, certified CLV, ROI, and bankroll allocation.</div></div>${alt}${resultsView}${portfolioView}`}function modelView(){const unified=safe(window.unifiedSimulation);const ancillary=safe(window.ancillaryProjection);const joint=safe(window.reboundsAssistsProjection);const points=safe(window.pointsProjection);const minutes=safe(window.minutesProjection);const aiView=safe(window.ai||ai);const healthView=safe(window.health||health);return `<div class="section"><h2 class="mono">Model Center</h2><div class="navSectionNote mono">Unified player simulations, Projection Engine v2, AI diagnostics, and production health.</div></div>${unified}${ancillary}${joint}${points}${minutes}<div class="modelCenterGrid"><div>${aiView}</div><div>${healthView}</div></div>`}window.render=function(view='today'){const aliases={games:'today',results:'performance',portfolio:'performance',ai:'model',health:'model',altperf:'performance',books:'props'};view=aliases[view]||view;if(!NAV.some(([id])=>id===view))view='today';chrome(view);const root=document.getElementById('root');if(!root)return;if(view==='today')root.innerHTML=safe(window.games||games);else if(view==='props'){root.innerHTML=safe(window.props||props);if(typeof drawProps==='function')drawProps()}else if(view==='alt')root.innerHTML=safe(window.altStreaks);else if(view==='best')root.innerHTML=safe(window.best||best);else if(view==='performance')root.innerHTML=performanceView();else if(view==='model')root.innerHTML=modelView();window.scrollTo(0,0)};window.render('today')})();</script>'''
def replace_block(html,start,end,replacement):
 i=html.find(start)
 if i<0:return html
 j=html.find(end,i)
 if j<0:return html
 return html[:i]+replacement.strip()+html[j+len(end):]
def refresh_clv():
 try:
  perf=json.load(PERFORMANCE.open(encoding='utf-8')) if PERFORMANCE.exists() else {};target=str(perf.get('target_date') or '')
  if target:
   from wnba_alt_closing_line_tracker import snapshot,resolve,report
   snapshot(target);resolve(target);report(target)
  from wnba_alt_performance_clv_context import main as attach
  attach()
 except Exception as exc:print('ALT CLV warning:',exc)
def main():
 if not HTML.exists():raise SystemExit('docs/index.html missing')
 refresh_clv();html=HTML.read_text(encoding='utf-8')
 html=replace_block(html,'<style id="v4-consolidated-navigation-style">','</style>',CSS) if 'id="v4-consolidated-navigation-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-consolidated-navigation-script">','</script>',SCRIPT) if 'id="v4-consolidated-navigation-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8')
 try:
  from patch_dashboard_v4_alt_clv import main as patch
  patch()
 except Exception as exc:print('ALT CLV dashboard warning:',exc)
 print('V4 Model Center includes unified simulation and supporting projections')
if __name__=='__main__':main()
