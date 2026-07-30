from __future__ import annotations

import json
from pathlib import Path

DASHBOARD = Path("docs/index.html")
GAME_MODEL = Path("data/dashboard/wnba_game_market_model.json")
MASTER = Path("data/dashboard/wnba_master.json")
STYLE_MARKER = "sprint25-games-markets-style"
SCRIPT_MARKER = "sprint25-games-markets-script"

STYLE = r'''<style id="sprint25-games-markets-style">
.gamesSummary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.gamesSummaryItem{border:1px solid var(--line);background:#091321;border-radius:14px;padding:12px}.gamesSummaryValue{font-size:22px;font-weight:900;color:var(--green);margin-top:4px}.marketGrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:12px}.marketBox{border:1px solid var(--line);background:#07101d;border-radius:14px;padding:13px}.marketTitle{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#7f8da7}.marketPick{font-size:18px;font-weight:900;color:var(--green);margin-top:6px}.marketMeta{font-size:11px;color:var(--muted);margin-top:5px}.candidateList{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}.candidate{border:1px solid #1a2942;background:#091321;border-radius:12px;padding:10px}.candidateName{font-weight:900}.candidatePick{color:var(--green);font-weight:900;margin-top:3px}.periodSoon{border:1px dashed #324564;color:#90a0bb;border-radius:12px;padding:13px;margin-top:12px}.marketTable{overflow:auto}.marketTable table{min-width:1050px}.sideGood{color:var(--green);font-weight:900}.sideMuted{color:#a5b2c9}.gameSummaryLine{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}.decisionBadge{display:inline-flex;align-items:center;border-radius:999px;padding:5px 10px;font-size:11px;font-weight:900;letter-spacing:.08em}.decisionBet{background:rgba(0,227,155,.14);color:var(--green);border:1px solid rgba(0,227,155,.45)}.decisionLean{background:rgba(255,209,102,.12);color:var(--gold);border:1px solid rgba(255,209,102,.4)}.decisionPass{background:#111827;color:#9aa7bd;border:1px solid #334155}.freshness{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px}.mobileMarkets{display:none}.candidateToggle{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}.candidateToggle summary{cursor:pointer;font-weight:800;color:#c7d5ef}.bestPlay{border:1px solid rgba(0,227,155,.45);background:linear-gradient(180deg,rgba(0,227,155,.08),#08101c);border-radius:16px;padding:14px;margin-bottom:14px}.bestPlayTitle{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#7f8da7}.bestPlayPick{font-size:22px;font-weight:900;color:var(--green);margin-top:4px}.gapWarn{color:var(--gold)}@media(max-width:900px){.marketGrid,.candidateList{grid-template-columns:1fr}.gamesSummary{grid-template-columns:repeat(2,minmax(0,1fr))}.marketTable{display:none}.mobileMarkets{display:grid;gap:10px}.mobileMarketCard{border:1px solid var(--line);background:#08101c;border-radius:14px;padding:13px}.mobileMarketRow{display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-bottom:1px solid #152034}.mobileMarketRow:last-child{border-bottom:0}.gameCard{padding:12px}}
</style>'''

