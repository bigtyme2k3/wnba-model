from __future__ import annotations

import json,re
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_s19_m06_results_lifecycle.json')
HISTORY=Path('data/history/wnba_model_history.jsonl')
GRADING=Path('data/dashboard/wnba_results_grading.json')
CURRENT_MODEL_VERSION='sprint19_player_props_v5_m02_action_v2'
START='<!-- SPRINT19_M06_RESULTS_LIFECYCLE_START -->'
END='<!-- SPRINT19_M06_RESULTS_LIFECYCLE_END -->'
STYLE='''<style id="s19-m06-results-style">
.resHero{display:flex;justify-content:space-between;gap:14px;align-items:center}.resHero h2{margin:7px 0}.resState{padding:8px 12px;border:1px solid #5b4920;background:#171307;color:#ffd166;border-radius:999px;white-space:nowrap}.resMetrics{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:10px;margin:14px 0}.resMetric,.resPanel{background:#091625;border:1px solid #1d334b;border-radius:15px;padding:14px}.resMetric span{display:block;color:#8ea1b6;font-size:11px;text-transform:uppercase;letter-spacing:.08em}.resMetric b{display:block;font-size:23px;margin:6px 0}.resGood{color:#20d89b}.resBad{color:#ff667d}.resWarn{color:#f4bf4f}.resGrid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}.resPanel h3{margin:0 0 10px}.resTableWrap{overflow:auto;max-height:52vh}.resTable{width:100%;min-width:860px;border-collapse:collapse;font-size:12px}.resTable th,.resTable td{text-align:left;padding:8px 6px;border-bottom:1px solid #162a40}.resTable th{color:#8ea1b6;position:sticky;top:0;background:#091625}.resLegacy{margin-top:12px;border:1px solid #34445a;background:#0a111c;border-radius:14px;padding:13px}.resFoot{color:#8191a6;font-size:11px;margin-top:9px}.resAction{font-weight:700}.resActionBET{color:#20d89b}.resActionLEAN{color:#77bdfb}.resActionWATCH{color:#f4bf4f}.resActionPASS{color:#8191a6}@media(max-width:900px){.resHero{align-items:flex-start;flex-direction:column}.resMetrics{grid-template-columns:repeat(2,1fr)}.resGrid{grid-template-columns:1fr}}
</style>'''


def latest_graded_predictions(limit=250):
    rows=[]
    if not HISTORY.exists():
        return rows
    for line in HISTORY.read_text(encoding='utf-8').splitlines():
        try:r=json.loads(line)
        except Exception:continue
        if not isinstance(r,dict):continue
        if str(r.get('model_version') or '') != CURRENT_MODEL_VERSION:continue
        if str(r.get('outcome') or '').upper() not in {'WIN','LOSS','PUSH','VOID'}:continue
        if str(r.get('signal') or r.get('recommendation') or '').upper() not in {'OVER','UNDER'}:continue
        scope=str(r.get('result_scope') or '').upper()
        if scope=='QUARANTINED':continue
        action=str(r.get('final_action') or r.get('action') or '').upper()
        if action not in {'BET','LEAN','WATCH','PASS'}:action='WATCH'
        item=dict(r);item['display_action']=action
        rows.append(item)
    rows.sort(key=lambda r:(str(r.get('date') or ''),str(r.get('graded_at_utc') or ''),str(r.get('captured_at_utc') or '')),reverse=True)
    return rows[:limit]


