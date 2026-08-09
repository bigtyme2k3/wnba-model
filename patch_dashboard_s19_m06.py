from __future__ import annotations

import json,re
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_s19_m06_results_lifecycle.json')
START='<!-- SPRINT19_M06_RESULTS_LIFECYCLE_START -->'
END='<!-- SPRINT19_M06_RESULTS_LIFECYCLE_END -->'


def main():
    if not HTML.exists() or not DATA.exists(): raise SystemExit('Sprint 19 M06 inputs missing')
    d=json.loads(DATA.read_text(encoding='utf-8'))
    if d.get('status')!='READY': raise SystemExit('Sprint 19 M06 lifecycle not READY')
    raw=json.dumps(d,ensure_ascii=False).replace('</','<\\/')
    block=f'''\n{START}
<script id="s19-m06-results-script">
(function(){{
 const D={raw}; window.WNBA_RESULTS_LIFECYCLE=D;
 const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
 const root=()=>document.getElementById('root');
 function renderResults(){{
   const s=D.summary||{{}};
   const r=root(); if(!r)return;
   r.innerHTML=`<div class="section"><div class="s19badge">SPRINT 19 M06 · ${{esc(D.target_date)}}</div><h2 class="mono">Results · Lifecycle</h2><div class="s19muted mono">Current predictions are archived before grading. Final outcomes are added only from completed-game actuals; same-day finals are never inferred.</div><div class="s19grid" style="margin-top:12px"><div class="s19card"><div class="s19muted">LIFECYCLE</div><h3>${{esc(s.results_state)}}</h3><div>Target ${{esc(D.target_date)}}</div></div><div class="s19card"><div class="s19muted">ARCHIVED</div><h3>${{esc(s.target_history_records??0)}}</h3><div>Added this build: ${{esc(s.added_history_records??0)}}</div></div><div class="s19card"><div class="s19muted">EDGE DB</div><h3>${{esc(s.target_edge_records??0)}}</h3><div>Open ${{esc(s.open_edge_records??0)}} · Settled ${{esc(s.settled_edge_records??0)}}</div></div><div class="s19card"><div class="s19muted">DUPLICATES</div><h3>${{esc(s.duplicate_history_keys??0)}}</h3><div>Deterministic archive keys</div></div></div></div>`;
 }}
 function install(){{if(window.__S19_M06_INSTALLED)return true;if(typeof window.render!=='function')return false;const old=window.render;window.__S19_M06_OLD_RENDER=old;window.render=function(view){{if(view==='results'){{try{{history.replaceState(null,'','#results')}}catch(e){{}};const t=document.getElementById('tabs');if(t)t.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('a',x.getAttribute('data-view')==='results'));renderResults();return}}return old(view)}};window.__S19_M06_INSTALLED=true;if((location.hash||'').replace('#','')==='results')window.render('results');return true}}
 if(!install()){{let n=0;const t=setInterval(()=>{{n++;if(install()||n>30)clearInterval(t)}},100)}}
}})();
</script>
{END}\n'''
    html=HTML.read_text(encoding='utf-8')
    html=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',html,flags=re.S)
    if '</body>' not in html: raise SystemExit('Dashboard shell missing closing body')
    HTML.write_text(html.replace('</body>',block+'\n</body>',1),encoding='utf-8')
    print({'status':'PASS','sprint':19,'module':'M06','target_date':d.get('target_date'),'results_state':(d.get('summary') or {}).get('results_state'),'target_history_records':(d.get('summary') or {}).get('target_history_records')})

if __name__=='__main__':main()
