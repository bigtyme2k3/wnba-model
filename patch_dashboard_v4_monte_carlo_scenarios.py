from __future__ import annotations

import json
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_monte_carlo_scenarios.json')

CSS = r'''<style id="v4-monte-carlo-scenarios-style">
.mcGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.mcCard{border:1px solid #263854;border-radius:16px;background:#091321;padding:14px}.mcHead{display:flex;justify-content:space-between;gap:12px}.mcProb{font-size:30px;font-weight:950;color:#34e6a1}.mcRisk{font-size:12px;font-weight:900}.mcMeta{font-size:11px;color:#8fa0bd;margin-top:4px}.mcMetrics{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:12px}.mcMetric{border-top:1px solid #1d2d46;padding-top:7px;font-size:10px;color:#8fa0bd}.mcMetric b{display:block;font-size:14px;color:#eef4ff}.mcScenario{border-top:1px solid #1d2d46;margin-top:8px;padding-top:7px;font-size:10px}.mcScenario b{color:#cfe0ff}.mcReasons{margin-top:10px;font-size:11px;color:#9eb0cc}.mcSummary{display:flex;gap:9px;flex-wrap:wrap;margin:10px 0 14px}.mcChip{border:1px solid #263854;border-radius:999px;padding:7px 10px;font-size:11px}.mcWarn{color:#ffcf66}.mcPositive{color:#34e6a1}.mcNegative{color:#ff637d}
</style>'''

SCRIPT = r'''<script id="v4-monte-carlo-scenarios-script">
(function(){
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const pct=v=>v==null?'—':(Number(v)*100).toFixed(1)+'%';
 const signed=v=>v==null?'—':`${Number(v)>=0?'+':''}${Number(v).toFixed(1)}%`;
 function card(r){const scenarios=(r.scenarios||[]).map(s=>`<div class="mcScenario"><b>${esc(s.scenario.replaceAll('_',' '))}</b> · ${pct(s.weight)} weight · ${pct(r.side==='UNDER'?s.under_probability:s.over_probability)} ${esc(r.side)}</div>`).join('');const reasons=(r.explanation||[]).map(x=>`<div>• ${esc(x)}</div>`).join('');const ev=Number(r.expected_value_percent||0);return `<div class="mcCard"><div class="mcHead"><div><div class="mcRisk">${esc(r.risk_band)} RISK${r.calibration_extrapolated?' · <span class="mcWarn">EXTRAPOLATED</span>':''}</div><h3>${esc(r.player)} ${esc(r.side)} ${esc(r.stat)} ${esc(r.line)}</h3><div class="mcMeta">${esc(r.game||'')} · ${esc(r.sportsbook||'Unknown book')} ${esc(r.odds??'')}</div></div><div class="mcProb">${pct(r.simulation_probability)}</div></div><div class="mcMetrics"><div class="mcMetric">Median<b>${esc(r.median)}</b></div><div class="mcMetric">80% range<b>${esc(r.p10)}–${esc(r.p90)}</b></div><div class="mcMetric">Expected value<b class="${ev>=0?'mcPositive':'mcNegative'}">${signed(ev)}</b></div><div class="mcMetric">Market implied<b>${pct(r.market_implied_probability)}</b></div><div class="mcMetric">Probability edge<b>${pct(r.probability_edge)}</b></div><div class="mcMetric">History<b>${esc(r.history_games)} games</b></div></div>${scenarios}<div class="mcReasons">${reasons}</div></div>`}
 window.monteCarloScenarios=function(){const p=(window.DATA&&DATA.monte_carlo_scenarios)||{};const s=p.summary||{};const rows=p.all_simulations||[];return `<div class="section"><h2 class="mono">Monte Carlo Scenario Lab</h2><div class="small mono">10,000-outcome player-prop simulations with minutes, blowout, foul-trouble, and injury scenarios.</div><div class="mcSummary"><span class="mcChip">${esc(s.candidates_simulated||0)} simulated</span><span class="mcChip">${esc(s.positive_ev||0)} positive EV</span><span class="mcChip">${esc(s.probability_60_plus||0)} at 60%+</span><span class="mcChip">${esc(s.low_risk||0)} low risk</span></div><div class="mcGrid">${rows.map(card).join('')||'<div class="empty mono">Awaiting the next live regular-season slate.</div>'}</div></div>`}
})();
</script>'''


def replace_block(html: str, start: str, end: str, replacement: str) -> str:
    i = html.find(start)
    if i < 0:
        return html
    j = html.find(end, i)
    if j < 0:
        return html
    return html[:i] + replacement.strip() + html[j + len(end):]


def patch_navigation(html: str) -> str:
    if "['simulation','Simulation']" not in html:
        html = html.replace("['ensemble','Ensemble'],['best','Best Bets']", "['ensemble','Ensemble'],['simulation','Simulation'],['best','Best Bets']")
    if "function simulationView()" not in html:
        html = html.replace("function ensembleView(){const body=safe(window.ensembleIntelligence);return body||'<div class=\"section\"><div class=\"empty mono\">Ensemble data is not available yet.</div></div>'}", "function ensembleView(){const body=safe(window.ensembleIntelligence);return body||'<div class=\"section\"><div class=\"empty mono\">Ensemble data is not available yet.</div></div>'}function simulationView(){const body=safe(window.monteCarloScenarios);return body||'<div class=\"section\"><div class=\"empty mono\">Simulation data is not available yet.</div></div>'}")
    if "else if(view==='simulation')" not in html:
        html = html.replace("else if(view==='ensemble')root.innerHTML=ensembleView();else if(view==='best')", "else if(view==='ensemble')root.innerHTML=ensembleView();else if(view==='simulation')root.innerHTML=simulationView();else if(view==='best')")
    return html


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    try:
        payload = json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
    except Exception:
        payload = {}
    html = HTML.read_text(encoding='utf-8')
    data = '<script id="v4-monte-carlo-scenarios-data">window.DATA=window.DATA||{};DATA.monte_carlo_scenarios=' + json.dumps(payload,separators=(',',':'),ensure_ascii=False) + ';</script>'
    html = replace_block(html,'<script id="v4-monte-carlo-scenarios-data">','</script>',data) if 'id="v4-monte-carlo-scenarios-data"' in html else html.replace('</body>',data+'</body>')
    html = replace_block(html,'<style id="v4-monte-carlo-scenarios-style">','</style>',CSS) if 'id="v4-monte-carlo-scenarios-style"' in html else html.replace('</head>',CSS+'</head>')
    html = replace_block(html,'<script id="v4-monte-carlo-scenarios-script">','</script>',SCRIPT) if 'id="v4-monte-carlo-scenarios-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    html = patch_navigation(html)
    HTML.write_text(html,encoding='utf-8')
    print('Sprint 10 Monte Carlo Scenario tab embedded')


if __name__ == '__main__':
    main()
