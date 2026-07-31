from __future__ import annotations

from pathlib import Path

HTML = Path("docs/index.html")

STYLE = r'''<style id="v4-portfolio-ai-style">
.moneyGrid,.aiKpiGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.splitGrid{display:grid;grid-template-columns:1.2fr .8fr;gap:14px}.metricCard{background:#08101c;border:1px solid #1e2a43;border-radius:16px;padding:15px}.metricLabel{color:#7e8ba3;font-size:11px;text-transform:uppercase;letter-spacing:.12em}.metricValue{font-size:25px;font-weight:900;margin-top:6px}.positive{color:#00e39b}.negative{color:#ff4d67}.neutral{color:#ffd166}.insightCard{border:1px solid #253552;background:#08101c;border-radius:14px;padding:14px;margin:9px 0}.insightTitle{font-weight:900;margin-bottom:5px}.dataWarning{border-left:3px solid #ffd166;padding:10px 12px;background:#171409;border-radius:8px;color:#e8dba7}.miniTable{overflow:auto}.miniTable table{min-width:650px}.emptyState{padding:24px;text-align:center;color:#7e8ba3;border:1px dashed #263854;border-radius:14px}.statusPill{display:inline-flex;border:1px solid #364b70;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:900}.recommendationList{display:grid;gap:9px}.recommendation{padding:12px;border-radius:12px;background:#0a1322;border:1px solid #263854}.barTrack{height:8px;background:#111b2c;border-radius:999px;overflow:hidden;margin-top:7px}.barFill{height:100%;background:#00e39b;border-radius:999px}@media(max-width:900px){.moneyGrid,.aiKpiGrid,.splitGrid{grid-template-columns:1fr 1fr}}@media(max-width:620px){.moneyGrid,.aiKpiGrid,.splitGrid{grid-template-columns:1fr}}
</style>'''

