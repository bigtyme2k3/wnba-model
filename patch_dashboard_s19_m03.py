from __future__ import annotations

import json,re,subprocess,sys
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_s19_m03_dashboard_consumer.json')
M04=Path('data/dashboard/wnba_s19_m04_decision_contract.json')
M04_AUDIT=Path('data/dashboard/wnba_s19_m04_decision_contract_audit.json')
M05=Path('data/dashboard/wnba_s19_m05_dashboard_health.json')
M05_AUDIT=Path('data/dashboard/wnba_s19_m05_dashboard_health_audit.json')
M06=Path('data/dashboard/wnba_s19_m06_results_lifecycle.json')
M06_AUDIT=Path('data/dashboard/wnba_s19_m06_results_lifecycle_audit.json')
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
 function best(){{
  const rows=Array.isArray(D.best_bets)?D.best_bets:[],state=D.research_watchlist_state||{{}};
  const stamp=Date.parse(state.market_generated_at_utc||''),now=Date.now();
  const marketFresh=state.status==='CURRENT'&&Number.isFinite(stamp)&&now-stamp>=-5*60000&&now-stamp<=180*60000;
  const watch=marketFresh?(D.research_watchlist||[]).filter(r=>{{const tip=Date.parse(r.commence_time||'');return Number.isFinite(tip)&&tip>now}}):[];
  const num=(v,d=1)=>v===null||v===undefined||v===''?'—':Number(v).toFixed(d);
  const odds=v=>v===null||v===undefined?'—':Number(v)>0?'+'+Number(v):String(v);
  const signalCurrent=D.buy_signal_source_date===D.target_date;
  const sourceNote=signalCurrent?'Current V5 buy-signal source: no approved signals.':`V5 buy-signal source last dated ${{esc(D.buy_signal_source_date||'unknown')}}; it has no current approved signals.`;
  const approved=rows.map(r=>`<div class="s19card"><div class="s19badge">APPROVED BET</div><h3>${{esc(r.player||r.pick||'Market')}}</h3><div>${{esc(r.game||'—')}} · ${{esc(r.stat||r.market||'—')}} ${{esc(r.recommendation||r.side||'—')}} ${{esc(r.line??'—')}}</div><div class="s19muted">${{esc(r.sportsbook||'—')}} ${{esc(odds(r.american_odds))}} · Projection ${{esc(num(r.model_projection))}} · Edge ${{esc(num(r.edge))}} · Model score ${{esc(num(r.confidence,0))}}</div></div>`).join('');
  const research=watch.map(r=>`<div class="s19card"><div class="s19badge">WATCH · RESEARCH ONLY</div><h3>${{esc(r.player)}} · ${{esc(r.stat)}} ${{esc(r.side)}} ${{esc(r.line)}}</h3><div>${{esc(r.game)}}</div><div class="s19muted">${{esc(r.sportsbook)}} ${{esc(odds(r.american_odds))}} · Projection ${{esc(num(r.model_projection))}} · Edge ${{esc(num(r.edge))}} · Model score ${{esc(num(r.confidence,0))}}</div><div class="s19muted">${{esc(r.injury_status)}} · ${{esc(r.projected_minutes==null?'Minutes unverified':num(r.projected_minutes)+' projected min')}} · No approved V5 buy signal</div></div>`).join('');
  const marketNote=marketFresh?`Exact sportsbook lines as of ${{esc(new Date(stamp).toLocaleTimeString('en-US',{{timeZone:'America/New_York',hour:'numeric',minute:'2-digit',timeZoneName:'short'}}))}}. Hide at tipoff or after 180 minutes.`:'Research lines are unavailable or older than 180 minutes. Wait for the next source refresh.';
  return `<div class="section">${{gate()}}<h2 class="mono">Best Bets · V5 Decisions</h2><div class="s19muted mono">${{rows.length}} approved bets · ${{watch.length}} research watch items · Slate ${{esc(D.target_date)}}</div>${{rows.length?`<div class="s19grid" style="margin-top:12px">${{approved}}</div>`:`<div class="uiFreezeUnavailable">No approved Best Bets for this slate. ${{sourceNote}}</div>`}}<h3 class="mono" style="margin-top:20px">Research Watchlist</h3><div class="s19muted mono">WATCH is not BET. These model scores are not calibrated win probabilities; no EV or fair odds is claimed. Speculative/questionable injuries and unsupported books are excluded. ${{marketNote}}</div><div class="s19grid" style="margin-top:12px">${{research||'<div class="uiFreezeUnavailable">No current research items pass the display checks.</div>'}}</div></div>`;
 }}
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

    if not M04.exists() or not M04_AUDIT.exists(): raise SystemExit('Sprint 19 M04 contract artifacts missing after M03 build')
    m04=json.loads(M04.read_text(encoding='utf-8')); audit=json.loads(M04_AUDIT.read_text(encoding='utf-8')); target=str(d.get('target_date') or '')[:10]
    assert m04.get('status')=='READY' and str(m04.get('target_date') or '')[:10]==target, m04
    assert audit.get('status')=='READY' and str(audit.get('target_date') or '')[:10]==target and audit.get('all_rows_current_slate') is True and audit.get('actionable_unavailable_props')==0 and audit.get('legacy_fallback_enabled') is False and audit.get('single_dashboard_contract') is True, audit
    subprocess.run([sys.executable,'patch_dashboard_s19_m04.py'],check=True)
    final_html=HTML.read_text(encoding='utf-8')
    if final_html.count('id="s19-m04-contract-script"') != 1 or 'WNBA_CANONICAL_DASHBOARD_CONTRACT' not in final_html: raise SystemExit('Sprint 19 M04 dashboard contract not installed exactly once')
    print({'status':'PASS','sprint':19,'module':'M04','target_date':target,'games':audit.get('games'),'player_props':audit.get('player_props'),'best_bets':audit.get('best_bets'),'portfolio':audit.get('portfolio'),'results_status':audit.get('results_status'),'single_dashboard_contract':True})

    subprocess.run([sys.executable,'scripts/wnba_s19_m05_dashboard_health.py','--date',target],check=True)
    if not M05.exists() or not M05_AUDIT.exists(): raise SystemExit('Sprint 19 M05 health artifacts missing')
    m05=json.loads(M05.read_text(encoding='utf-8')); a05=json.loads(M05_AUDIT.read_text(encoding='utf-8'))
    assert m05.get('status')=='READY' and str(m05.get('target_date') or '')[:10]==target, m05
    assert a05.get('status')=='READY' and str(a05.get('target_date') or '')[:10]==target and a05.get('all_health_checks_pass') is True and a05.get('legacy_fallback_enabled') is False and a05.get('single_dashboard_contract') is True, a05
    subprocess.run([sys.executable,'patch_dashboard_s19_m05.py'],check=True)
    final_html=HTML.read_text(encoding='utf-8')
    if final_html.count('id="s19-m05-health-script"') != 1 or 'WNBA_DASHBOARD_HEALTH' not in final_html: raise SystemExit('Sprint 19 M05 dashboard health contract not installed exactly once')
    print({'status':'PASS','sprint':19,'module':'M05','target_date':target,'health':a05.get('status'),'healthy_checks':a05.get('healthy_checks'),'total_checks':a05.get('total_checks'),'contract_age_minutes':a05.get('contract_age_minutes')})

    # M06 archives the current canonical predictions into the existing durable history/edge lifecycle.
    subprocess.run([sys.executable,'scripts/wnba_s19_m06_results_lifecycle.py','--date',target],check=True)
    if not M06.exists() or not M06_AUDIT.exists(): raise SystemExit('Sprint 19 M06 lifecycle artifacts missing')
    m06=json.loads(M06.read_text(encoding='utf-8')); a06=json.loads(M06_AUDIT.read_text(encoding='utf-8'))
    assert m06.get('status')=='READY' and str(m06.get('target_date') or '')[:10]==target, m06
    assert a06.get('status')=='READY' and str(a06.get('target_date') or '')[:10]==target and a06.get('duplicate_history_keys')==0 and a06.get('same_day_final_results_inferred') is False and a06.get('existing_grader_reused') is True and a06.get('existing_edge_database_reused') is True, a06
    subprocess.run([sys.executable,'patch_dashboard_s19_m06.py'],check=True)
    final_html=HTML.read_text(encoding='utf-8')
    if final_html.count('id="s19-m06-results-script"') != 1 or 'WNBA_RESULTS_LIFECYCLE' not in final_html: raise SystemExit('Sprint 19 M06 results lifecycle not installed exactly once')
    print({'status':'PASS','sprint':19,'module':'M06','target_date':target,'target_history_records':a06.get('target_history_records'),'added_history_records':a06.get('added_history_records'),'target_edge_records':a06.get('target_edge_records'),'results_state':a06.get('results_state')})

if __name__=='__main__':main()
