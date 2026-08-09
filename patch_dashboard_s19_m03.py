from __future__ import annotations

import json,re,subprocess,sys
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_s19_m03_dashboard_consumer.json')
M04=Path('data/dashboard/wnba_s19_m04_decision_contract.json')
M04_AUDIT=Path('data/dashboard/wnba_s19_m04_decision_contract_audit.json')
START='<!-- SPRINT19_M03_CONSUMER_UI_START -->'
END='<!-- SPRINT19_M03_CONSUMER_UI_END -->'


def main():
    if not HTML.exists() or not DATA.exists(): raise SystemExit('Sprint 19 M03 inputs missing')
    d=json.loads(DATA.read_text(encoding='utf-8'))
    if d.get('status')!='READY': raise SystemExit('Sprint 19 M03 consumer not READY')
    raw=json.dumps(d,ensure_ascii=False).replace('</','<\\/')
    block=f'''\n{START}
<script id="s19-m03-script">
(function(){{
 const D={raw}; window.WNBA_S19_M03=D;
 const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
 const root=()=>document.getElementById('root');
 const gate=()=>`<div class="s19badge">SPRINT 19 M03 · ${{esc(D.target_date)}}</div>`;
 function sync(view){{const t=document.getElementById('tabs');if(t)t.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('a',x.getAttribute('data-view')===view));try{{history.replaceState(null,'','#'+view)}}catch(e){{}}}}
 function best(){{const rows=D.best_bets||[];if(!rows.length)return `<div class="section">${{gate()}}<h2 class="mono">Best Bets · V5 Buy Signals</h2><div class="uiFreezeUnavailable">No current V5 buy signals cleared all guardrails. Legacy Phase 2 fallback is disabled.</div></div>`;return `<div class="section">${{gate()}}<h2 class="mono">Best Bets · V5 Buy Signals</h2><div class="s19grid">${{rows.map(r=>`<div class="s19card"><div class="s19muted mono">V5 BUY SIGNAL</div><h3>${{esc(r.player||r.pick||r.selection||r.side)}}</h3><div>${{esc(r.game)}}</div><div class="s19badge">${{esc(r.market||r.stat||r.type)}}</div><div class="s19badge">${{esc(r.side||r.recommendation||r.action)}}</div><div class="s19muted">Edge ${{esc(r.edge??r.v5_edge??'—')}} · Confidence ${{esc(r.confidence??r.score??'—')}}</div></div>`).join('')}}</div></div>`}}
 function portfolio(){{const rows=D.portfolio||[];if(!rows.length)return `<div class="section">${{gate()}}<h2 class="mono">Portfolio · V5 Live Portfolio</h2><div class="uiFreezeUnavailable">No current V5 portfolio positions are approved. Legacy stake-pending cards are disabled.</div></div>`;return `<div class="section">${{gate()}}<h2 class="mono">Portfolio · V5 Live Portfolio</h2><div class="s19grid">${{rows.map(r=>`<div class="s19card"><div class="s19muted mono">V5 PORTFOLIO</div><h3>${{esc(r.player||r.pick||r.selection||r.side)}}</h3><div>${{esc(r.game)}}</div><div class="s19badge">${{esc(r.market||r.stat||r.type)}}</div><div class="s19badge">Stake ${{esc(r.stake??r.units??r.unit_size??'—')}}</div><div class="s19muted">Edge ${{esc(r.edge??r.v5_edge??'—')}} · Confidence ${{esc(r.confidence??r.score??'—')}}</div></div>`).join('')}}</div></div>`}}
 function results(){{const r=D.results||{{}},s=r.summary||{{}};return `<div class="section">${{gate()}}<h2 class="mono">Results · Canonical Grading</h2><div class="s19muted mono">Deterministic results grading for ${{esc(D.target_date)}}. Waiting for actuals is a valid state and never backfills old results.</div><div class="s19grid" style="margin-top:12px"><div class="s19card"><div class="s19muted">STATUS</div><h3>${{esc(r.status||'unknown')}}</h3><div>Actual source: ${{esc(r.actual_source||'pending')}}</div></div><div class="s19card"><div class="s19muted">ARCHIVED</div><h3>${{esc(r.archived_predictions??0)}}</h3><div>Graded this run: ${{esc(s.graded_this_run??0)}}</div></div><div class="s19card"><div class="s19muted">RECORD</div><h3>${{esc(s.win??0)}}-${{esc(s.loss??0)}}</h3><div>Push ${{esc(s.push??0)}} · Pending ${{esc(s.pending??0)}}</div></div><div class="s19card"><div class="s19muted">P/L</div><h3>${{esc(s.profit_loss??0)}}</h3><div>ROI ${{s.roi==null?'—':(Number(s.roi)*100).toFixed(1)+'%'}}</div></div></div></div>`}}
 function install(){{if(window.__S19_M03_INSTALLED)return true;if(typeof window.render!=='function')return false;const old=window.render;window.__S19_M03_OLD_RENDER=old;window.render=function(view){{if(view==='best'||view==='portfolio'||view==='results'){{const r=root();if(!r)return old(view);sync(view);r.innerHTML=view==='best'?best():view==='portfolio'?portfolio():results();return}}return old(view)}};window.__S19_M03_INSTALLED=true;const h=(location.hash||'').replace('#','');if(['best','portfolio','results'].includes(h))window.render(h);return true}}
 if(!install()){{let n=0;const t=setInterval(()=>{{n++;if(install()||n>30)clearInterval(t)}},100)}}
}})();
</script>
{END}\n'''
    html=HTML.read_text(encoding='utf-8')
    html=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',html,flags=re.S)
    if '</body>' not in html: raise SystemExit('Dashboard shell missing closing body')
    HTML.write_text(html.replace('</body>',block+'\n</body>',1),encoding='utf-8')
    print({'status':'PASS','target_date':d.get('target_date'),'best_bets':len(d.get('best_bets') or []),'portfolio':len(d.get('portfolio') or []),'results_status':(d.get('results') or {}).get('status')})

    # M04 must be built by the M03 consumer and installed into the deployed HTML.
    if not M04.exists() or not M04_AUDIT.exists():
        raise SystemExit('Sprint 19 M04 contract artifacts missing after M03 build')
    m04=json.loads(M04.read_text(encoding='utf-8'))
    audit=json.loads(M04_AUDIT.read_text(encoding='utf-8'))
    target=str(d.get('target_date') or '')[:10]
    assert m04.get('status')=='READY' and str(m04.get('target_date') or '')[:10]==target, m04
    assert audit.get('status')=='READY' and str(audit.get('target_date') or '')[:10]==target, audit
    assert audit.get('all_rows_current_slate') is True, audit
    assert audit.get('actionable_unavailable_props')==0, audit
    assert audit.get('legacy_fallback_enabled') is False, audit
    assert audit.get('single_dashboard_contract') is True, audit

    subprocess.run([sys.executable,'patch_dashboard_s19_m04.py'],check=True)
    final_html=HTML.read_text(encoding='utf-8')
    if final_html.count('id="s19-m04-contract-script"') != 1:
        raise SystemExit('Sprint 19 M04 dashboard contract marker missing or duplicated')
    if 'WNBA_CANONICAL_DASHBOARD_CONTRACT' not in final_html:
        raise SystemExit('Sprint 19 M04 canonical dashboard contract not installed')
    print({'status':'PASS','sprint':19,'module':'M04','target_date':target,'games':audit.get('games'),'player_props':audit.get('player_props'),'best_bets':audit.get('best_bets'),'portfolio':audit.get('portfolio'),'results_status':audit.get('results_status'),'single_dashboard_contract':True})

if __name__=='__main__':main()
