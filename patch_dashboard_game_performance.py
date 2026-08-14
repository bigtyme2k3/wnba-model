"""Expose Game Performance as a single routed renderer for the locked UI."""
from __future__ import annotations

import json
import re
from pathlib import Path

from wnba_game_performance import build as build_game_performance

HTML = Path("docs/index.html")
DATA = Path("data/dashboard/wnba_game_performance.json")

STYLE = r'''<style id="game-performance-route-style">
.gp-summary{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:12px;margin:14px 0 16px}.gp-metric,.gp-card,.gp-panel{background:#091625;border:1px solid #1d334b;border-radius:16px;padding:16px}.gp-metric span,.gp-grid span,.gp-panel span{display:block;color:#8ea1b6;font-size:12px;text-transform:uppercase;letter-spacing:.08em}.gp-metric b{display:block;font-size:24px;margin-top:7px;color:#eef5ff}.gp-metric small{color:#8ea1b6}.gp-alert{border:1px solid #6b5724;background:#171307;color:#ffd166;border-radius:12px;padding:11px 13px;margin:10px 0;font-size:12px}.gp-panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:0 0 16px}.gp-panel{overflow-x:auto}.gp-panel h3{margin:0 0 10px;font-size:15px}.gp-table{width:100%;border-collapse:collapse;font-size:12px;min-width:520px}.gp-table th,.gp-table td{text-align:left;border-bottom:1px solid #162a40;padding:7px 5px}.gp-table th{color:#8ea1b6;font-weight:600}.gp-pos{color:#20d89b}.gp-neg{color:#ff667d}.gp-warn{color:#f4bf4f}.gp-archive{background:#07111e;border:1px solid #1d334b;border-radius:16px;padding:12px;margin-top:12px}.gp-archive-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:4px 4px 12px}.gp-archive-head h3{margin:0}.gp-scroll{max-height:58vh;overflow-y:auto;overscroll-behavior:contain;padding-right:5px}.gp-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.gp-card{padding:13px}.gp-card h3{margin:4px 0 12px;color:#f1f5f9;font-size:16px}.gp-date{color:#20d89b;font-size:11px}.gp-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.gp-grid div{background:#07111e;border:1px solid #162a40;border-radius:10px;padding:8px}.gp-grid b,.gp-grid small,.gp-grid em{display:block;margin-top:4px}.gp-grid em.win{color:#20d89b}.gp-grid em.loss{color:#ff667d}.gp-grid em.pass{color:#f4bf4f}@media(max-width:900px){.gp-summary{grid-template-columns:repeat(2,1fr)}.gp-panels{grid-template-columns:1fr}.gp-cards{grid-template-columns:1fr}.gp-grid{grid-template-columns:repeat(2,1fr)}.gp-scroll{max-height:62vh}}
</style>'''


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    build_game_performance()
    payload = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    raw = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    script = r'''<script id="game-performance-route-script">(function(){
const D=__PAYLOAD__;window.WNBA_GAME_PERFORMANCE=D;
const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const pct=v=>{if(v===null||v===undefined||v==='')return '—';const n=Number(v);return Number.isFinite(n)?(n*100).toFixed(1)+'%':'—'};
const fixed=(v,d=2)=>{if(v===null||v===undefined||v==='')return '—';const n=Number(v);return Number.isFinite(n)?n.toFixed(d):'—'};
const rec=o=>{o=(o&&o.record)?o.record:(o||{});return `${Number(o.wins||0)}-${Number(o.losses||0)}-${Number(o.pushes||0)}`};
const bias=(v,label)=>{const n=Number(v);if(!Number.isFinite(n))return '—';const direction=n>0?'high':n<0?'low':'neutral';return `${Math.abs(n).toFixed(2)} ${label} ${direction}`};
const calRows=c=>(c?.buckets||[]).map(b=>`<tr><td>${esc(b.label)}</td><td>${Number(b.samples||0)}</td><td>${pct(b.avg_probability)}</td><td>${pct(b.hit_rate)}</td><td>${pct(b.shrunk_empirical_probability)}</td><td>${pct(b.wilson_low_95)}–${pct(b.wilson_high_95)}</td><td class="${b.bucket_ready?'gp-pos':'gp-warn'}">${b.bucket_ready?'Usable':'Small n'}</td></tr>`).join('');
const edgeRows=a=>(a||[]).map(b=>`<tr><td>${esc(b.label)}</td><td>${Number(b.samples||0)}</td><td>${Number(b.wins||0)}-${Number(b.losses||0)}-${Number(b.pushes||0)}</td><td>${pct(b.hit_rate)}</td><td class="${b.sample_sufficient?'gp-pos':'gp-warn'}">${b.sample_sufficient?'Usable':'Small n'}</td></tr>`).join('');
window.fullGamePerformance=function(){
 const s=D.summary||{},sp=D.spread||{},to=D.total||{},rows=Array.isArray(D.recent_games)?D.recent_games:[];
 const cards=rows.map(r=>`<article class="gp-card"><div class="gp-date mono">${esc(r.target_date||'')}</div><h3 class="mono">${esc(r.game||'Unknown game')}</h3><div class="gp-grid"><div><span>Winner</span><b>${esc(r.predicted_winner||'—')}</b><em class="${String(r.winner_result||'').toLowerCase()}">${esc(r.winner_result||'—')}</em></div><div><span>Spread</span><b>${esc(r.spread_recommendation||'PASS')}</b><em class="${String(r.spread_result||'').toLowerCase()}">${esc(r.spread_result||'PENDING')}</em></div><div><span>Total</span><b>${esc(r.total_recommendation||'PASS')}</b><em class="${String(r.total_result||'').toLowerCase()}">${esc(r.total_result||'PENDING')}</em></div><div><span>Score</span><b>${esc(r.projected_away_score)}–${esc(r.projected_home_score)}</b><small>Actual ${esc(r.actual_away_score)}–${esc(r.actual_home_score)}</small></div><div><span>Margin error</span><b>${fixed(r.margin_error)}</b><small>Bias ${fixed(r.margin_bias)}</small></div><div><span>Total error</span><b>${fixed(r.total_error)}</b><small>Bias ${fixed(r.total_bias)}</small></div><div><span>Spread edge</span><b>${fixed(r.spread_edge)}</b><small>Prob ${pct(r.spread_probability)}</small></div><div><span>Total edge</span><b>${fixed(r.total_edge)}</b><small>Prob ${pct(r.total_probability)}</small></div></div></article>`).join('');
 return `<div class="section"><h2 class="mono">Game Performance</h2><p class="small mono">Recommended wager results and broader forecast calibration are reported separately. No live model parameter changes occur until readiness gates pass.</p>
 <div class="gp-alert mono">Calibration status: Spread ${esc(sp.calibration?.status||'COLLECTING')} · Total ${esc(to.calibration?.status||'COLLECTING')}. Current empirical adjustments remain research-only.</div><div class="gp-summary"><div class="gp-metric"><span>Archive coverage</span><b>${Number(s.graded_games||0)}/${Number(s.archived_games||0)}</b><small>${pct(s.grade_coverage)} graded</small></div><div class="gp-metric"><span>Winner accuracy</span><b>${pct(s.winner_accuracy)}</b><small>${Number(s.winner_correct||0)}/${Number(s.winner_decisions||0)}</small></div><div class="gp-metric"><span>Spread recommendations</span><b>${rec(sp)}</b><small>${pct(sp.hit_rate)} · ${esc(sp.display_status||'PRELIMINARY')} n=${Number(sp.decisions||0)}</small></div><div class="gp-metric"><span>Total recommendations</span><b>${rec(to)}</b><small>${pct(to.hit_rate)} · ${esc(to.display_status||'PRELIMINARY')} n=${Number(to.decisions||0)}</small></div><div class="gp-metric"><span>Margin MAE</span><b>${fixed(s.avg_margin_error)}</b><small>${bias(s.margin_bias,'pts')}</small></div><div class="gp-metric"><span>Total MAE</span><b>${fixed(s.avg_total_error)}</b><small>${bias(s.total_bias,'pts')}</small></div><div class="gp-metric"><span>Away score MAE</span><b>${fixed(s.away_score_mae)}</b></div><div class="gp-metric"><span>Home score MAE</span><b>${fixed(s.home_score_mae)}</b></div></div>
 <div class="gp-panels"><div class="gp-panel"><h3 class="mono">Spread Forecast Calibration</h3><p class="small mono">${esc(sp.calibration?.diagnosis||'COLLECTING')} · Brier ${fixed(sp.calibration?.brier_score,4)} · ECE ${pct(sp.calibration?.expected_calibration_error)} · n=${Number(sp.calibration?.samples||0)}</p><table class="gp-table"><thead><tr><th>Raw band</th><th>N</th><th>Avg raw</th><th>Hit</th><th>Shrunk</th><th>95% CI</th><th>Status</th></tr></thead><tbody>${calRows(sp.calibration)||'<tr><td colspan="7">Not enough graded probability data.</td></tr>'}</tbody></table></div><div class="gp-panel"><h3 class="mono">Total Forecast Calibration</h3><p class="small mono">${esc(to.calibration?.diagnosis||'COLLECTING')} · Brier ${fixed(to.calibration?.brier_score,4)} · ECE ${pct(to.calibration?.expected_calibration_error)} · n=${Number(to.calibration?.samples||0)}</p><table class="gp-table"><thead><tr><th>Raw band</th><th>N</th><th>Avg raw</th><th>Hit</th><th>Shrunk</th><th>95% CI</th><th>Status</th></tr></thead><tbody>${calRows(to.calibration)||'<tr><td colspan="7">Not enough graded probability data.</td></tr>'}</tbody></table></div><div class="gp-panel"><h3 class="mono">Spread Edge Research</h3><table class="gp-table"><thead><tr><th>|Edge|</th><th>N</th><th>Record</th><th>Hit</th><th>Status</th></tr></thead><tbody>${edgeRows(sp.edge_buckets)||'<tr><td colspan="5">No graded edge buckets.</td></tr>'}</tbody></table></div><div class="gp-panel"><h3 class="mono">Total Edge Research</h3><table class="gp-table"><thead><tr><th>|Edge|</th><th>N</th><th>Record</th><th>Hit</th><th>Status</th></tr></thead><tbody>${edgeRows(to.edge_buckets)||'<tr><td colspan="5">No graded edge buckets.</td></tr>'}</tbody></table></div></div>
 <div class="gp-archive"><div class="gp-archive-head"><h3 class="mono">Graded Game Archive</h3><span class="small mono">${rows.length} recent graded games · scroll inside</span></div><div class="gp-scroll"><div class="gp-cards">${cards||'<div class="gp-card">No graded game cards yet.</div>'}</div></div></div></div>`;
};
})();</script>'''.replace('__PAYLOAD__', raw)
    html = HTML.read_text(encoding="utf-8")
    html = re.sub(r'<!-- WNBA_GAME_PERFORMANCE_START -->.*?<!-- WNBA_GAME_PERFORMANCE_END -->', '', html, flags=re.S)
    html = re.sub(r'<style id="game-performance-route-style">.*?</style>', '', html, flags=re.S)
    html = re.sub(r'<script id="game-performance-route-script">.*?</script>', '', html, flags=re.S)
    html = html.replace('</head>', STYLE + '\n</head>', 1)
    html = html.replace('</body>', script + '\n</body>', 1)
    HTML.write_text(html, encoding="utf-8")
    print({'status':'PASS','renderer':'fullGamePerformance','standalone_nav':False,'archive_scroll':True,'grading_v2':True})


if __name__ == "__main__":
    main()
