from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_s19_m02_predictions.json')
AUDIT = Path('data/dashboard/wnba_s19_m02_prediction_audit.json')
BUILDER = Path('scripts/wnba_s19_m02_predictions.py')
START = '<!-- SPRINT19_M02_PREDICTION_UI_START -->'
END = '<!-- SPRINT19_M02_PREDICTION_UI_END -->'


def ensure_predictions():
    target = str(os.environ.get('TARGET') or '').strip()
    if not target:
        proc = subprocess.run(['python', 'active_slate_date.py'], capture_output=True, text=True)
        if proc.returncode == 0:
            target = proc.stdout.strip().splitlines()[-1].strip()
    if not target:
        raise SystemExit('Sprint 19 M02 target date unavailable')

    subprocess.run(['python', 'player_points.py', '--date', target, '--out', 'data/raw'], check=True)
    subprocess.run(['python', str(BUILDER), '--date', target], check=True)

    if not DATA.exists() or not AUDIT.exists():
        raise SystemExit('Sprint 19 M02 prediction artifacts missing after rebuild')

    payload = json.loads(DATA.read_text(encoding='utf-8'))
    audit = json.loads(AUDIT.read_text(encoding='utf-8'))
    if payload.get('status') != 'READY' or audit.get('status') != 'READY':
        raise SystemExit({'payload_status': payload.get('status'), 'audit_status': audit.get('status')})
    if str(payload.get('target_date') or '')[:10] != target or str(audit.get('target_date') or '')[:10] != target:
        raise SystemExit({'target': target, 'payload_target': payload.get('target_date'), 'audit_target': audit.get('target_date')})
    if int(audit.get('actionable_out_props') or 0) != 0:
        raise SystemExit({'actionable_out_props': audit.get('actionable_out_props')})
    if int(audit.get('player_prop_predictions') or 0) <= 0:
        raise SystemExit('Sprint 19 M02 produced zero Player Props predictions')
    if audit.get('player_props_with_model_projection') != audit.get('player_prop_predictions'):
        raise SystemExit('Sprint 19 M02 has Player Props without model projections')
    if audit.get('all_rendered_props_exact_current_slate') is not True:
        raise SystemExit('Sprint 19 M02 exact current-slate Player Props guard failed')
    if audit.get('phase2_portfolio_fallback_enabled') is not False:
        raise SystemExit('Sprint 19 M02 Phase 2 portfolio fallback is still enabled')
    return payload


