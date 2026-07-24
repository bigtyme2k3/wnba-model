from __future__ import annotations

import json
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_ensemble_intelligence.json')

CSS = r'''<style id="v4-ensemble-intelligence-style">
.ensembleGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px}.ensembleCard{border:1px solid #263854;border-radius:16px;background:#091321;padding:14px}.ensembleHead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.ensembleScore{font-size:30px;font-weight:950}.ensembleGrade{font-size:18px;font-weight:950;color:#34e6a1}.ensembleMeta{color:#8fa0bd;font-size:11px;margin-top:4px}.ensembleBreakdown{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:12px}.ensembleMetric{border-top:1px solid #1d2d46;padding-top:6px;font-size:11px}.ensembleMetric b{display:block;font-size:14px}.ensembleReasons{margin-top:10px;color:#9eb0cc;font-size:11px}.ensembleSummary{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 14px}.ensembleChip{border:1px solid #263854;border-radius:999px;padding:7px 10px;font-size:11px}.ensembleWarn{color:#ffcf66}
</style>'''

SCRIPT = r'''<script id="v4-ensemble-intelligence-script">
(function(){
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const pct=v=>v==null?'—':(Number(v)*100).toFixed(1)+'%';
 function card(r){const b=r.component_breakdown||{};const metrics=Object.entries(b).map(([k,v])=>`<div class="ensembleMetric">${esc(k.replaceAll('_',' '))}<b>${esc(v.score)}</b><span>+${esc(v.contribution)}</span></div>`).join('');const reasons=(r.reasons||[]).map(x=>`<div>• ${esc(x)}</div>`).join('');return `<div class="ensembleCard"><div class="ensembleHead"><div><div class="ensembleGrade">${esc(r.grade)} · ${esc(r.ensemble_confidence)}</div><h3>${esc(r.player)} ${esc(r.side)} ${esc(r.market)} ${esc(r.line)}</h3><div class="ensembleMeta">${esc(r.game||'')} · ${esc(r.sportsbook||'Unknown book')} ${esc(r.odds??'')}</div></div><div class="ensembleScore">${esc(r.ensemble_score)}</div></div><div class="ensembleMeta">Calibrated ${pct(r.adaptive_probability)} · Evidence ${esc(r.evidence_count)}${r.calibration_extrapolated?' · <span class="ensembleWarn">extrapolated</span>':''}</div><div class="ensembleBreakdown">${metrics}</div><div class="ensembleReasons">${reasons}</div></div>`}
 window.ensembleIntelligence=function(){const p=(window.DATA&&DATA.ensemble_intelligence)||{};const s=p.summary||{};const rows=p.ranked_edges||[];return `<div class="section"><h2 class="mono">Ensemble Intelligence</h2><div class="small mono">Unified ranking across projections, form, market value, CLV, ROI, sample strength, and calibrated confidence.</div><div class="ensembleSummary"><span class="ensembleChip">${esc(s.candidates_ranked||0)} ranked</span><span class="ensembleChip">${esc(s.a_plus||0)} A+</span><span class="ensembleChip">${esc(s.high_or_better||0)} high+</span><span class="ensembleChip">Top ${esc(s.top_score??'—')}</span></div><div class="ensembleGrid">${rows.map(card).join('')||'<div class="empty mono">Awaiting the next live regular-season slate.</div>'}</div></div>`}
})();
</script>'''


def replace_block(html: str, start: str, end: str, replacement: str) -> str:
    i = html.find(start)
    if i < 0: return html
    j = html.find(end, i)
    if j < 0: return html
    return html[:i] + replacement.strip() + html[j + len(end):]


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    try:
        payload = json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
    except Exception:
        payload = {}
    html = HTML.read_text(encoding='utf-8')
    data = '<script id="v4-ensemble-intelligence-data">window.DATA=window.DATA||{};DATA.ensemble_intelligence=' + json.dumps(payload,separators=(',',':'),ensure_ascii=False) + ';</script>'
    html = replace_block(html,'<script id="v4-ensemble-intelligence-data">','</script>',data) if 'id="v4-ensemble-intelligence-data"' in html else html.replace('</body>',data+'</body>')
    html = replace_block(html,'<style id="v4-ensemble-intelligence-style">','</style>',CSS) if 'id="v4-ensemble-intelligence-style"' in html else html.replace('</head>',CSS+'</head>')
    html = replace_block(html,'<script id="v4-ensemble-intelligence-script">','</script>',SCRIPT) if 'id="v4-ensemble-intelligence-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8')
    print('Ensemble Intelligence dashboard blocks embedded')


if __name__ == '__main__':
    main()
