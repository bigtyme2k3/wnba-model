from __future__ import annotations

from pathlib import Path

HTML = Path('docs/index.html')

CSS = r'''<style id="v4-prop-bet-cards-style">
.betCardGrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:14px 0}.betCard{border:1px solid #263854;background:linear-gradient(180deg,#101a2d,#08101c);border-radius:18px;padding:16px}.betCardTop{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.betGrade{font-size:28px;font-weight:900;color:#00e39b}.betMeta{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0}.betMetrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.betMetric{border:1px solid #1e2a43;border-radius:12px;padding:10px;background:#07101d}.betMetric b{display:block;font-size:18px;margin-top:4px}.betList{margin:10px 0 0;padding-left:18px;color:#b8c8e8}.betRisk{color:#ffd166}.betNotice{border:1px solid #304365;border-radius:14px;padding:12px;color:#b8c8e8;background:#0a1322}.betSectionTitle{display:flex;justify-content:space-between;gap:12px;align-items:center}@media(max-width:900px){.betCardGrid{grid-template-columns:1fr}.betMetrics{grid-template-columns:1fr 1fr}}
</style>'''

SCRIPT = r'''<script id="v4-prop-bet-cards-script">
(function(){
 const arr=v=>Array.isArray(v)?v:[];
 const esc=v=>typeof E==='function'?E(v):String(v??'');
 const val=(v,d='—')=>v===undefined||v===null||v===''?d:v;
 const pct=v=>v===undefined||v===null?'—':`${(Number(v)*100).toFixed(1)}%`;
 const money=v=>v===undefined||v===null?'—':`${Number(v)>=0?'+':''}${(Number(v)*100).toFixed(1)}%`;
 function cards(){return arr(DATA.master?.best_bets).filter(x=>x&&x.source==='calibrated_prop_bet_card_v1')}
 function trend(c,key){const t=c?.trend?.[key]||{};return t.sample?`${t.hits}/${t.sample} (${Math.round(Number(t.hit_rate||0)*100)}%)`:'—'}
 function card(c){
   const reasons=arr(c.reasons).map(x=>`<li>${esc(x)}</li>`).join('');
   const risks=arr(c.risks).map(x=>`<li>${esc(x)}</li>`).join('');
   return `<div class="betCard"><div class="betCardTop"><div><div class="label mono">${esc(val(c.action,'WATCH'))}</div><h3 class="mono">${esc(c.player)} ${esc(c.stat)} ${esc(c.side)}</h3><div class="small mono">${esc(c.game)} · ${esc(val(c.sportsbook))} ${esc(val(c.odds))}</div></div><div class="betGrade mono">${esc(val(c.letter_grade))}</div></div><div class="betMeta"><span class="chip mono">Line ${esc(val(c.line))}</span><span class="chip mono">Projection ${esc(val(c.projection))}</span><span class="chip mono">Research grade ${esc(val(c.research_grade))}</span><span class="chip mono">${esc(val(c.book_count,0))} books</span></div><div class="betMetrics"><div class="betMetric"><div class="label mono">Sim Win %</div><b class="mono">${pct(c.simulation_probability)}</b></div><div class="betMetric"><div class="label mono">Expected Value</div><b class="mono">${money(c.expected_value)}</b></div><div class="betMetric"><div class="label mono">L10 Hit</div><b class="mono">${trend(c,'last10')}</b></div><div class="betMetric"><div class="label mono">Stake</div><b class="mono">${esc(val(c.recommended_units))}</b></div></div>${reasons?`<ul class="betList">${reasons}</ul>`:''}${risks?`<ul class="betList betRisk">${risks}</ul>`:''}</div>`
 }
 const originalProps=window.props||props;
 window.props=function(){
   const ranked=cards();
   const summary=`<div class="section"><div class="betSectionTitle"><div><h2 class="mono">Player Props & Best Bets</h2><div class="small mono">Research grade is not a win probability. Simulation probability and expected value are shown separately.</div></div><span class="chip mono">${ranked.length} ranked</span></div>${ranked.length?`<div class="betCardGrid">${ranked.map(card).join('')}</div>`:'<div class="betNotice mono">No props currently meet the BET or LEAN thresholds. The full prop board remains available below.</div>'}</div>`;
   return summary+originalProps();
 };
 window.best=window.props;
})();
</script>'''


def replace_block(html: str, marker: str, closing: str, replacement: str) -> str:
    start = html.find(marker)
    if start < 0: return html
    end = html.find(closing, start)
    if end < 0: return html
    return html[:start] + replacement.strip() + html[end + len(closing):]


def main() -> None:
    if not HTML.exists(): raise SystemExit('docs/index.html missing')
    html = HTML.read_text(encoding='utf-8')
    html = replace_block(html,'<style id="v4-prop-bet-cards-style">','</style>',CSS) if 'id="v4-prop-bet-cards-style"' in html else html.replace('</head>',CSS+'</head>')
    html = replace_block(html,'<script id="v4-prop-bet-cards-script">','</script>',SCRIPT) if 'id="v4-prop-bet-cards-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8')
    print('Dashboard prop bet cards active')


if __name__=='__main__': main()
