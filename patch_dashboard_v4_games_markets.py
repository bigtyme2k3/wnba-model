from __future__ import annotations

import json
from pathlib import Path


DASHBOARD = Path("docs/index.html")
GAME_MODEL = Path("data/dashboard/wnba_game_market_model.json")
STYLE_MARKER = "sprint25-games-markets-style"
SCRIPT_MARKER = "sprint25-games-markets-script"

STYLE = r'''<style id="sprint25-games-markets-style">
.marketGrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:12px}.marketBox{border:1px solid var(--line);background:#07101d;border-radius:14px;padding:13px}.marketTitle{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#7f8da7}.marketPick{font-size:18px;font-weight:900;color:var(--green);margin-top:6px}.marketMeta{font-size:11px;color:var(--muted);margin-top:5px}.candidateList{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}.candidate{border:1px solid #1a2942;background:#091321;border-radius:12px;padding:10px}.candidateName{font-weight:900}.candidatePick{color:var(--green);font-weight:900;margin-top:3px}.periodSoon{border:1px dashed #324564;color:#90a0bb;border-radius:12px;padding:13px;margin-top:12px}.marketTable{overflow:auto}.marketTable table{min-width:1050px}.sideGood{color:var(--green);font-weight:900}.sideMuted{color:#a5b2c9}.gameSummaryLine{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}@media(max-width:900px){.marketGrid,.candidateList{grid-template-columns:1fr}}
</style>'''

