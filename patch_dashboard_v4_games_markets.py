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
  const GAME_MODEL=__GAME_MODEL__;
  const firstValue=(obj,keys,def='-')=>{for(const k of keys){const v=obj?.[k];if(v!==undefined&&v!==null&&v!=='')return v}return def};
  const num=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
  const signed=v=>{const n=num(v);return n===null?'-':`${n>0?'+':''}${n}`};
  const gameKey=v=>String(v||'').trim().toLowerCase().replace(/\s+/g,' ');
  const modelRows=A(GAME_MODEL?.games);
  const modelMap=new Map(modelRows.map(r=>[gameKey(r.game||[r.away_team,r.home_team].filter(Boolean).join(' @ ')),r]));
  const modelFor=g=>modelMap.get(gameKey(game(g)))||{};
  const mergedGame=g=>Object.assign({},g,modelFor(g));
  const gamePropsFor=g=>propsRaw().filter(p=>gameKey(p.game)===gameKey(game(g)));
  const candidateScore=p=>Number(p.governed_score??p.calibrated_score??p.final_score??p.confidence??0);
  const namedCandidates=(g,limit=4)=>gamePropsFor(g).filter(p=>p.player&&p.stat).sort((a,b)=>candidateScore(b)-candidateScore(a)).slice(0,limit);
  const modelSpread=g=>firstValue(mergedGame(g),['projected_margin','model_spread','projected_spread','predicted_spread','spread_projection','projection_spread']);
  const bookSpread=g=>firstValue(mergedGame(g),['market_spread','spread','current_spread','consensus_spread','closing_spread']);
  const modelTotal=g=>firstValue(mergedGame(g),['projected_total','model_total','predicted_total','total_projection','projection_total']);
  const bookTotal=g=>firstValue(mergedGame(g),['market_total','total','current_total','consensus_total','closing_total']);
  const moneyline=g=>firstValue(mergedGame(g),['moneyline','home_moneyline','consensus_moneyline']);
  const spreadEdge=g=>{const row=modelFor(g),direct=num(row.spread_edge);if(direct!==null)return Number(direct.toFixed(2));const m=num(modelSpread(g)),b=num(bookSpread(g));return m===null||b===null?null:Number((m-b).toFixed(2))};
  const totalEdge=g=>{const row=modelFor(g),direct=num(row.total_edge);if(direct!==null)return Number(direct.toFixed(2));const m=num(modelTotal(g)),b=num(bookTotal(g));return m===null||b===null?null:Number((m-b).toFixed(2))};
  const spreadLean=g=>{const r=modelFor(g);if(r.spread_recommendation)return r.spread_recommendation==='PASS'?'PASS':`${r.spread_recommendation} ${signed(bookSpread(g))}`;const e=spreadEdge(g);if(e===null)return 'Model pending';if(Math.abs(e)<1)return 'PASS';return e>0?'Lean home side':'Lean away side'};
  const totalLean=g=>{const r=modelFor(g);if(r.total_recommendation)return r.total_recommendation==='PASS'?'PASS':`${r.total_recommendation} ${bookTotal(g)}`;const e=totalEdge(g);if(e===null)return 'Model pending';if(Math.abs(e)<1)return 'PASS';return e>0?'OVER lean':'UNDER lean'};
  const probability=(g,field)=>{const n=num(modelFor(g)?.[field]);return n===null?'-':`${(n*100).toFixed(1)}%`};
  const scoreProjection=g=>{const r=modelFor(g);const a=num(r.projected_away_score),h=num(r.projected_home_score);return a===null||h===null?'-':`${a.toFixed(1)} - ${h.toFixed(1)}`};
  const marketBox=(title,pick,meta='')=>`<div class="marketBox"><div class="marketTitle mono">${E(title)}</div><div class="marketPick mono">${E(pick)}</div><div class="marketMeta mono">${E(meta)}</div></div>`;
  const candidateCard=p=>{const side=S(p.signal||p.side,'WATCH'),line=S(p.line||p.consensus_line),proj=S(p.projection||p.pred),score=S(p.governed_score||p.calibrated_score||p.final_score||p.confidence);return `<div class="candidate"><div class="candidateName">${E(p.player)}</div><div class="candidatePick mono">${E(side)} ${E(p.stat)} ${E(line)}</div><div class="marketMeta mono">Proj ${E(proj)} · Score ${E(score)} · ${E(p.book||p.best_book||p.best_over_book||'Book TBD')}</div></div>`};

  window.gamesV25=function(){
    const today=A(DATA.today_games), yesterday=A(DATA.yesterday_games);
    const todayHtml=today.map(g=>{const c=namedCandidates(g);return `<div class="gameCard"><div class="row"><div><b class="mono">${E(game(g))}</b><div class="small mono">${E(S(g.start_time,'Time TBD'))} · ${E(S(g.status,'Pregame'))}</div></div><div class="score mono">${E(score(g))}</div></div><div class="gameSummaryLine"><span class="chip mono">Book spread ${E(bookSpread(g))}</span><span class="chip mono">Model margin ${E(modelSpread(g))}</span><span class="chip mono">Book total ${E(bookTotal(g))}</span><span class="chip mono">Model total ${E(modelTotal(g))}</span><span class="chip mono">Projected score ${E(scoreProjection(g))}</span></div><div class="marketGrid">${marketBox('Spread prediction',spreadLean(g),`Edge ${signed(spreadEdge(g))} · Win ${probability(g,'spread_probability')}`)}${marketBox('Total prediction',totalLean(g),`Edge ${signed(totalEdge(g))} · Win ${probability(g,'total_probability')}`)}${marketBox('Moneyline',String(moneyline(g)),'Current market price')}</div><div class="candidateList">${c.map(candidateCard).join('')||'<div class="empty mono">No named player candidates for this matchup.</div>'}</div></div>`}).join('')||'<div class="empty mono">No games.</div>';
    const resultHtml=yesterday.map(g=>`<div class="gameCard"><div class="row"><div><b class="mono">${E(game(g))}</b><div class="small mono">Final</div></div><div class="score mono">${E(score(g))}</div></div></div>`).join('')||'<div class="empty mono">No completed results.</div>';
    return kpis()+`<div class="grid2"><div class="section"><h2 class="mono">Tonight</h2><div class="small mono">Matchup hub with sportsbook lines, model projections and named player candidates.</div>${todayHtml}</div><div class="section"><h2 class="mono">Recent Results</h2>${resultHtml}</div></div>`;
  };

  window.marketsV25=function(){
    const rows=A(DATA.today_games);
    return `<div class="section"><h2 class="mono">Game Markets</h2><div class="small mono">Game-level markets only: spreads, totals and moneylines. Model fields come from the verified game-market engine.</div><div class="marketTable"><table><thead><tr><th>Game</th><th>Book spread</th><th>Model margin</th><th>Spread pick</th><th>Spread edge</th><th>Book total</th><th>Model total</th><th>Total pick</th><th>Total edge</th><th>Projected score</th></tr></thead><tbody>${rows.map(g=>`<tr><td><b>${E(game(g))}</b><div class="small mono">${E(S(g.start_time,'Time TBD'))}</div></td><td>${E(bookSpread(g))}</td><td>${E(modelSpread(g))}</td><td>${E(spreadLean(g))}</td><td class="${spreadEdge(g)!==null&&Math.abs(spreadEdge(g))>=1?'sideGood':'sideMuted'}">${E(signed(spreadEdge(g)))}</td><td>${E(bookTotal(g))}</td><td>${E(modelTotal(g))}</td><td>${E(totalLean(g))}</td><td class="${totalEdge(g)!==null&&Math.abs(totalEdge(g))>=1?'sideGood':'sideMuted'}">${E(signed(totalEdge(g)))}</td><td>${E(scoreProjection(g))}</td></tr>`).join('')||'<tr><td colspan="10" class="empty mono">No active game markets.</td></tr>'}</tbody></table></div><div class="periodSoon mono"><b>Period markets:</b> 1Q spread, 1Q total, 1H spread, 1H total and team totals are structurally reserved here. They remain unavailable until a verified source supplies those rows.</div></div>`;
  };

  try{games=window.gamesV25}catch(e){}
  if(Array.isArray(tabs)){
    const existing=tabs.findIndex(x=>x[0]==='markets'||x[0]==='gameprops');
    if(existing>=0)tabs[existing]=['markets','Game Props'];
    else tabs.splice(1,0,['markets','Game Props']);
  }
  render=function(t='games'){
    q('tabs').innerHTML=tabs.map(x=>`<button class="tab ${x[0]===t?'a':''}" onclick="render('${x[0]}')">${x[1]}</button>`).join('');
    q('sub').textContent=`Slate ${S(DATA.master?.target_date,'-')} · Updated ${fmt(DATA.generated_at_utc)}`;
    q('badge').textContent=`V4 · ${S(summary().sportsbook_markets,0)} odds markets`;
    const views={games:window.gamesV25,markets:window.marketsV25,props,books,best,portfolio,ai,results,health};
    q('root').innerHTML=(views[t]||window.gamesV25)();
    if(t==='props')drawProps();
    scrollTo(0,0);
  };
  render('games');
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


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    if STYLE_MARKER not in html:
        html = html.replace("</head>", STYLE + "</head>", 1)
    if SCRIPT_MARKER not in html:
        script = SCRIPT.replace("__GAME_MODEL__", json.dumps(load_game_model(), separators=(",", ":"), ensure_ascii=False))
        html = html.replace("</body>", script + "</body>", 1)
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Sprint 25 Games and Markets dashboard patch applied with game-model projections")


if __name__ == "__main__":
    main()