SCRIPT = r'''<script id="v4-portfolio-ai-script">(function(){
const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');
const arr=v=>Array.isArray(v)?v:[];
const obj=v=>v&&typeof v==='object'&&!Array.isArray(v)?v:{};
const number=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
const first=(source,keys)=>{for(const k of keys){const parts=k.split('.');let cur=source;for(const p of parts){if(cur==null){cur=undefined;break}cur=cur[p]}if(cur!==undefined&&cur!==null&&cur!=='')return cur}return null};
const fmt=(v,digits=1)=>{const n=number(v);return n==null?'—':n.toFixed(digits)};
const money=v=>{const n=number(v);return n==null?'—':`${n<0?'−':''}$${Math.abs(n).toFixed(2)}`};
const pct=v=>{const n=number(v);return n==null?'—':`${n.toFixed(1)}%`};
const units=v=>{const n=number(v);return n==null?'—':`${n>=0?'+':''}${n.toFixed(2)}u`};
const cls=v=>{const n=number(v);return n==null?'neutral':n>0?'positive':n<0?'negative':'neutral'};
function card(label,value,note='',tone=''){return `<div class="metricCard"><div class="metricLabel mono">${esc(label)}</div><div class="metricValue mono ${tone}">${esc(value)}</div>${note?`<div class="small mono">${esc(note)}</div>`:''}</div>`}
function rowsFrom(value){if(Array.isArray(value))return value;if(value&&typeof value==='object'){for(const k of ['rows','bets','items','records','recommendations','plays','history','markets','books'])if(Array.isArray(value[k]))return value[k]}return []}
function empty(message){return `<div class="emptyState mono">${esc(message)}</div>`}
function table(headers,rows){if(!rows.length)return empty('No verified records are available for this section yet.');return `<div class="miniTable"><table><thead><tr>${headers.map(h=>`<th>${esc(h.label)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${headers.map(h=>`<td>${esc(h.render?r[h.render](r):first(r,h.keys)||'—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
function activeRecommendations(){const candidates=[DATA?.cross_market?.portfolio,DATA?.cross_market?.top_plays,DATA?.unified?.portfolio,DATA?.master?.best_bets,DATA?.best_bets];for(const c of candidates){const rows=rowsFrom(c);if(rows.length)return rows.filter(r=>{const action=String(first(r,['decision','action','signal','status'])||'').toUpperCase();return !action||['BET','LEAN','ACTIVE','OPEN','PENDING'].includes(action)})}return []}
window.portfolio=function(){
 const p=obj(DATA?.portfolio),risk=obj(DATA?.risk),results=obj(DATA?.results||DATA?.grading),summary=obj(first(p,['summary','metrics','kpis'])||p);
 const starting=first(summary,['starting_bankroll','bankroll_start','initial_bankroll']);
 const current=first(summary,['current_bankroll','bankroll','ending_bankroll']);
 const profit=first(summary,['profit_loss','p_l','pl','total_profit','net_profit'])??first(results,['summary.profit_loss','summary.pl','profit_loss']);
 const roi=first(summary,['roi','roi_pct','return_on_investment'])??first(results,['summary.roi','roi']);
 const unitTotal=first(summary,['units','units_won','net_units'])??first(results,['summary.units','units']);
 const active=activeRecommendations();
 const bookRows=rowsFrom(first(p,['sportsbooks','book_breakdown','by_book']));
 const marketRows=rowsFrom(first(p,['markets','market_breakdown','by_market']))||rowsFrom(first(results,['by_stat','performance_by_stat']));
 const recent=rowsFrom(first(p,['recent_bets','bets','history'])).slice(0,12);
 const exposure=first(risk,['total_exposure','exposure_units','summary.total_exposure']);
 const drawdown=first(risk,['max_drawdown','drawdown','summary.max_drawdown']);
 const largestWin=first(p,['largest_win','risk_metrics.largest_win']);
 const largestLoss=first(p,['largest_loss','risk_metrics.largest_loss']);
 const missing=starting==null&&current==null&&profit==null&&roi==null;
 return `<div class="section"><div class="row"><div><h2 class="mono">Portfolio</h2><div class="small mono">Bankroll, profit, exposure and betting risk.</div></div><span class="statusPill mono ${missing?'neutral':'positive'}">${missing?'DATA COLLECTION':'TRACKING ACTIVE'}</span></div>${missing?'<div class="dataWarning mono">Bankroll values have not been configured. The tab will display verified recommendations and graded results without inventing financial totals.</div>':''}<div class="moneyGrid" style="margin-top:14px">${card('Current Bankroll',money(current),'Verified balance',cls(current))}${card('Starting Bankroll',money(starting),'Configured baseline')}${card('Profit / Loss',money(profit),'Settled wagers',cls(profit))}${card('ROI',pct(roi),'Return on stake',cls(roi))}${card('Net Units',units(unitTotal),'Graded betting units',cls(unitTotal))}${card('Active Bets',String(active.length),'Open recommendations')}${card('Exposure',units(exposure),'Current risk allocation',cls(exposure==null?null:-Math.abs(number(exposure)||0)))}${card('Max Drawdown',pct(drawdown),'Peak-to-trough decline',cls(drawdown==null?null:-Math.abs(number(drawdown)||0)))}</div></div>
 <div class="splitGrid"><div class="section"><h2 class="mono">Recent Bets</h2>${table([{label:'Player / Game',keys:['player','game','matchup']},{label:'Market',keys:['market','stat','bet']},{label:'Side',keys:['side','signal','pick']},{label:'Odds',keys:['odds','price','american_odds']},{label:'Result',keys:['result','status','grade']},{label:'P/L',keys:['profit_loss','pl','units']}],recent)}</div><div class="section"><h2 class="mono">Risk Snapshot</h2>${card('Largest Win',money(largestWin),'Single settled result',cls(largestWin))}${card('Largest Loss',money(largestLoss),'Single settled result',cls(largestLoss))}<div class="insightCard"><div class="insightTitle mono">Allocation rule</div><div class="small mono">Only verified active recommendations are counted. Missing sportsbook balances or stakes remain unreported rather than estimated.</div></div></div></div>
 <div class="splitGrid"><div class="section"><h2 class="mono">Sportsbook Breakdown</h2>${table([{label:'Sportsbook',keys:['book','sportsbook','name']},{label:'Bets',keys:['bets','count','n']},{label:'Win %',keys:['win_rate','hit_rate','win_pct']},{label:'ROI',keys:['roi','roi_pct']},{label:'P/L',keys:['profit_loss','pl','units']}],bookRows)}</div><div class="section"><h2 class="mono">Market Profitability</h2>${table([{label:'Market',keys:['market','stat','name']},{label:'Bets',keys:['bets','count','n']},{label:'Win %',keys:['win_rate','hit_rate','win_pct']},{label:'ROI',keys:['roi','roi_pct']},{label:'P/L',keys:['profit_loss','pl','units']}],marketRows)}</div></div>`;
};
function textItems(value){if(Array.isArray(value))return value.map(x=>typeof x==='string'?x:first(x,['text','message','note','recommendation','summary'])).filter(Boolean);if(typeof value==='string')return [value];return rowsFrom(value).map(x=>first(x,['text','message','note','recommendation','summary'])).filter(Boolean)}
window.ai=function(){
 const ai=obj(DATA?.ai||DATA?.ai_coach),perf=obj(DATA?.performance||DATA?.projection_performance),results=obj(DATA?.results||DATA?.grading),learning=obj(DATA?.learning);
 const health=String(first(ai,['health.status','model_health','status','summary.status'])||first(perf,['overall_grade','summary.grade'])||'MONITOR').toUpperCase();
 const summary=first(ai,['daily_summary','summary.text','summary','analysis'])||'The AI Center is waiting for a verified generated summary.';
 const recs=textItems(first(ai,['recommendations','actions','coach_recommendations']));
 const notes=textItems(first(ai,['learning_notes','notes'])||first(learning,['notes','insights','recommendations']));
 const edges=rowsFrom(first(ai,['daily_edges','edges','top_plays'])||DATA?.cross_market?.top_plays).slice(0,8);
 const roi=first(perf,['market_roi','summary.roi','roi'])??first(results,['summary.roi','roi']);
 const hit=first(perf,['hit_rate','summary.hit_rate'])??first(results,['summary.win_rate','win_rate']);
 const mae=first(perf,['mae','summary.mae']);
 const bias=first(perf,['bias','summary.bias']);
 const healthTone=/HEALTH|READY|PASS|A|B/.test(health)?'positive':/RETRAIN|FAIL|F/.test(health)?'negative':'neutral';
 return `<div class="section"><div class="row"><div><h2 class="mono">AI Center</h2><div class="small mono">Model health, learning signals and recommended actions.</div></div><span class="statusPill mono ${healthTone}">${esc(health)}</span></div><div class="aiKpiGrid" style="margin-top:14px">${card('Market ROI',pct(roi),'Graded decisions',cls(roi))}${card('Hit Rate',pct(hit),'Pushes excluded',cls((number(hit)||0)-50))}${card('MAE',fmt(mae,2),'Average prediction error')}${card('Bias',fmt(bias,3),'Near zero is preferred',cls(bias==null?null:-Math.abs(number(bias)||0)))}</div></div>
 <div class="splitGrid"><div class="section"><h2 class="mono">Daily AI Summary</h2><div class="insightCard"><div class="insightTitle mono">Current read</div><div>${esc(typeof summary==='string'?summary:JSON.stringify(summary))}</div></div><div class="dataWarning mono">AI guidance is descriptive. Recommendations should only use verified data and do not guarantee profitable outcomes.</div></div><div class="section"><h2 class="mono">Model Health</h2><div class="metricValue mono ${healthTone}">${esc(health)}</div><div class="small mono">Status is derived from available AI, performance and grading outputs.</div>${bias!=null?`<div class="insightCard"><div class="insightTitle mono">Projection bias</div><div>${esc(fmt(bias,3))}</div><div class="barTrack"><div class="barFill" style="width:${Math.min(100,Math.abs(number(bias)||0)*20)}%"></div></div></div>`:''}</div></div>
 <div class="splitGrid"><div class="section"><h2 class="mono">Recommended Actions</h2><div class="recommendationList">${recs.length?recs.slice(0,10).map(x=>`<div class="recommendation">${esc(x)}</div>`).join(''):empty('No generated model actions are available yet.')}</div></div><div class="section"><h2 class="mono">Automated Learning Notes</h2><div class="recommendationList">${notes.length?notes.slice(0,10).map(x=>`<div class="recommendation">${esc(x)}</div>`).join(''):empty('No verified learning notes are available yet.')}</div></div></div>
 <div class="section"><h2 class="mono">Daily Edge Report</h2>${table([{label:'Player / Game',keys:['player','game','matchup']},{label:'Market',keys:['market','stat']},{label:'Pick',keys:['pick','signal','side']},{label:'Line',keys:['line','consensus_line']},{label:'Confidence',keys:['confidence','final_score','score']},{label:'Decision',keys:['decision','action','status']}],edges)}</div>`;
};
window.WNBA_PORTFOLIO_AI_RENDERERS={version:'1.0',portfolio:typeof window.portfolio==='function',ai:typeof window.ai==='function'};
})();</script>'''


def replace_or_insert(html: str, marker: str, block: str, closing: str) -> str:
    start = html.find(marker)
    if start >= 0:
        end = html.find(closing, start)
        if end >= 0:
            return html[:start] + block + html[end + len(closing):]
    return html.replace("</head>", block + "</head>") if closing == "</style>" else html.replace("</body>", block + "</body>")


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    html = HTML.read_text(encoding="utf-8")
    html = replace_or_insert(html, '<style id="v4-portfolio-ai-style">', STYLE, "</style>")
    html = replace_or_insert(html, '<script id="v4-portfolio-ai-script">', SCRIPT, "</script>")
    HTML.write_text(html, encoding="utf-8")
    print("Restored Portfolio and AI Center renderers")


if __name__ == "__main__":
    main()