SCRIPT = r'''<script id="sprint25-games-markets-script">
(function(){
  const A=v=>Array.isArray(v)?v:[];
  const GAME_MODEL=__GAME_MODEL__;
  const firstValue=(obj,keys,def='-')=>{for(const k of keys){const v=obj?.[k];if(v!==undefined&&v!==null&&v!=='')return v}return def};
  const num=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
  const signed=v=>{const n=num(v);return n===null?'-':`${n>0?'+':''}${n}`};
  const gameKey=v=>String(v||'').trim().toLowerCase().replace(/\s+/g,' ');
  const allGames=()=>{const candidates=[window.DATA?.master?.games,window.DATA?.games,window.DATA?.master?.schedule,window.DATA?.schedule];for(const rows of candidates){if(Array.isArray(rows)&&rows.length)return rows}return []};
  const todayGames=()=>{const direct=[window.DATA?.today_games,window.DATA?.master?.today_games];for(const rows of direct){if(Array.isArray(rows)&&rows.length)return rows}const target=String(window.DATA?.master?.target_date||window.DATA?.target_date||'');return allGames().filter(g=>String(g?.bucket||'').toLowerCase()==='today'||(target&&String(g?.game_date||'')===target&& !String(g?.status||'').toUpperCase().includes('FINAL')))};
  const recentGames=()=>{const direct=[window.DATA?.yesterday_games,window.DATA?.master?.yesterday_games];for(const rows of direct){if(Array.isArray(rows)&&rows.length)return rows}return allGames().filter(g=>String(g?.bucket||'').toLowerCase()==='yesterday'||String(g?.status||'').toUpperCase().includes('FINAL'))};
  window.WNBA_GAME_SOURCE={allGames,todayGames,recentGames};
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
  const probability=(g,field)=>{const n=num(modelFor(g)?.[field]);return n===null?'-':`${(n*100).toFixed(1)}%`};
  const scoreProjection=g=>{const r=modelFor(g);const a=num(r.projected_away_score),h=num(r.projected_home_score);return a===null||h===null?'-':`${a.toFixed(1)} - ${h.toFixed(1)}`};
  const displayScore=g=>{const a=firstValue(g,['away_score'],''),h=firstValue(g,['home_score'],'');return a!==''&&h!==''?`${a}-${h}`:window.S(g.status,'Pregame')};
  const marketBox=(title,pick,meta='')=>`<div class="marketBox"><div class="marketTitle mono">${window.E(title)}</div><div class="marketPick mono">${window.E(pick)}</div><div class="marketMeta mono">${window.E(meta)}</div></div>`;
  const candidateCard=p=>{const side=window.S(p.signal||p.side,'WATCH'),line=window.S(p.line||p.consensus_line),proj=window.S(p.projection||p.pred),score=window.S(p.governed_score||p.calibrated_score||p.final_score||p.confidence);return `<div class="candidate"><div class="candidateName">${window.E(p.player)}</div><div class="candidatePick mono">${window.E(side)} ${window.E(p.stat)} ${window.E(line)}</div><div class="marketMeta mono">Proj ${window.E(proj)} · Score ${window.E(score)} · ${window.E(p.book||p.best_book||p.best_over_book||'Book TBD')}</div></div>`};

  window.gamesV25=function(){
    const today=A(todayGames()), yesterday=A(recentGames());
    const todayHtml=today.map(g=>{const c=namedCandidates(g);return `<div class="gameCard"><div class="row"><div><b class="mono">${window.E(window.game(g))}</b><div class="small mono">${window.E(window.S(g.start_time,'Time TBD'))} · ${window.E(window.S(g.status,'Pregame'))}</div></div><div class="score mono">${window.E(displayScore(g))}</div></div><div class="gameSummaryLine"><span class="chip mono">Home book spread ${window.E(bookSpread(g))}</span><span class="chip mono">Home model margin ${window.E(modelSpread(g))}</span><span class="chip mono">Book total ${window.E(bookTotal(g))}</span><span class="chip mono">Model total ${window.E(modelTotal(g))}</span><span class="chip mono">Projected score ${window.E(scoreProjection(g))}</span></div><div class="marketGrid">${marketBox('Spread prediction',spreadLean(g),`Edge ${signed(spreadEdge(g))} · Win ${probability(g,'spread_probability')}`)}${marketBox('Total prediction',totalLean(g),`Edge ${signed(totalEdge(g))} · Win ${probability(g,'total_probability')}`)}${marketBox('Moneyline',String(moneyline(g)),'Current market price')}</div><div class="candidateList">${c.map(candidateCard).join('')||'<div class="empty mono">No named player candidates for this matchup.</div>'}</div></div>`}).join('')||'<div class="empty mono">No games.</div>';
    const resultHtml=yesterday.map(g=>`<div class="gameCard"><div class="row"><div><b class="mono">${window.E(window.game(g))}</b><div class="small mono">Final</div></div><div class="score mono">${window.E(displayScore(g))}</div></div></div>`).join('')||'<div class="empty mono">No completed results.</div>';
    const top=typeof window.kpis==='function'?window.kpis():'';
    return top+`<div class="grid2"><div class="section"><h2 class="mono">Tonight</h2><div class="small mono">Matchup hub with sportsbook lines, model projections and named player candidates.</div>${todayHtml}</div><div class="section"><h2 class="mono">Recent Results</h2>${resultHtml}</div></div>`;
  };

  window.marketsV25=function(){
    const rows=A(todayGames());
    return `<div class="section"><h2 class="mono">Game Markets</h2><div class="small mono">The book spread and model margin are shown from the home-team perspective. Pick lines are converted to the selected team.</div><div class="marketTable"><table><thead><tr><th>Game</th><th>Home book spread</th><th>Home model margin</th><th>Spread pick</th><th>Spread edge</th><th>Book total</th><th>Model total</th><th>Total pick</th><th>Total edge</th><th>Projected score</th></tr></thead><tbody>${rows.map(g=>`<tr><td><b>${window.E(window.game(g))}</b><div class="small mono">${window.E(window.S(g.start_time,'Time TBD'))}</div></td><td>${window.E(bookSpread(g))}</td><td>${window.E(modelSpread(g))}</td><td>${window.E(spreadLean(g))}</td><td class="${spreadEdge(g)!==null&&Math.abs(spreadEdge(g))>=1?'sideGood':'sideMuted'}">${window.E(signed(spreadEdge(g)))}</td><td>${window.E(bookTotal(g))}</td><td>${window.E(modelTotal(g))}</td><td>${window.E(totalLean(g))}</td><td class="${totalEdge(g)!==null&&Math.abs(totalEdge(g))>=1?'sideGood':'sideMuted'}">${window.E(signed(totalEdge(g)))}</td><td>${window.E(scoreProjection(g))}</td></tr>`).join('')||'<tr><td colspan="10" class="empty mono">No active game markets.</td></tr>'}</tbody></table></div><div class="periodSoon mono"><b>Period markets:</b> 1Q spread, 1Q total, 1H spread, 1H total and team totals are structurally reserved here. They remain unavailable until a verified source supplies those rows.</div></div>`;
  };
})();
</script>'''


def load_game_model() -> dict:
    try:
        if GAME_MODEL.exists():
            payload = json.loads(GAME_MODEL.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        print(f"[warn] unable to load game model: {exc}")
    return {}


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
    script = SCRIPT.replace("__GAME_MODEL__", json.dumps(load_game_model(), separators=(",", ":"), ensure_ascii=False))
    if f'id="{STYLE_MARKER}"' in html:
        html = replace_block(html, f'<style id="{STYLE_MARKER}">', "</style>", STYLE)
    else:
        html = html.replace("</head>", STYLE + "</head>", 1)
    if f'id="{SCRIPT_MARKER}"' in html:
        html = replace_block(html, f'<script id="{SCRIPT_MARKER}">', "</script>", script)
    else:
        html = html.replace("</body>", script + "</body>", 1)
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Authoritative Games and Game Props renderers replaced with normalized game sources")


if __name__ == "__main__":
    main()