SCRIPT = r'''<script id="sprint25-games-markets-script">
(function(){
  const A=v=>Array.isArray(v)?v:[];
  const GAME_MODEL=__GAME_MODEL__;
  const EMBEDDED_TODAY=__TODAY_GAMES__;
  const EMBEDDED_RECENT=__RECENT_GAMES__;
  const dashboardData=()=>typeof DATA!=='undefined'&&DATA?DATA:(window.DATA||{});
  const masterData=()=>dashboardData().master||dashboardData();
  const firstValue=(obj,keys,def='-')=>{for(const k of keys){const v=obj?.[k];if(v!==undefined&&v!==null&&v!=='')return v}return def};
  const num=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
  const signed=v=>{const n=num(v);return n===null?'-':`${n>0?'+':''}${n}`};
  const gameKey=v=>String(v||'').trim().toLowerCase().replace(/\s+/g,' ');
  const allGames=()=>{const root=dashboardData(),master=masterData();const candidates=[master.games,root.games,master.schedule,root.schedule];for(const rows of candidates){if(Array.isArray(rows)&&rows.length)return rows}return [...A(EMBEDDED_TODAY),...A(EMBEDDED_RECENT)]};
  const todayGames=()=>{if(A(EMBEDDED_TODAY).length)return A(EMBEDDED_TODAY);const root=dashboardData(),master=masterData(),direct=[root.today_games,master.today_games];for(const rows of direct){if(Array.isArray(rows)&&rows.length)return rows}const target=String(master.target_date||root.target_date||'');return allGames().filter(g=>String(g?.bucket||'').toLowerCase()==='today'||(target&&String(g?.game_date||'')===target&&!String(g?.status||'').toUpperCase().includes('FINAL')))};
  const recentGames=()=>{if(A(EMBEDDED_RECENT).length)return A(EMBEDDED_RECENT);const root=dashboardData(),master=masterData(),direct=[root.yesterday_games,master.yesterday_games];for(const rows of direct){if(Array.isArray(rows)&&rows.length)return rows}return allGames().filter(g=>String(g?.bucket||'').toLowerCase()==='yesterday'||String(g?.status||'').toUpperCase().includes('FINAL'))};
  window.WNBA_GAME_SOURCE={allGames,todayGames,recentGames,embeddedToday:A(EMBEDDED_TODAY).length,embeddedRecent:A(EMBEDDED_RECENT).length};
  const modelRows=A(GAME_MODEL?.games);
  const modelMap=new Map(modelRows.map(r=>[gameKey(r.game||[r.away_team,r.home_team].filter(Boolean).join(' @ ')),r]));
  const modelFor=g=>modelMap.get(gameKey(window.game(g)))||{};
  const mergedGame=g=>Object.assign({},g,modelFor(g));
  const gamePropsFor=g=>(typeof window.propsRaw==='function'?window.propsRaw():[]).filter(p=>gameKey(p.game)===gameKey(window.game(g)));
  const candidateScore=p=>Number(p.governed_score??p.calibrated_score??p.final_score??p.confidence??0);
  const namedCandidates=(g,limit=4)=>gamePropsFor(g).filter(p=>p.player&&p.stat).sort((a,b)=>candidateScore(b)-candidateScore(a)).slice(0,limit);
  const modelSpread=g=>firstValue(mergedGame(g),['projected_margin','model_spread','projected_spread','predicted_spread','spread_projection','projection_spread']);
  const bookSpread=g=>firstValue(mergedGame(g),['market_spread','spread','current_spread','consensus_spread','closing_spread']);
  const modelTotal=g=>firstValue(mergedGame(g),['projected_total','model_total','predicted_total','total_projection','projection_total']);
  const bookTotal=g=>firstValue(mergedGame(g),['market_total','total','current_total','consensus_total','closing_total']);
  const moneyline=g=>firstValue(mergedGame(g),['moneyline','home_moneyline','moneyline_home','consensus_moneyline']);
  const spreadEdge=g=>{const row=modelFor(g),direct=num(row.spread_edge);if(direct!==null)return Number(direct.toFixed(2));const m=num(modelSpread(g)),b=num(bookSpread(g));return m===null||b===null?null:Number((m-b).toFixed(2))};
  const totalEdge=g=>{const row=modelFor(g),direct=num(row.total_edge);if(direct!==null)return Number(direct.toFixed(2));const m=num(modelTotal(g)),b=num(bookTotal(g));return m===null||b===null?null:Number((m-b).toFixed(2))};
  const spreadPickLine=g=>{const r=modelFor(g),line=num(bookSpread(g));if(line===null)return '-';if(r.spread_recommendation===r.away_team)return -line;if(r.spread_recommendation===r.home_team)return line;return line};
  const spreadLean=g=>{const r=modelFor(g);if(r.spread_recommendation)return r.spread_recommendation==='PASS'?'PASS':`${r.spread_recommendation} ${signed(spreadPickLine(g))}`;const e=spreadEdge(g);if(e===null)return 'Model pending';if(Math.abs(e)<1)return 'PASS';return e>0?'Lean home side':'Lean away side'};
  const totalLean=g=>{const r=modelFor(g);if(r.total_recommendation)return r.total_recommendation==='PASS'?'PASS':`${r.total_recommendation} ${bookTotal(g)}`;const e=totalEdge(g);if(e===null)return 'Model pending';if(Math.abs(e)<1)return 'PASS';return e>0?'OVER lean':'UNDER lean'};
  const probability=(g,field)=>{const n=num(modelFor(g)?.[field]);return n===null?null:n};
  const scoreProjection=g=>{const r=modelFor(g);const a=num(r.projected_away_score),h=num(r.projected_home_score);return a===null||h===null?'-':`${a.toFixed(1)} - ${h.toFixed(1)}`};
  const displayScore=g=>{const a=firstValue(g,['away_score'],''),h=firstValue(g,['home_score'],'');return a!==''&&h!==''?`${a}-${h}`:window.S(g.status,'Pregame')};
  const decisionFor=g=>{const r=modelFor(g),s=String(r.spread_recommendation||'').toUpperCase(),t=String(r.total_recommendation||'').toUpperCase(),edge=Math.max(Math.abs(spreadEdge(g)||0),Math.abs(totalEdge(g)||0));if((s&&s!=='PASS')||(t&&t!=='PASS'))return edge>=3?'BET':'LEAN';return 'PASS'};
  const decisionBadge=d=>`<span class="decisionBadge ${d==='BET'?'decisionBet':d==='LEAN'?'decisionLean':'decisionPass'}">${d}</span>`;
  const confidenceFor=g=>{const vals=[probability(g,'spread_probability'),probability(g,'total_probability')].filter(v=>v!==null);return vals.length?Math.max(...vals):null};
  const marketBox=(title,pick,meta='')=>`<div class="marketBox"><div class="marketTitle mono">${window.E(title)}</div><div class="marketPick mono">${window.E(pick)}</div><div class="marketMeta mono">${window.E(meta)}</div></div>`;
  const candidateCard=p=>{const side=window.S(p.signal||p.side,'WATCH'),line=window.S(p.line||p.consensus_line),proj=window.S(p.projection||p.pred),score=window.S(p.governed_score||p.calibrated_score||p.final_score||p.confidence);return `<div class="candidate"><div class="candidateName">${window.E(p.player)}</div><div class="candidatePick mono">${window.E(side)} ${window.E(p.stat)} ${window.E(line)}</div><div class="marketMeta mono">Proj ${window.E(proj)} · Score ${window.E(score)} · ${window.E(p.book||p.best_book||p.best_over_book||'Book TBD')}</div></div>`};
  const compactSummary=()=>{const root=dashboardData(),s=masterData().summary||{},active=typeof window.dashboardActiveBestBets==='function'?A(window.dashboardActiveBestBets()):A(root.cross_market?.portfolio),units=active.reduce((n,r)=>n+Number(r.recommended_units_final??r.recommended_units||0),0);return `<div class="gamesSummary"><div class="gamesSummaryItem"><div class="label mono">Games</div><div class="gamesSummaryValue mono">${A(todayGames()).length}</div></div><div class="gamesSummaryItem"><div class="label mono">Odds markets</div><div class="gamesSummaryValue mono">${window.E(window.S(s.sportsbook_markets,0))}</div></div><div class="gamesSummaryItem"><div class="label mono">Active plays</div><div class="gamesSummaryValue mono">${active.length}</div></div><div class="gamesSummaryItem"><div class="label mono">Units</div><div class="gamesSummaryValue mono">${units.toFixed(2)}</div></div></div>`};
  const bestPlay=()=>{let best=null;for(const g of todayGames()){const opts=[{pick:spreadLean(g),edge:Math.abs(spreadEdge(g)||0)},{pick:totalLean(g),edge:Math.abs(totalEdge(g)||0)}].filter(x=>x.pick&&x.pick!=='PASS'&&x.pick!=='Model pending');for(const x of opts){if(!best||x.edge>best.edge)best={...x,g}}}if(!best)return '';const c=confidenceFor(best.g);return `<div class="bestPlay"><div class="bestPlayTitle mono">Top game edge</div><div class="bestPlayPick">${window.E(best.pick)}</div><div class="small mono">${window.E(window.game(best.g))} · Edge ${window.E(best.edge.toFixed(2))}${c!==null?` · Confidence ${(c*100).toFixed(1)}%`:''}</div></div>`};

  window.gamesV25=function(){
    const today=A(todayGames()), yesterday=A(recentGames());
    const todayHtml=today.map(g=>{const c=namedCandidates(g),decision=decisionFor(g),conf=confidenceFor(g),gap=Math.abs((num(bookTotal(g))||0)-(num(modelTotal(g))||0));return `<div class="gameCard"><div class="row"><div><b class="mono">${window.E(window.game(g))}</b><div class="small mono">${window.E(window.S(g.start_time,'Time TBD'))} · ${window.E(window.S(g.status,'Pregame'))}</div></div><div>${decisionBadge(decision)} ${conf!==null?`<span class="small mono">${(conf*100).toFixed(1)}%</span>`:''}</div></div><div class="freshness"><span class="chip mono">Model ${window.E(modelFor(g).model_version||'V4')}</span><span class="chip mono">Updated ${window.E(firstValue(mergedGame(g),['updated_at','generated_at_utc','last_updated'],'Current build'))}</span>${gap>=12?'<span class="chip mono gapWarn">Large total gap</span>':''}</div><div class="gameSummaryLine"><span class="chip mono">Book spread ${window.E(bookSpread(g))}</span><span class="chip mono">Model margin ${window.E(modelSpread(g))}</span><span class="chip mono">Book total ${window.E(bookTotal(g))}</span><span class="chip mono">Model total ${window.E(modelTotal(g))}</span><span class="chip mono">Projected ${window.E(scoreProjection(g))}</span></div><div class="marketGrid">${marketBox('Spread',spreadLean(g),`Edge ${signed(spreadEdge(g))}`)}${marketBox('Total',totalLean(g),`Edge ${signed(totalEdge(g))}`)}${marketBox('Moneyline',String(moneyline(g)),'Current market')}</div><details class="candidateToggle"><summary>Player candidates (${c.length})</summary><div class="candidateList">${c.map(candidateCard).join('')||'<div class="empty mono">No named player candidates for this matchup.</div>'}</div></details></div>`}).join('')||'<div class="empty mono">No games.</div>';
    const resultHtml=yesterday.map(g=>`<div class="gameCard"><div class="row"><div><b class="mono">${window.E(window.game(g))}</b><div class="small mono">Final</div></div><div class="score mono">${window.E(displayScore(g))}</div></div></div>`).join('')||'<div class="empty mono">No completed results.</div>';
    return compactSummary()+bestPlay()+`<div class="grid2"><div class="section"><h2 class="mono">Tonight</h2><div class="small mono">Sportsbook lines, projections, edges and recommendations.</div>${todayHtml}</div><div class="section"><h2 class="mono">Recent Results</h2>${resultHtml}</div></div>`;
  };

  window.marketsV25=function(){
    const rows=A(todayGames());
    const desktop=`<div class="marketTable"><table><thead><tr><th>Game</th><th>Home book spread</th><th>Home model margin</th><th>Spread pick</th><th>Spread edge</th><th>Book total</th><th>Model total</th><th>Total pick</th><th>Total edge</th><th>Projected score</th></tr></thead><tbody>${rows.map(g=>`<tr><td><b>${window.E(window.game(g))}</b><div class="small mono">${window.E(window.S(g.start_time,'Time TBD'))}</div></td><td>${window.E(bookSpread(g))}</td><td>${window.E(modelSpread(g))}</td><td>${window.E(spreadLean(g))}</td><td class="${spreadEdge(g)!==null&&Math.abs(spreadEdge(g))>=1?'sideGood':'sideMuted'}">${window.E(signed(spreadEdge(g)))}</td><td>${window.E(bookTotal(g))}</td><td>${window.E(modelTotal(g))}</td><td>${window.E(totalLean(g))}</td><td class="${totalEdge(g)!==null&&Math.abs(totalEdge(g))>=1?'sideGood':'sideMuted'}">${window.E(signed(totalEdge(g)))}</td><td>${window.E(scoreProjection(g))}</td></tr>`).join('')||'<tr><td colspan="10" class="empty mono">No active game markets.</td></tr>'}</tbody></table></div>`;
    const mobile=`<div class="mobileMarkets">${rows.map(g=>`<div class="mobileMarketCard"><div class="row"><b>${window.E(window.game(g))}</b>${decisionBadge(decisionFor(g))}</div><div class="mobileMarketRow"><span>Book spread</span><b>${window.E(bookSpread(g))}</b></div><div class="mobileMarketRow"><span>Spread pick</span><b>${window.E(spreadLean(g))}</b></div><div class="mobileMarketRow"><span>Spread edge</span><b class="${Math.abs(spreadEdge(g)||0)>=1?'sideGood':'sideMuted'}">${window.E(signed(spreadEdge(g)))}</b></div><div class="mobileMarketRow"><span>Book total</span><b>${window.E(bookTotal(g))}</b></div><div class="mobileMarketRow"><span>Total pick</span><b>${window.E(totalLean(g))}</b></div><div class="mobileMarketRow"><span>Total edge</span><b class="${Math.abs(totalEdge(g)||0)>=1?'sideGood':'sideMuted'}">${window.E(signed(totalEdge(g)))}</b></div><div class="mobileMarketRow"><span>Projected score</span><b>${window.E(scoreProjection(g))}</b></div></div>`).join('')||'<div class="empty mono">No active game markets.</div>'}</div>`;
    return `<div class="section"><h2 class="mono">Game Markets</h2><div class="small mono">Book lines and model projections are shown from the home-team perspective.</div>${desktop}${mobile}<div class="periodSoon mono"><b>Period markets:</b> 1Q spread, 1Q total, 1H spread, 1H total and team totals remain reserved until a verified source supplies those rows.</div></div>`;
  };
})();
</script>'''


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        print(f"[warn] unable to load {path}: {exc}")
        return {}


