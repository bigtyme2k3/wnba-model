from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html');PERFORMANCE=Path('data/dashboard/wnba_alt_performance.json')
CSS=r'''<style id="v4-consolidated-navigation-style">.navSectionNote{margin:0 0 14px;color:#7e8ba3;font-size:12px}.performanceJump{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.performanceJump button{border:1px solid #263854;background:#08101c;color:#cbd7f1;border-radius:999px;padding:8px 12px;font-weight:800}.propsStack{display:grid;gap:16px}.streakNote{border:1px solid #263854;border-radius:14px;padding:12px;background:#0a1322}.aiCenterGrid{display:grid;grid-template-columns:1fr;gap:16px}#terminal-ui{display:none!important}body.show-system-health #terminal-ui{display:block!important}@media(min-width:1100px){.aiCenterGrid{grid-template-columns:1fr 1fr}}</style>'''
SCRIPT=r'''<script id="v4-consolidated-navigation-script">(function(){const NAV=[['today','Games'],['gameprops','Game Props'],['props','Player Props & Best Bets'],['portfolio','Portfolio'],['ai','AI Center'],['results','Results'],['health','System Health']];function safe(fn,fallback=''){try{return typeof fn==='function'?fn():fallback}catch(err){return `<div class="section"><div class="empty mono">Section unavailable: ${String(err)}</div></div>`}}function chrome(view){const tabs=document.getElementById('tabs');if(tabs)tabs.innerHTML=NAV.map(([id,label])=>`<button class="tab ${id===view?'a':''}" data-view="${id}" onclick="render('${id}')">${label}</button>`).join('')}function propsView(){const standard=safe(window.props||props);const streaks=safe(window.altStreaks);return `<div class="propsStack">${standard}<div class="section"><div class="streakNote"><b>Streak Board</b><div class="small">Verified standard-line streak context is kept with Player Props. True alternate lines appear only when supplied by the odds source.</div></div></div>${streaks}</div>`}function aiView(){const ai=safe(window.ai||ai);return `<div class="section"><h2 class="mono">AI Center</h2><div class="navSectionNote mono">Research, explanations, trend discovery, and warehouse questions. Internal engines remain in the background.</div></div><div class="aiCenterGrid"><div>${ai}</div></div>`}function healthView(){const health=safe(window.health||health);return `<div class="section"><h2 class="mono">System Health</h2><div class="navSectionNote mono">Data freshness, workflow status, source health, API usage, and technical diagnostics.</div></div>${health}`}window.render=function(view='today'){const aliases={games:'today',performance:'results',model:'ai',alt:'props',altperf:'results',books:'props',best:'props',q1:'gameprops'};view=aliases[view]||view;if(!NAV.some(([id])=>id===view))view='today';document.body.classList.toggle('show-system-health',view==='health');chrome(view);const root=document.getElementById('root');if(!root)return;if(view==='today')root.innerHTML=safe(window.games||games);else if(view==='gameprops')root.innerHTML=safe(window.gameProps);else if(view==='props'){root.innerHTML=propsView();if(typeof drawProps==='function')drawProps()}else if(view==='portfolio')root.innerHTML=safe(window.portfolio||portfolio);else if(view==='ai')root.innerHTML=aiView();else if(view==='results')root.innerHTML=safe(window.results||results);else if(view==='health')root.innerHTML=healthView();window.scrollTo(0,0)};window.render('today')})();</script>'''
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
 except Exception as exc:print('Streak CLV warning:',exc)
def main():
 if not HTML.exists():raise SystemExit('docs/index.html missing')
 refresh_clv();html=HTML.read_text(encoding='utf-8')
 html=replace_block(html,'<style id="v4-consolidated-navigation-style">','</style>',CSS) if 'id="v4-consolidated-navigation-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-consolidated-navigation-script">','</script>',SCRIPT) if 'id="v4-consolidated-navigation-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8')
 try:
  from patch_dashboard_v4_alt_clv import main as patch
  patch()
 except Exception as exc:print('Streak CLV dashboard warning:',exc)
 print('Dashboard simplified to seven user-facing tabs; Game Props includes first-quarter markets')
if __name__=='__main__':main()
