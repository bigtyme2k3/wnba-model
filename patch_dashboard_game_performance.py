"""Expose Game Performance as a single routed renderer for the locked V4 UI."""
from __future__ import annotations

import json
import re
from pathlib import Path

HTML = Path("docs/index.html")
DATA = Path("data/dashboard/wnba_game_performance.json")
STYLE_ID = "game-performance-route-style"
SCRIPT_ID = "game-performance-route-script"

STYLE = r'''<style id="game-performance-route-style">
.gp-summary{display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:12px;margin:14px 0 20px}.gp-metric,.gp-card{background:#091625;border:1px solid #1d334b;border-radius:16px;padding:16px}.gp-metric span,.gp-grid span{display:block;color:#8ea1b6;font-size:12px;text-transform:uppercase;letter-spacing:.08em}.gp-metric b{display:block;font-size:25px;margin-top:7px;color:#eef5ff}.gp-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.gp-card h3{margin:4px 0 14px;color:#f1f5f9}.gp-date{color:#20d89b;font-size:12px}.gp-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.gp-grid div{background:#07111e;border:1px solid #162a40;border-radius:10px;padding:10px}.gp-grid b,.gp-grid small,.gp-grid em{display:block;margin-top:5px}.gp-grid em.win{color:#20d89b}.gp-grid em.loss{color:#ff667d}.gp-grid em.pass{color:#f4bf4f}@media(max-width:900px){.gp-summary{grid-template-columns:repeat(2,1fr)}.gp-cards{grid-template-columns:1fr}.gp-grid{grid-template-columns:repeat(2,1fr)}}
</style>'''


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    payload = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    raw = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    script = r'''<script id="game-performance-route-script">(function(){
const D=__PAYLOAD__;window.WNBA_GAME_PERFORMANCE=D;
const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const pct=v=>{const n=Number(v);return Number.isFinite(n)?(n*100).toFixed(1)+'%':'—'};
const rec=o=>{o=o||{};return `${Number(o.wins||0)}-${Number(o.losses||0)}-${Number(o.pushes||0)}`};
window.fullGamePerformance=function(){const s=D.summary||{},sp=D.spread||{},to=D.total||{},rows=Array.isArray(D.recent_games)?D.recent_games:[];const cards=rows.slice(0,20).map(r=>`<article class="gp-card"><div class="gp-date mono">${esc(r.target_date||'')}</div><h3 class="mono">${esc(r.game||'Unknown game')}</h3><div class="gp-grid"><div><span>Spread pick</span><b>${esc(r.spread_recommendation||r.spread_pick||'PASS')}</b><em class="${String(r.spread_result||'').toLowerCase()}">${esc(r.spread_result||'PENDING')}</em></div><div><span>Total pick</span><b>${esc(r.total_recommendation||r.total_pick||'PASS')}</b><em class="${String(r.total_result||'').toLowerCase()}">${esc(r.total_result||'PENDING')}</em></div><div><span>Projected</span><b>${esc(r.projected_away_score)}–${esc(r.projected_home_score)}</b><small>Total ${esc(r.projected_total)}</small></div><div><span>Actual</span><b>${esc(r.actual_away_score)}–${esc(r.actual_home_score)}</b><small>Total ${esc(r.actual_total)}</small></div></div></article>`).join('');return `<div class="section"><h2 class="mono">Game Performance</h2><p class="small mono">Frozen pregame spreads, totals and projected scores graded against final results.</p><div class="gp-summary"><div class="gp-metric"><span>Archived games</span><b>${Number(s.archived_games||0)}</b></div><div class="gp-metric"><span>Graded games</span><b>${Number(s.graded_games||0)}</b></div><div class="gp-metric"><span>Spread record</span><b>${rec(sp)}</b><small>${pct(sp.hit_rate)}</small></div><div class="gp-metric"><span>Total record</span><b>${rec(to)}</b><small>${pct(to.hit_rate)}</small></div><div class="gp-metric"><span>Margin MAE</span><b>${esc(s.avg_margin_error)}</b></div><div class="gp-metric"><span>Total MAE</span><b>${esc(s.avg_total_error)}</b></div></div><div class="gp-cards">${cards||'<div class="gp-card">No graded game cards yet.</div>'}</div></div>`};
})();</script>'''.replace('__PAYLOAD__', raw)
    html = HTML.read_text(encoding="utf-8")
    # Remove both the old static injector and any prior routed version.
    html = re.sub(r'<!-- WNBA_GAME_PERFORMANCE_START -->.*?<!-- WNBA_GAME_PERFORMANCE_END -->', '', html, flags=re.S)
    html = re.sub(r'<style id="game-performance-route-style">.*?</style>', '', html, flags=re.S)
    html = re.sub(r'<script id="game-performance-route-script">.*?</script>', '', html, flags=re.S)
    html = html.replace('</head>', STYLE + '\n</head>', 1)
    html = html.replace('</body>', script + '\n</body>', 1)
    HTML.write_text(html, encoding="utf-8")
    print({'status':'PASS','renderer':'fullGamePerformance','standalone_nav':False})


if __name__ == "__main__":
    main()
