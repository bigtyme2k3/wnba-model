from __future__ import annotations

import json
from pathlib import Path

HTML = Path("docs/index.html")
DATA = Path("data/dashboard/wnba_daily_edges.json")

CSS = r'''<style id="v4-daily-edges-style">
.edgeToolbar{display:grid;grid-template-columns:1fr repeat(3,minmax(130px,.35fr));gap:9px;margin:14px 0}.edgeToolbar input,.edgeToolbar select{background:#07101d;border:1px solid #263854;color:#fff;border-radius:12px;padding:11px}.edgeKpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}.edgeKpi{border:1px solid #263854;border-radius:14px;background:#08101c;padding:12px}.edgeKpi b{display:block;font-size:22px;color:#34e6a1}.edgeGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:12px}.edgeCard{border:1px solid #263854;border-radius:16px;background:#08101c;padding:14px}.edgeTop{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}.edgeScore{font-size:29px;font-weight:950;color:#34e6a1}.edgeConfidence{font-size:10px;border:1px solid #36517b;border-radius:999px;padding:4px 8px}.edgeLine{font-size:18px;font-weight:950;margin-top:5px}.edgeBook{color:#98a9c5;font-size:11px}.edgeComponents{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:11px}.edgeComponent{border-top:1px solid #1d2d46;padding-top:6px;color:#8fa0bd;font-size:9px}.edgeComponent b{display:block;color:#eaf1ff;font-size:12px}.edgeEvidence{margin-top:10px;color:#a9b8d2;font-size:11px}.edgeEvidence div{margin:3px 0}.edgeMissing{margin-top:9px;color:#ffbf69;font-size:10px}.edgeQa{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin-top:12px}.edgeQaCard{border:1px solid #263854;border-radius:12px;padding:10px;background:#0a1322}.edgeQaCard h4{margin:0 0 7px}.edgeQaRow{display:flex;justify-content:space-between;font-size:10px;margin:4px 0}.edgeEmpty{padding:28px;text-align:center;color:#8fa0bd}@media(max-width:800px){.edgeToolbar,.edgeKpis{grid-template-columns:1fr 1fr}.edgeComponents{grid-template-columns:repeat(2,1fr)}}
</style>'''