def load_game_model() -> dict:
    return load_json(GAME_MODEL) if GAME_MODEL.exists() else {}


def load_game_rows() -> tuple[list[dict], list[dict]]:
    master = load_json(MASTER) if MASTER.exists() else {}
    games = master.get("games", []) if isinstance(master, dict) else []
    today = [g for g in games if isinstance(g, dict) and str(g.get("bucket", "")).lower() == "today"]
    recent = [g for g in games if isinstance(g, dict) and (str(g.get("bucket", "")).lower() == "yesterday" or "FINAL" in str(g.get("status", "")).upper())]
    print(f"Embedded game rows: today={len(today)} recent={len(recent)}")
    return today, recent


def replace_block(html: str, start: str, end: str, replacement: str) -> str:
    i = html.find(start)
    if i < 0:
        return html
    j = html.find(end, i)
    if j < 0:
        return html
    return html[:i] + replacement.strip() + html[j + len(end):]


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    today, recent = load_game_rows()
    script = (
        SCRIPT.replace("__GAME_MODEL__", json.dumps(load_game_model(), separators=(",", ":"), ensure_ascii=False))
        .replace("__TODAY_GAMES__", json.dumps(today, separators=(",", ":"), ensure_ascii=False))
        .replace("__RECENT_GAMES__", json.dumps(recent, separators=(",", ":"), ensure_ascii=False))
    )
    if f'id="{STYLE_MARKER}"' in html:
        html = replace_block(html, f'<style id="{STYLE_MARKER}">', "</style>", STYLE)
    else:
        html = html.replace("</head>", STYLE + "</head>", 1)
    if f'id="{SCRIPT_MARKER}"' in html:
        html = replace_block(html, f'<script id="{SCRIPT_MARKER}">', "</script>", script)
    else:
        html = html.replace("</body>", script + "</body>", 1)
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Games UX repair batch applied")


if __name__ == "__main__":
    main()
