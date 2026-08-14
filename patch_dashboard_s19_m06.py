from __future__ import annotations

import json,re
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_s19_m06_results_lifecycle.json')
START='<!-- SPRINT19_M06_RESULTS_LIFECYCLE_START -->'
END='<!-- SPRINT19_M06_RESULTS_LIFECYCLE_END -->'
STYLE='''<style id="s19-m06-results-style">
.resHero{display:flex;justify-content:space-between;gap:14px;align-items:center}.resHero h2{margin:7px 0}.resState{padding:8px 12px;border:1px solid #5b4920;background:#171307;color:#ffd166;border-radius:999px;white-space:nowrap}.resMetrics{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:10px;margin:14px 0}.resMetric,.resPanel{background:#091625;border:1px solid #1d334b;border-radius:15px;padding:14px}.resMetric span{display:block;color:#8ea1b6;font-size:11px;text-transform:uppercase;letter-spacing:.08em}.resMetric b{display:block;font-size:23px;margin:6px 0}.resGood{color:#20d89b}.resBad{color:#ff667d}.resWarn{color:#f4bf4f}.resGrid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}.resPanel h3{margin:0 0 10px}.resTableWrap{overflow:auto;max-height:52vh}.resTable{width:100%;min-width:760px;border-collapse:collapse;font-size:12px}.resTable th,.resTable td{text-align:left;padding:8px 6px;border-bottom:1px solid #162a40}.resTable th{color:#8ea1b6;position:sticky;top:0;background:#091625}.resLegacy{margin-top:12px;border:1px solid #34445a;background:#0a111c;border-radius:14px;padding:13px}.resFoot{color:#8191a6;font-size:11px;margin-top:9px}@media(max-width:900px){.resHero{align-items:flex-start;flex-direction:column}.resMetrics{grid-template-columns:repeat(2,1fr)}.resGrid{grid-template-columns:1fr}}
</style>'''


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
 const pct=v=>v===null||v===undefined?'—':(Number(v)*100).toFixed(1)+'%';
 const root=()=>document.getElementById('root');
 function renderResults(){{
   const s=D.summary||{{}},c=D.current_model||{{}},p=c.performance||{{}},t=c.target?.recommended||{{}},legacy=D.legacy_reference?.performance||{{}},research=D.research_archive||{{}},quality=c.data_quality||{{}},recent=Array.isArray(c.recent_results)?c.recent_results:[];
   const status=t.pending>0?'WAITING FOR FINALS':t.rows>0?'CURRENT SLATE SETTLED':'NO CURRENT RECOMMENDATIONS';
   const rows=recent.map(x=>`<tr><td>${{esc(x.date)}}</td><td><b>${{esc(x.player)}}</b><br><span class="s19muted">${{esc(x.game)}}</span></td><td>${{esc(x.stat)}} ${{esc(x.signal)}} ${{esc(x.line)}}</td><td>${{esc(x.pred)}}</td><td>${{esc(x.actual)}}</td><td class="${{x.outcome==='WIN'?'resGood':x.outcome==='LOSS'?'resBad':'resWarn'}}"><b>${{esc(x.outcome)}}</b></td><td>${{esc(x.sportsbook)}}</td></tr>`).join('');
   const breakdown=(c.by_stat||[]).map(x=>`<tr><td>${{esc(x.group)}}</td><td>${{x.decisions}}</td><td>${{x.wins}}-${{x.losses}}-${{x.pushes}}</td><td>${{pct(x.hit_rate)}}</td></tr>`).join('');
   const r=root(); if(!r)return;
   r.innerHTML=`<div class="section"><div class="resHero"><div><div class="s19badge">PLAYER PROPS RESULTS · ${{esc(D.target_date)}}</div><h2 class="mono">Player Props Results</h2><div class="s19muted mono">Standard player props from DraftKings, FanDuel, and Fanatics only. Game predictions, ALT Props, Best Bets, research candidates, and legacy models are excluded.</div></div><div class="resState mono">${{esc(status)}}</div></div>
   <div class="resMetrics"><div class="resMetric"><span>Current record</span><b>${{p.wins||0}}-${{p.losses||0}}-${{p.pushes||0}}</b><small>${{pct(p.hit_rate)}} · n=${{p.decisions||0}}</small></div><div class="resMetric"><span>Today recommended</span><b>${{t.rows||0}}</b><small>${{t.pending||0}} pending · ${{t.voids||0}} void</small></div><div class="resMetric"><span>Latest graded</span><b>${{recent.length}}</b><small>current-model rows shown</small></div><div class="resMetric"><span>Duplicates</span><b>${{s.duplicate_history_keys||0}}</b><small>deterministic keys</small></div><div class="resMetric"><span>P/L</span><b>—</b><small>no recorded stakes</small></div></div>
   ${{quality.negative_projections||quality.invalid_american_odds?`<div class="gp-alert mono">Historical current-version quality warning: ${{quality.negative_projections||0}} negative projections · ${{quality.invalid_american_odds||0}} invalid American prices. These rows remain visible for audit and should not be interpreted as wager performance.</div>`:''}}
   <div class="resGrid"><div class="resPanel"><h3 class="mono">Performance by stat</h3><div class="resTableWrap"><table class="resTable" style="min-width:440px"><thead><tr><th>Stat</th><th>N</th><th>Record</th><th>Hit</th></tr></thead><tbody>${{breakdown||'<tr><td colspan="4">No graded current-model recommendations.</td></tr>'}}</tbody></table></div></div><div class="resPanel"><h3 class="mono">Current slate lifecycle</h3><p>Archived candidates: <b>${{c.target?.archived_candidates||0}}</b></p><p>Eligible recommendations: <b>${{t.rows||0}}</b></p><p>Pending completed-game actuals: <b>${{t.pending||0}}</b></p><p>Finals are never inferred. Grading requires verified player actuals.</p><div class="resFoot">${{esc(c.profit_loss_status)}}</div></div></div>
   <div class="resPanel"><h3 class="mono">Latest graded recommendations</h3><div class="resTableWrap"><table class="resTable"><thead><tr><th>Date</th><th>Player / game</th><th>Pick</th><th>Model</th><th>Actual</th><th>Result</th><th>Book</th></tr></thead><tbody>${{rows||'<tr><td colspan="7">No verified current-model results yet.</td></tr>'}}</tbody></table></div></div>
   <div class="resLegacy"><h3 class="mono">Legacy models — historical reference only</h3><div>${{legacy.wins||0}}-${{legacy.losses||0}}-${{legacy.pushes||0}} · ${{pct(legacy.hit_rate)}} across n=${{legacy.decisions||0}} graded decisions. Excluded from current results.</div></div>
   <div class="resLegacy"><h3 class="mono">Research archive diagnostics</h3><div>${{research.all_history_rows||0}} archived candidates · Edge DB ${{research.edge_database_open||0}} open / ${{research.edge_database_settled||0}} settled.</div><div class="resFoot">These are database lifecycle counts, not bets and not the current-model record.</div></div></div>`;
 }}
 function install(){{if(window.__S19_M06_INSTALLED)return true;if(typeof window.render!=='function')return false;const old=window.render;window.__S19_M06_OLD_RENDER=old;window.render=function(view){{if(view==='results'){{try{{history.replaceState(null,'','#results')}}catch(e){{}};const t=document.getElementById('tabs');if(t)t.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('a',x.getAttribute('data-view')==='results'));renderResults();return}}return old(view)}};window.__S19_M06_INSTALLED=true;if((location.hash||'').replace('#','')==='results')window.render('results');return true}}
 if(!install()){{let n=0;const t=setInterval(()=>{{n++;if(install()||n>30)clearInterval(t)}},100)}}
}})();
</script>
{END}\n'''
    html=HTML.read_text(encoding='utf-8')
    html=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',html,flags=re.S)
    html=re.sub(r'<style id="s19-m06-results-style">.*?</style>','',html,flags=re.S)
    html=html.replace('</head>',STYLE+'\n</head>',1)
    if '</body>' not in html: raise SystemExit('Dashboard shell missing closing body')
    HTML.write_text(html.replace('</body>',block+'\n</body>',1),encoding='utf-8')
    print({'status':'PASS','sprint':19,'module':'M06','target_date':d.get('target_date'),'results_state':(d.get('summary') or {}).get('results_state'),'target_history_records':(d.get('summary') or {}).get('target_history_records')})

if __name__=='__main__':main()