SCRIPT = r'''<script id="v4-daily-edges-script">
(function(){
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const n=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
 const pct=v=>v==null?'—':(Number(v)*100).toFixed(0)+'%';
 const odds=v=>{const x=n(v);return x==null?'—':(x>0?'+'+x:String(x))};
 function comp(r,key,label){return `<div class="edgeComponent">${label}<b>${esc(r.components?.[key]??'—')}</b></div>`}
 function card(r){const ev=(r.evidence||[]).map(x=>`<div>• ${esc(x)}</div>`).join('');const miss=(r.missing_evidence||[]).join(', ');return `<div class="edgeCard"><div class="edgeTop"><div><div class="edgeScore">${esc(r.edge_score)}</div><span class="edgeConfidence">${esc(r.confidence)}</span></div><div style="text-align:right"><div class="edgeLine">${esc(r.player)} ${esc(r.side)} ${esc(r.market)} ${esc(r.line)}</div><div class="edgeBook">${esc(r.sportsbook||'Unknown book')} · ${odds(r.odds)} · ${esc(r.market_type||'')}</div><div class="edgeBook">${esc(r.game||'')}</div></div></div><div class="edgeComponents">${comp(r,'projection','Projection')}${comp(r,'recent_form','Recent')}${comp(r,'season_history','Season')}${comp(r,'market_value','Value')}${comp(r,'clv','CLV')}${comp(r,'roi','ROI')}${comp(r,'sample_strength','Sample')}${`<div class="edgeComponent">Evidence<b>${esc(r.evidence_count??0)}/6</b></div>`}</div><div class="edgeEvidence">${ev||'<div>No supporting evidence details.</div>'}</div>${miss?`<div class="edgeMissing">Missing: ${esc(miss)}</div>`:''}</div>`}
 function qaCard(title,obj,format){return `<div class="edgeQaCard"><h4>${esc(title)}</h4>${Object.entries(obj||{}).map(([k,v])=>`<div class="edgeQaRow"><span>${esc(k)}</span><b>${esc(format?format(v):v)}</b></div>`).join('')||'<div class="small">No data</div>'}</div>`}
 function render(){const p=(window.DATA&&DATA.daily_edges)||{};const rows=Array.isArray(p.top_edges)?p.top_edges:[];const s=p.summary||{},qa=p.qa||{};setTimeout(window.drawDailyEdges,0);return `<div class="section"><h2 class="mono">Daily Edges</h2><div class="small mono">Transparent rankings only. HIGH confidence is withheld until evidence and calibration gates are met.</div><div class="edgeKpis"><div class="edgeKpi">Top score<b>${esc(s.top_score??'—')}</b></div><div class="edgeKpi">HIGH<b>${esc(s.high_confidence||0)}</b></div><div class="edgeKpi">MODERATE<b>${esc(s.moderate_confidence||0)}</b></div><div class="edgeKpi">Candidates<b>${esc(s.candidates_scored||0)}</b></div></div><div class="edgeToolbar"><input id="edgePlayer" placeholder="Player" oninput="drawDailyEdges()"><select id="edgeConfidence" onchange="drawDailyEdges()"><option value="">All confidence</option><option>HIGH</option><option>MODERATE</option><option>LOW</option></select><select id="edgeType" onchange="drawDailyEdges()"><option value="">All markets</option><option value="standard">Standard</option><option value="alternate">Alternate</option></select><select id="edgeBook" onchange="drawDailyEdges()"><option value="">All books</option>${[...new Set(rows.map(r=>r.sportsbook).filter(Boolean))].sort().map(x=>`<option>${esc(x)}</option>`).join('')}</select></div><div id="dailyEdgeRows" class="edgeGrid"></div><div class="section"><h3 class="mono">Edge QA</h3><div class="edgeQa">${qaCard('Score distribution',qa.score_distribution)}${qaCard('Evidence coverage',qa.evidence_coverage_rates,pct)}${qaCard('Missing evidence',qa.missing_evidence_counts)}${qaCard('Component averages',qa.component_averages)}</div><div class="small mono" style="margin-top:10px">${esc(qa.high_confidence_gate||'')}</div></div></div>`}
 window.drawDailyEdges=function(){const p=(window.DATA&&DATA.daily_edges)||{};let rows=Array.isArray(p.top_edges)?p.top_edges.slice():[];const player=(document.getElementById('edgePlayer')?.value||'').trim().toLowerCase();const conf=document.getElementById('edgeConfidence')?.value||'';const type=document.getElementById('edgeType')?.value||'';const book=document.getElementById('edgeBook')?.value||'';rows=rows.filter(r=>(!player||String(r.player||'').toLowerCase().includes(player))&&(!conf||r.confidence===conf)&&(!type||r.market_type===type)&&(!book||r.sportsbook===book));const root=document.getElementById('dailyEdgeRows');if(root)root.innerHTML=rows.map(card).join('')||'<div class="edgeEmpty mono">No edges match these filters.</div>'};
 window.dailyEdges=render;
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


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    try:
        payload = json.load(DATA.open(encoding="utf-8")) if DATA.exists() else {}
    except Exception:
        payload = {}
    html = HTML.read_text(encoding="utf-8")
    data = f'<script id="v4-daily-edges-data">window.DATA=window.DATA||{{}};DATA.daily_edges={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html = replace_block(html, '<script id="v4-daily-edges-data">', '</script>', data) if 'id="v4-daily-edges-data"' in html else html.replace('</body>', data + '</body>')
    html = replace_block(html, '<style id="v4-daily-edges-style">', '</style>', CSS) if 'id="v4-daily-edges-style"' in html else html.replace('</head>', CSS + '</head>')
    html = replace_block(html, '<script id="v4-daily-edges-script">', '</script>', SCRIPT) if 'id="v4-daily-edges-script"' in html else html.replace('</body>', SCRIPT + '</body>')
    HTML.write_text(html, encoding="utf-8")
    print("Daily Edges dashboard embedded")


if __name__ == "__main__":
    main()