def main():
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')

    payload = ensure_predictions()
    raw = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')

    block = f'''\n{START}
<style id="s19-m02-style">
.s19badge{{display:inline-block;border:1px solid #285a48;background:#09271f;color:#55d6a5;border-radius:999px;padding:4px 8px;font-size:11px;margin:2px 5px 2px 0}}
.s19warn{{border-color:#665324;background:#2a2108;color:#ffd166}}.s19bad{{border-color:#6a2c39;background:#2b0d15;color:#ff7b91}}
.s19grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px}}
.s19card{{background:#0b1423;border:1px solid #263854;border-radius:15px;padding:14px}}
.s19metrics{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:10px}}
.s19metric{{background:#08111f;border:1px solid #1d2c43;border-radius:10px;padding:9px}}.s19metric b{{display:block;margin-top:3px}}
.s19toolbar{{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin:12px 0 8px}}.s19filter{{background:#0b1423;border:1px solid #263854;color:#b7c6da;border-radius:999px;padding:7px 11px;font:inherit;cursor:pointer}}.s19filter.a{{border-color:#3de6b0;color:#3de6b0;background:#09271f}}.s19count{{margin-left:auto;color:#8190aa;font-size:11px}}
.s19scroll{{overflow:auto;max-height:70vh;border:1px solid #1d2c43;border-radius:12px;position:relative;overscroll-behavior:contain}}.s19scroll:after{{content:'⇄ scroll columns';position:sticky;left:10px;bottom:5px;display:inline-block;background:#07111ecc;color:#8190aa;padding:3px 7px;border-radius:8px;font-size:10px;pointer-events:none}}
.s19table{{min-width:1180px;width:100%;border-collapse:separate;border-spacing:0;font-size:12px}}.s19table th,.s19table td{{padding:9px;border-bottom:1px solid #1d2c43;text-align:left;vertical-align:top;white-space:nowrap;background:#07111e}}.s19table thead th{{position:sticky;top:0;z-index:4;background:#0b1423}}.s19table th:nth-child(1),.s19table td:nth-child(1){{position:sticky;left:0;z-index:3;min-width:235px;max-width:235px}}.s19table th:nth-child(2),.s19table td:nth-child(2){{position:sticky;left:235px;z-index:3;min-width:68px;background:#081421}}.s19table thead th:nth-child(1),.s19table thead th:nth-child(2){{z-index:6}}
.s19sort{{appearance:none;border:0;background:transparent;color:#9fb1c8;font:inherit;font-weight:700;letter-spacing:.03em;padding:0;cursor:pointer;display:inline-flex;gap:5px;align-items:center;touch-action:manipulation}}.s19sort:hover,.s19sort.active{{color:#55d6a5}}.s19sortmark{{font-size:10px;min-width:10px;color:#61738c}}.s19sort.active .s19sortmark{{color:#55d6a5}}.s19sortstatus{{color:#8190aa;font-size:10px;margin-left:4px}}
.s19good{{color:#3de6b0}}.s19under{{color:#77b7ff}}.s19pass{{color:#8190aa}}.s19muted{{color:#8190aa;font-size:11px}}
@media(max-width:900px){{.s19count{{width:100%;margin-left:0}}.s19scroll{{max-height:68vh}}.s19sort{{min-height:30px}}}}
</style>
<script id="s19-m02-script">
(function(){{
 const D={raw}; window.WNBA_S19_M02=D; let propFilter='ALL'; let propSort={{key:null,dir:'asc'}};
 const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
 const num=(v,d=1)=>v==null||v===''?'—':Number(v).toFixed(d);
 const root=()=>document.getElementById('root');
 const gate=()=>`<div class="s19badge">SPRINT 19 M02 · ${{esc(D.target_date)}}</div>`;
 function syncTabs(view){{const tabs=document.getElementById('tabs');if(tabs)tabs.querySelectorAll('[data-view]').forEach(el=>el.classList.toggle('a',el.getAttribute('data-view')===view));try{{history.replaceState(null,'','#'+view)}}catch(e){{}}}}
 function injuryBadges(ctx){{ctx=ctx||{{}};const parts=[];if(ctx.out)parts.push(`<span class="s19badge s19bad">${{ctx.out}} OUT</span>`);if(ctx.questionable)parts.push(`<span class="s19badge s19warn">${{ctx.questionable}} Q</span>`);if(ctx.probable)parts.push(`<span class="s19badge">${{ctx.probable}} PROB</span>`);return parts.join('')||'<span class="s19badge">No listed injuries</span>'}}
 function gamesHtml(){{const games=D.games||[];return `<div class="section">${{gate()}}<h2 class="mono">Today's Games · Injury-Adjusted Predictions</h2><div class="s19muted mono">Every projection below was regenerated after the current official injury refresh.</div><div class="s19grid" style="margin-top:12px">${{games.map(g=>{{const p=g.projection||{{}},m=g.market||{{}},e=g.edge||{{}},r=g.recommendation||{{}},c=g.injury_context||{{}};return `<div class="s19card"><div class="s19muted mono">${{esc(g.game)}}</div><h3 class="mono">${{esc(g.away_team)}} ${{num(p.away_score)}} · ${{esc(g.home_team)}} ${{num(p.home_score)}}</h3>${{injuryBadges(c)}}<div class="s19metrics"><div class="s19metric">Win Probability<b>${{esc(g.home_team)}} ${{p.home_win_probability==null?'—':(Number(p.home_win_probability)*100).toFixed(1)+'%'}}</b></div><div class="s19metric">Spread<b>Book ${{esc(m.home_spread)}} · Model ${{num(p.model_home_spread)}}</b><span class="s19good">Edge ${{num(e.spread)}}</span></div><div class="s19metric">Total<b>Book ${{esc(m.total)}} · Model ${{num(p.total)}}</b><span class="s19good">Edge ${{num(e.total)}}</span></div><div class="s19metric">Recommendation<b>${{esc(r.spread||'PASS')}} · ${{esc(r.total||'PASS')}}</b>Conf ${{esc(g.confidence)}} · Grade ${{esc(g.model_grade)}}</div></div><div class="s19muted" style="margin-top:9px">Injury source ${{esc(c.generated_at_utc||D.injury_generated_at_utc)}}</div></div>`}}).join('')}}</div></div>`}}
 function sortValue(r,key){{
   if(key==='player')return String(r.player||'').toLowerCase();
   if(key==='stat')return String(r.stat||'').toLowerCase();
   if(key==='pick')return String(r.recommendation||'PASS').toUpperCase();
   if(key==='injury')return String(r.injury_status||'CLEAR').toUpperCase();
   if(key==='market'){{const a=Number(r.best_over_price);return Number.isFinite(a)?a:-99999}}
   const map={{line:r.line,model:r.model_projection,edge:r.edge,confidence:r.confidence,minutes:r.projected_minutes}};
   const n=Number(map[key]);return Number.isFinite(n)?n:-99999;
 }}
 function sortedRows(rows){{if(!propSort.key)return rows.slice();const dir=propSort.dir==='asc'?1:-1;return rows.slice().sort((a,b)=>{{const av=sortValue(a,propSort.key),bv=sortValue(b,propSort.key);if(typeof av==='string'||typeof bv==='string')return String(av).localeCompare(String(bv))*dir;return (av-bv)*dir}})}}
 function sortHead(label,key){{const active=propSort.key===key;const mark=active?(propSort.dir==='asc'?'▲':'▼'):'↕';const aria=active?`aria-sort="${{propSort.dir==='asc'?'ascending':'descending'}}"`:'';return `<button class="s19sort ${{active?'active':''}}" ${{aria}} onclick="window.s19SortProps('${{key}}')" title="Sort ${{esc(label)}}">${{esc(label)}} <span class="s19sortmark">${{mark}}</span></button>`}}
 function propsHtml(){{const all=D.player_props||[];const counts={{OVER:0,UNDER:0,PASS:0,ACTIONABLE:0}};all.forEach(r=>{{const p=String(r.recommendation||'PASS').toUpperCase();counts[p]=(counts[p]||0)+1;if(r.eligible)counts.ACTIONABLE++}});const filtered=all.filter(r=>propFilter==='ALL'||(propFilter==='ACTIONABLE'&&r.eligible)||String(r.recommendation||'PASS').toUpperCase()===propFilter);const rows=sortedRows(filtered);const btn=f=>`<button class="s19filter ${{propFilter===f?'a':''}}" onclick="window.s19SetPropFilter('${{f}}')">${{f==='ALL'?'All '+all.length:f+' '+(counts[f]||0)}}</button>`;const sortStatus=propSort.key?` · Sorted ${{esc(propSort.key)}} ${{propSort.dir==='asc'?'↑':'↓'}}`:'';return `<div class="section">${{gate()}}<h2 class="mono">Player Props · Model Predictions</h2><div class="s19muted mono">Exact current-slate sportsbook lines vs current V5 projections. Tap any column heading to sort ascending/descending. Player and prop stay pinned while the remaining columns scroll horizontally.</div><div class="s19toolbar">${{['ALL','OVER','UNDER','PASS','ACTIONABLE'].map(btn).join('')}}<span class="s19count">Showing ${{rows.length}} of ${{all.length}}${{sortStatus}}</span></div><div class="s19scroll"><table class="s19table"><thead><tr><th>${{sortHead('Player','player')}}</th><th>${{sortHead('Prop','stat')}}</th><th>${{sortHead('Line','line')}}</th><th>${{sortHead('Model','model')}}</th><th>${{sortHead('Edge','edge')}}</th><th>${{sortHead('Pick','pick')}}</th><th>${{sortHead('Confidence','confidence')}}</th><th>${{sortHead('Minutes','minutes')}}</th><th>${{sortHead('Injury','injury')}}</th><th>${{sortHead('Market O/U','market')}}</th></tr></thead><tbody>${{rows.map(r=>{{const pick=String(r.recommendation||'PASS');const cls=pick==='OVER'?'s19good':pick==='UNDER'?'s19under':'s19pass';return `<tr><td><b>${{esc(r.player)}}</b><div class="s19muted">${{esc(r.team||'')}} · ${{esc(r.game)}}</div></td><td>${{esc(r.stat)}}</td><td>${{num(r.line)}}</td><td><b>${{num(r.model_projection)}}</b></td><td class="${{Number(r.edge)>=0?'s19good':'s19under'}}">${{Number(r.edge)>=0?'+':''}}${{num(r.edge)}}</td><td class="${{cls}}"><b>${{esc(pick)}}</b>${{r.eligible?'':'<div class="s19muted">not actionable</div>'}}</td><td>${{r.confidence==null?esc(r.confidence_label||'—'):num(r.confidence)}}</td><td>${{r.projected_minutes==null?'—':num(r.projected_minutes)}}${{r.minutes_delta==null?'':`<div class="s19muted">Δ ${{Number(r.minutes_delta)>=0?'+':''}}${{num(r.minutes_delta)}}</div>`}}</td><td>${{esc(r.injury_status||'CLEAR')}}${{r.injury_adjusted?'<div class="s19muted">adjusted</div>':''}}</td><td>O ${{esc(r.best_over_book||'Consensus')}} ${{esc(r.best_over_price)}}<br>U ${{esc(r.best_under_book||'Consensus')}} ${{esc(r.best_under_price)}}</td></tr>`}}).join('')}}</tbody></table></div></div>`}}
 function rerenderProps(preserveScroll){{const r=root();if(!r)return;const old=document.querySelector('.s19scroll');const left=preserveScroll&&old?old.scrollLeft:0;const top=preserveScroll&&old?old.scrollTop:0;r.innerHTML=propsHtml();const next=document.querySelector('.s19scroll');if(next){{next.scrollLeft=left;next.scrollTop=top}}}}
 window.s19SetPropFilter=function(f){{propFilter=f;rerenderProps(false)}};
 window.s19SortProps=function(key){{if(propSort.key===key)propSort.dir=propSort.dir==='asc'?'desc':'asc';else propSort={{key:key,dir:'asc'}};rerenderProps(true)}};
 function bestHtml(){{const rows=D.best_bets||[];if(!rows.length)return `<div class="section">${{gate()}}<h2 class="mono">Best Bets · V5 Buy Signals</h2><div class="uiFreezeUnavailable">No current V5 buy signals cleared the model guardrails. Phase 2 fallback recommendations are disabled.</div></div>`;return `<div class="section">${{gate()}}<h2 class="mono">Best Bets · V5 Buy Signals</h2><div class="s19grid">${{rows.map(r=>`<div class="s19card"><div class="s19muted mono">V5 BUY SIGNAL</div><h3>${{esc(r.player||r.pick||r.selection||r.side)}}</h3><div>${{esc(r.game)}}</div><div class="s19badge">${{esc(r.market||r.stat||r.type)}}</div><div class="s19badge">${{esc(r.side||r.recommendation||r.action)}}</div><div class="s19muted">Edge ${{esc(r.edge??r.v5_edge??'—')}} · Confidence ${{esc(r.confidence??r.score??'—')}}</div></div>`).join('')}}</div></div>`}}
 function portfolioHtml(){{const rows=D.portfolio||[];if(!rows.length)return `<div class="section">${{gate()}}<h2 class="mono">Portfolio · V5 Live Portfolio</h2><div class="uiFreezeUnavailable">No current V5 portfolio positions are approved. Phase 2 candidate fallback and stake-pending cards are disabled.</div></div>`;return `<div class="section">${{gate()}}<h2 class="mono">Portfolio · V5 Live Portfolio</h2><div class="s19grid">${{rows.map(r=>`<div class="s19card"><div class="s19muted mono">V5 PORTFOLIO</div><h3>${{esc(r.player||r.pick||r.selection||r.side)}}</h3><div>${{esc(r.game)}}</div><div class="s19badge">${{esc(r.market||r.stat||r.type)}}</div><div class="s19badge">Stake ${{esc(r.stake??r.units??r.unit_size??'—')}}</div><div class="s19muted">Edge ${{esc(r.edge??r.v5_edge??'—')}} · Confidence ${{esc(r.confidence??r.score??'—')}}</div></div>`).join('')}}</div></div>`}}
 function install(){{if(window.__S19_M02_INSTALLED)return true;if(typeof window.render!=='function')return false;const old=window.render;window.__S19_M02_OLD_RENDER=old;window.render=function(view){{if(view==='games'||view==='props'||view==='best'||view==='portfolio'){{const r=root();if(!r)return old(view);syncTabs(view);r.innerHTML=view==='games'?gamesHtml():view==='props'?propsHtml():view==='best'?bestHtml():portfolioHtml();return}}return old(view)}};window.__S19_M02_INSTALLED=true;const hash=(location.hash||'').replace('#','');if(['games','props','best','portfolio'].includes(hash))window.render(hash);return true}}
 if(!install()){{let n=0;const t=setInterval(()=>{{n++;if(install()||n>30)clearInterval(t)}},100)}}
}})();
</script>
{END}\n'''

    html = HTML.read_text(encoding='utf-8')
    html = re.sub(re.escape(START) + r'.*?' + re.escape(END), '', html, flags=re.S)
    if '</body>' not in html:
        raise SystemExit('Dashboard shell missing closing body tag')
    html = html.replace('</body>', block + '\n</body>', 1)
    HTML.write_text(html, encoding='utf-8')
    print({'status': 'PASS', 'target_date': payload.get('target_date'), 'games': len(payload.get('games') or []), 'props': len(payload.get('player_props') or []), 'best_bets': len(payload.get('best_bets') or []), 'portfolio': len(payload.get('portfolio') or []), 'prediction_artifact_ready': True})


if __name__ == '__main__':
    main()
