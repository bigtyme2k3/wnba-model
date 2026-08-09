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

    needs_build = not DATA.exists() or not AUDIT.exists()
    if not needs_build:
        try:
            payload = json.loads(DATA.read_text(encoding='utf-8'))
            audit = json.loads(AUDIT.read_text(encoding='utf-8'))
            needs_build = (
                payload.get('status') != 'READY'
                or audit.get('status') != 'READY'
                or str(payload.get('target_date') or '')[:10] != target
                or str(audit.get('target_date') or '')[:10] != target
            )
        except Exception:
            needs_build = True

    if needs_build:
        if not BUILDER.exists():
            raise SystemExit(f'Sprint 19 M02 builder missing: {BUILDER}')
        print({'status': 'BUILDING', 'module': 'SPRINT19-M02', 'target_date': target, 'reason': 'missing_or_stale_prediction_artifact'})
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
.s19table{{width:100%;border-collapse:collapse;font-size:12px}}.s19table th,.s19table td{{padding:9px;border-bottom:1px solid #1d2c43;text-align:left;vertical-align:top;white-space:nowrap}}
.s19scroll{{overflow:auto;max-height:72vh}}.s19good{{color:#3de6b0}}.s19under{{color:#77b7ff}}.s19pass{{color:#8190aa}}.s19muted{{color:#8190aa;font-size:11px}}
</style>
<script id="s19-m02-script">
(function(){{
 const D={raw}; window.WNBA_S19_M02=D;
 const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
 const num=(v,d=1)=>v==null||v===''?'—':Number(v).toFixed(d);
 const root=()=>document.getElementById('root');
 const gate=()=>`<div class="s19badge">SPRINT 19 M02 · ${{esc(D.target_date)}}</div>`;
 function injuryBadges(ctx){{ctx=ctx||{{}};const parts=[];if(ctx.out)parts.push(`<span class="s19badge s19bad">${{ctx.out}} OUT</span>`);if(ctx.questionable)parts.push(`<span class="s19badge s19warn">${{ctx.questionable}} Q</span>`);if(ctx.probable)parts.push(`<span class="s19badge">${{ctx.probable}} PROB</span>`);return parts.join('')||'<span class="s19badge">No listed injuries</span>'}}
 function gamesHtml(){{const games=D.games||[];return `<div class="section">${{gate()}}<h2 class="mono">Today's Games · Injury-Adjusted Predictions</h2><div class="s19muted mono">Every projection below was regenerated after the current official injury refresh.</div><div class="s19grid" style="margin-top:12px">${{games.map(g=>{{const p=g.projection||{{}},m=g.market||{{}},e=g.edge||{{}},r=g.recommendation||{{}},c=g.injury_context||{{}};return `<div class="s19card"><div class="s19muted mono">${{esc(g.game)}}</div><h3 class="mono">${{esc(g.away_team)}} ${{num(p.away_score)}} · ${{esc(g.home_team)}} ${{num(p.home_score)}}</h3>${{injuryBadges(c)}}<div class="s19metrics"><div class="s19metric">Win Probability<b>${{esc(g.home_team)}} ${{p.home_win_probability==null?'—':(Number(p.home_win_probability)*100).toFixed(1)+'%'}}</b></div><div class="s19metric">Spread<b>Book ${{esc(m.home_spread)}} · Model ${{num(p.model_home_spread)}}</b><span class="s19good">Edge ${{num(e.spread)}}</span></div><div class="s19metric">Total<b>Book ${{esc(m.total)}} · Model ${{num(p.total)}}</b><span class="s19good">Edge ${{num(e.total)}}</span></div><div class="s19metric">Recommendation<b>${{esc(r.spread||'PASS')}} · ${{esc(r.total||'PASS')}}</b>Conf ${{esc(g.confidence)}} · Grade ${{esc(g.model_grade)}}</div></div><div class="s19muted" style="margin-top:9px">Injury source ${{esc(c.generated_at_utc||D.injury_generated_at_utc)}}</div></div>`}}).join('')}}</div></div>`}}
 function propsHtml(){{const rows=D.player_props||[];return `<div class="section">${{gate()}}<h2 class="mono">Player Props · Model Predictions</h2><div class="s19muted mono">Book line vs injury-adjusted model projection. OUT/DOUBTFUL players are blocked; uncertain players remain non-actionable.</div><div class="s19scroll" style="margin-top:12px"><table class="s19table"><thead><tr><th>Player</th><th>Prop</th><th>Line</th><th>Model</th><th>Edge</th><th>Pick</th><th>Confidence</th><th>Minutes</th><th>Injury</th><th>Best O/U</th></tr></thead><tbody>${{rows.map(r=>{{const pick=String(r.recommendation||'PASS');const cls=pick==='OVER'?'s19good':pick==='UNDER'?'s19under':'s19pass';return `<tr><td><b>${{esc(r.player)}}</b><div class="s19muted">${{esc(r.team)}} · ${{esc(r.game)}}</div></td><td>${{esc(r.stat)}}</td><td>${{num(r.line)}}</td><td><b>${{num(r.model_projection)}}</b></td><td class="${{Number(r.edge)>=0?'s19good':'s19under'}}">${{Number(r.edge)>=0?'+':''}}${{num(r.edge)}}</td><td class="${{cls}}"><b>${{esc(pick)}}</b>${{r.eligible?'':'<div class="s19muted">not actionable</div>'}}</td><td>${{r.confidence==null?'—':num(r.confidence)}}</td><td>${{r.projected_minutes==null?'—':num(r.projected_minutes)}}${{r.minutes_delta==null?'':`<div class="s19muted">Δ ${{Number(r.minutes_delta)>=0?'+':''}}${{num(r.minutes_delta)}}</div>`}}</td><td>${{esc(r.injury_status||'CLEAR')}}${{r.injury_adjusted?'<div class="s19muted">adjusted</div>':''}}</td><td>O ${{esc(r.best_over_book)}} ${{esc(r.best_over_price)}}<br>U ${{esc(r.best_under_book)}} ${{esc(r.best_under_price)}}</td></tr>`}}).join('')}}</tbody></table></div></div>`}}
 function bestHtml(){{const rows=D.best_bets||[];if(!rows.length)return `<div class="section">${{gate()}}<h2 class="mono">Best Bets · V5 Buy Signals</h2><div class="uiFreezeUnavailable">No current V5 buy signals cleared the model guardrails. Phase 2 fallback recommendations are disabled.</div></div>`;return `<div class="section">${{gate()}}<h2 class="mono">Best Bets · V5 Buy Signals</h2><div class="s19grid">${{rows.map(r=>`<div class="s19card"><div class="s19muted mono">V5 BUY SIGNAL</div><h3>${{esc(r.player||r.pick||r.selection||r.side)}}</h3><div>${{esc(r.game)}}</div><div class="s19badge">${{esc(r.market||r.stat||r.type)}}</div><div class="s19badge">${{esc(r.side||r.recommendation||r.action)}}</div><div class="s19muted">Edge ${{esc(r.edge??r.v5_edge??'—')}} · Confidence ${{esc(r.confidence??r.score??'—')}}</div></div>`).join('')}}</div></div>`}}
 function install(){{if(window.__S19_M02_INSTALLED)return true;if(typeof window.render!=='function')return false;const old=window.render;window.__S19_M02_OLD_RENDER=old;window.render=function(view){{if(view==='games'||view==='props'||view==='best'){{const r=root();if(!r)return old(view);if(typeof window.chrome==='function')try{{window.chrome(view)}}catch(e){{}};r.innerHTML=view==='games'?gamesHtml():view==='props'?propsHtml():bestHtml();return}}return old(view)}};window.__S19_M02_INSTALLED=true;const hash=(location.hash||'').replace('#','');if(['games','props','best'].includes(hash))window.render(hash);return true}}
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
    print({'status': 'PASS', 'target_date': payload.get('target_date'), 'games': len(payload.get('games') or []), 'props': len(payload.get('player_props') or []), 'best_bets': len(payload.get('best_bets') or []), 'prediction_artifact_ready': True})


if __name__ == '__main__':
    main()