def main():
    if not HTML.exists() or not DATA.exists(): raise SystemExit('Sprint 19 M06 inputs missing')
    d=json.loads(DATA.read_text(encoding='utf-8'))
    if d.get('status')!='READY': raise SystemExit('Sprint 19 M06 lifecycle not READY')
    d.setdefault('current_model',{})['recent_predictions']=latest_graded_predictions()
    if GRADING.exists():
        g=json.loads(GRADING.read_text(encoding='utf-8'))
        if g.get('status')=='ok':
            d['latest_grading']={'date':g.get('target_date'),'void':(g.get('summary') or {}).get('void',0),'archived':g.get('archived_predictions',0)}
    raw=json.dumps(d,ensure_ascii=False).replace('</','<\\/')
    block=f'''\n{START}
<script id="s19-m06-results-script">
(function(){{
 const D={raw}; window.WNBA_RESULTS_LIFECYCLE=D;
 const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
 const pct=v=>v===null||v===undefined?'—':(Number(v)*100).toFixed(1)+'%';
 const root=()=>document.getElementById('root');
 function renderResults(){{
   const s=D.summary||{{}},c=D.current_model||{{}},p=c.performance||{{}},t=c.target?.recommended||{{}},y=c.yesterday||{{}},yd=y.all_directional||{{}},yb=y.bet||{{}},yr=y.research||{{}},legacy=D.legacy_reference?.performance||{{}},research=D.research_archive||{{}},cal=D.calibration_training_set||{{}},q=D.quarantine||{{}},quality=c.data_quality||{{}},recent=Array.isArray(c.recent_predictions)?c.recent_predictions:(Array.isArray(c.recent_results)?c.recent_results:[]);
   const completed=recent.filter(x=>['WIN','LOSS','PUSH','VOID'].includes(String(x.outcome||'').toUpperCase()));
   const latestDate=completed.length?String(completed[0].date||''):'';
   const latestRows=completed.filter(x=>String(x.date||'')===latestDate);
   const tally=items=>{{const w=items.filter(x=>x.outcome==='WIN').length,l=items.filter(x=>x.outcome==='LOSS').length,p=items.filter(x=>x.outcome==='PUSH').length;return {{wins:w,losses:l,pushes:p,decisions:w+l,hit_rate:w+l?w/(w+l):null}}}};
   const fullYesterday=latestDate&&latestDate===String(y.date||'');
   const latestAll=fullYesterday?yd:tally(latestRows),latestBet=fullYesterday?yb:tally(latestRows.filter(x=>String(x.display_action||x.final_action||x.action||'').toUpperCase()==='BET')),latestResearch=fullYesterday?yr:tally(latestRows.filter(x=>String(x.display_action||x.final_action||x.action||'').toUpperCase()!=='BET'));
   const grading=D.latest_grading||{{}},latestVoid=String(grading.date||'')===latestDate?Number(grading.void||0):latestRows.filter(x=>x.outcome==='VOID').length;
   const status=t.pending>0?'WAITING FOR FINALS':t.rows>0?'CURRENT SLATE SETTLED':'NO CURRENT BETS';
   const rows=recent.map(x=>`<tr><td>${{esc(x.date)}}</td><td><b>${{esc(x.player)}}</b><br><span class="s19muted">${{esc(x.game)}}</span></td><td>${{esc(x.stat)}} ${{esc(x.signal)}} ${{esc(x.line)}}</td><td>${{esc(x.pred)}}</td><td>${{esc(x.actual)}}</td><td class="${{x.outcome==='WIN'?'resGood':x.outcome==='LOSS'?'resBad':'resWarn'}}"><b>${{esc(x.outcome)}}</b></td><td class="resAction resAction${{esc(x.display_action||x.final_action||x.action||'WATCH')}}">${{esc(x.display_action||x.final_action||x.action||'WATCH')}}</td><td>${{esc(x.sportsbook)}}</td></tr>`).join('');
   const breakdown=(c.by_stat||[]).map(x=>`<tr><td>${{esc(x.group)}}</td><td>${{x.decisions}}</td><td>${{x.wins}}-${{x.losses}}-${{x.pushes}}</td><td>${{pct(x.hit_rate)}}</td></tr>`).join('');
   const r=root(); if(!r)return;
   r.innerHTML=`<div class="section"><div class="resHero"><div><div class="s19badge">PLAYER PROPS RESULTS · ${{esc(D.target_date)}}</div><h2 class="mono">Player Props Results</h2><div class="s19muted mono">Standard player props from DraftKings, FanDuel, and Fanatics only. Game predictions, ALT Props, Best Bets, research candidates, and legacy models are excluded from BET performance.</div></div><div class="resState mono">${{esc(status)}}</div></div>
   <div class="resMetrics"><div class="resMetric"><span>BET record</span><b>${{p.wins||0}}-${{p.losses||0}}-${{p.pushes||0}}</b><small>${{p.decisions?pct(p.hit_rate):'Insufficient sample'}} · n=${{p.decisions||0}}</small></div><div class="resMetric"><span>Today BET</span><b>${{t.rows||0}}</b><small>${{t.pending||0}} pending · ${{t.voids||0}} void</small></div><div class="resMetric"><span>Research candidates</span><b>${{research.current_research_rows||0}}</b><small>not recommended wagers</small></div><div class="resMetric"><span>Quarantined</span><b>${{q.rows||0}}</b><small>excluded from results</small></div><div class="resMetric"><span>P/L</span><b>—</b><small>no recorded stakes</small></div></div>
   <div class="resPanel"><h3 class="mono">Latest graded player-prop slate · ${{latestDate?esc(latestDate):"None yet"}}</h3><div class="resFoot">Verified current-model outcomes from the most recent graded date. The cards use full-slate totals when available; the detail table shows the latest 250 rows. WATCH and other research are excluded from the BET record. VOID rows are counted separately.</div>
   <div class="resMetrics"><div class="resMetric"><span>All graded O/U</span><b>${{latestAll.wins}}-${{latestAll.losses}}-${{latestAll.pushes}}</b><small>${{latestAll.decisions?pct(latestAll.hit_rate):"No graded directions"}} · n=${{latestAll.decisions}}</small></div><div class="resMetric"><span>Approved BET</span><b>${{latestBet.wins}}-${{latestBet.losses}}-${{latestBet.pushes}}</b><small>${{latestBet.decisions?pct(latestBet.hit_rate):"No BET sample"}} · n=${{latestBet.decisions}}</small></div><div class="resMetric"><span>WATCH / research</span><b>${{latestResearch.wins}}-${{latestResearch.losses}}-${{latestResearch.pushes}}</b><small>${{latestResearch.decisions?pct(latestResearch.hit_rate):"No research sample"}} · n=${{latestResearch.decisions}}</small></div><div class="resMetric"><span>VOID (grader)</span><b>${{latestVoid}}</b><small>excluded from win rate</small></div></div>
   <div class="resFoot">Yesterday (${{esc(y.date)}}) ${{yd.decisions||0}} graded O/U decisions. Current slate ${{c.target?.archived_candidates||0}} archived predictions awaiting verified actuals.</div></div>
   ${{quality.negative_projections||quality.invalid_american_odds?`<div class="gp-alert mono">Historical current-version quality warning: ${{quality.negative_projections||0}} negative projections · ${{quality.invalid_american_odds||0}} invalid American prices. These rows remain visible for audit and should not be interpreted as wager performance.</div>`:''}}
   <div class="resGrid"><div class="resPanel"><h3 class="mono">BET performance by stat</h3><div class="resTableWrap"><table class="resTable" style="min-width:440px"><thead><tr><th>Stat</th><th>N</th><th>Record</th><th>Hit</th></tr></thead><tbody>${{breakdown||'<tr><td colspan="4">Insufficient sample — explicit BET recommendations have not accumulated yet.</td></tr>'}}</tbody></table></div></div><div class="resPanel"><h3 class="mono">Current slate lifecycle</h3><p>Archived candidates: <b>${{c.target?.archived_candidates||0}}</b></p><p>Explicit BET recommendations: <b>${{t.rows||0}}</b></p><p>Pending completed-game actuals: <b>${{t.pending||0}}</b></p><p>Finals are never inferred. Grading requires verified player actuals.</p><div class="resFoot">${{esc(c.profit_loss_status)}}</div></div></div>
   <div class="resPanel"><h3 class="mono">Latest graded model predictions</h3><div class="resFoot">All graded current-model OVER/UNDER predictions are shown here. The ACTION column identifies BET, LEAN, WATCH, or PASS; only BET rows count toward the performance cards above.</div><div class="resTableWrap"><table class="resTable"><thead><tr><th>Date</th><th>Player / game</th><th>Pick</th><th>Model</th><th>Actual</th><th>Result</th><th>Action</th><th>Book</th></tr></thead><tbody>${{rows||'<tr><td colspan="8">No verified graded model predictions yet.</td></tr>'}}</tbody></table></div></div>
   <div class="resLegacy"><h3 class="mono">Legacy models — historical reference only</h3><div>${{legacy.wins||0}}-${{legacy.losses||0}}-${{legacy.pushes||0}} · ${{pct(legacy.hit_rate)}} across n=${{legacy.decisions||0}} graded decisions. Excluded from current results.</div></div>
   <div class="resLegacy"><h3 class="mono">Research evaluation — not wagers</h3><div>${{research.performance?.wins||0}}-${{research.performance?.losses||0}}-${{research.performance?.pushes||0}} · ${{pct(research.performance?.hit_rate)}} across n=${{research.performance?.decisions||0}} directional candidates.</div><div class="resFoot">LEAN/WATCH/PASS and unselected OVER/UNDER candidates are evaluated here only. They never enter BET record, units, or ROI.</div></div><div class="resLegacy"><h3 class="mono">Calibration training set · ${{esc(cal.status||'COLLECTING')}}</h3><div>${{cal.graded_training_rows||0}} valid graded rows · ${{cal.qualified_segment_count||0}} qualified segments · minimum ${{cal.minimum_per_segment||25}} per segment · forward BET validation n=${{cal.forward_bet_validation_n||0}}.</div><div class="resFoot">Readiness requires sufficient observations within stat, side, sportsbook, price, and confidence segments—not league-wide volume alone.</div></div><div class="resLegacy"><h3 class="mono">Data-quality quarantine</h3><div>${{q.rows||0}} excluded rows · ${{Object.entries(q.reason_counts||{{}}).filter(x=>x[1]).map(x=>esc(x[0])+': '+esc(x[1])).join(' · ')||'No quality exclusions'}}</div></div></div>`;
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
    print({'status':'PASS','sprint':19,'module':'M06','target_date':d.get('target_date'),'results_state':(d.get('summary') or {}).get('results_state'),'target_history_records':(d.get('summary') or {}).get('target_history_records'),'recent_predictions':len(d.get('current_model',{}).get('recent_predictions',[]))})

if __name__=='__main__':main()
