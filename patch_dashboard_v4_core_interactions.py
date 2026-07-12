from __future__ import annotations

from pathlib import Path

PATH = Path("docs/index.html")

CSS = r"""
<style id="v4-core-interactions-style">
.gameCard.selectable{cursor:pointer;transition:transform .12s ease,border-color .12s ease}.gameCard.selectable:hover,.gameCard.selectable:focus{border-color:#80a8ff;transform:translateY(-1px);outline:none}.gameAction{margin-top:10px;display:inline-flex;border:1px solid #304365;border-radius:999px;padding:6px 10px;color:#b8c8e8;font-size:12px;font-weight:800}.clickHint{color:#80a8ff;font-size:11px;margin-top:5px}.previewPanel{margin-top:16px;border:1px solid #304365;background:linear-gradient(180deg,#111d31,#09111e);border-radius:20px;padding:18px}.previewHead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.previewTitle{font-size:22px;font-weight:900}.previewGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px}.previewStat{background:#07101d;border:1px solid #1e2a43;border-radius:15px;padding:14px}.previewValue{font-size:24px;font-weight:900;margin-top:5px}.previewPickGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px}.previewPick{background:#08101c;border:1px solid #1e2a43;border-radius:15px;padding:14px}.previewPickRank{color:#80a8ff;font-size:11px;letter-spacing:.12em;text-transform:uppercase}.previewPickTitle{font-size:16px;font-weight:900;margin-top:5px}.previewActions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.previewBtn{border:1px solid #304365;background:#101a2d;color:#eef4ff;border-radius:999px;padding:9px 12px;font-weight:800}.resultsGrid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:14px 0}.resultKpi{background:#08101c;border:1px solid #1e2a43;border-radius:15px;padding:14px}.resultKpi .value{font-size:25px;font-weight:900;margin-top:5px}.resultStatus{display:inline-flex;border:1px solid #304365;border-radius:999px;padding:6px 10px;margin-top:8px}.resultRows{display:grid;grid-template-columns:1fr 1fr;gap:12px}.resultScore{font-size:22px;font-weight:900}@media(max-width:900px){.previewGrid,.previewPickGrid,.resultsGrid,.resultRows{grid-template-columns:1fr 1fr}.previewPickGrid .previewPick:last-child,.resultsGrid .resultKpi:last-child{grid-column:1/-1}}
</style>
"""

SCRIPT = r"""
<script id="v4-core-interactions-script">
(function(){
  const arr=v=>Array.isArray(v)?v:[];
  const val=(v,d='-')=>v===undefined||v===null||v===''?d:v;
  const esc=v=>typeof E==='function'?E(v):String(v??'');
  const gameName=g=>typeof game==='function'?game(g):val(g?.game,[g?.away_team,g?.home_team].filter(Boolean).join(' @ '));
  const scoreText=g=>typeof score==='function'?score(g):((g?.away_score??'')!==''||(g?.home_score??'')!==''?`${val(g.away_score,'')}-${val(g.home_score,'')}`:'');
  const js=s=>String(s??'').replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/\r?\n/g,' ');
  let previewGame='';

  function teams(name){return String(name||'').split(' @ ').map(x=>x.trim()).filter(Boolean)}
  function sameGame(a,b){if(!a||!b)return false;if(a===b)return true;const x=teams(a),y=teams(b);return x.length===2&&y.length===2&&x.every(t=>y.includes(t))}
  function rowsFrom(obj){if(Array.isArray(obj))return obj;if(!obj||typeof obj!=='object')return[];for(const k of ['rows','games','predictions','projections','markets','top_decisions','best_bets','qualified_bets','items'])if(Array.isArray(obj[k]))return obj[k];return[]}
  function matchingRows(name){
    const pools=[DATA.market,DATA.projection,DATA.monte,DATA.master?.best_bets,DATA.master?.props];
    return pools.flatMap(rowsFrom).filter(r=>sameGame(r.game||r.matchup||r.event,name));
  }
  function firstValue(rows,keys,d='-'){for(const r of rows)for(const k of keys)if(r&&r[k]!==undefined&&r[k]!==null&&r[k]!=='')return r[k];return d}
  function pct(v){if(v===undefined||v===null||v==='')return'-';const n=Number(v);if(Number.isNaN(n))return String(v);return n<=1?`${(n*100).toFixed(1)}%`:`${n.toFixed(1)}%`}
  function topPicks(name){
    const candidates=arr(DATA.master?.best_bets).concat(arr(DATA.master?.props)).filter(r=>sameGame(r.game,name));
    const score=r=>Number(r.final_score??r.confidence??r.edge_pct??r.ev_pct??0);
    const seen=new Set();
    return candidates.sort((a,b)=>score(b)-score(a)).filter(r=>{const k=[r.player,r.stat,r.signal||r.side,r.line].join('|');if(seen.has(k))return false;seen.add(k);return true}).slice(0,3);
  }
  function predictionCard(g){
    const name=gameName(g), rows=matchingRows(name), picks=topPicks(name);
    const marketSpread=val(g.spread??g.spread_home,firstValue(rows,['spread','market_spread','consensus_spread']));
    const marketTotal=val(g.total,firstValue(rows,['total','market_total','consensus_total']));
    const projectedMargin=firstValue(rows,['projected_margin','predicted_margin','margin_prediction','model_spread','spread_projection']);
    const projectedTotal=firstValue(rows,['projected_total','predicted_total','total_projection','model_total']);
    const spreadPick=firstValue(rows,['spread_pick','ats_pick','spread_lean','predicted_winner'],projectedMargin!=='-'?`Model margin ${projectedMargin}`:'No spread prediction yet');
    const totalPick=firstValue(rows,['total_pick','ou_pick','total_lean'],projectedTotal!=='-'&&marketTotal!=='-'?(Number(projectedTotal)>Number(marketTotal)?'OVER':'UNDER'):'No total prediction yet');
    const spreadProb=firstValue(rows,['spread_probability','ats_probability','cover_probability','win_probability']);
    const totalProb=firstValue(rows,['total_probability','over_probability','ou_probability']);
    const pickHtml=picks.length?picks.map((p,i)=>`<div class="previewPick"><div class="previewPickRank mono">Top Pick ${i+1}</div><div class="previewPickTitle">${esc(val(p.player,'Game'))} ${esc(val(p.stat,p.market||''))} ${esc(val(p.signal||p.side,p.pick||''))}</div><div class="small mono">Line ${esc(val(p.line||p.consensus_line))} · ${esc(val(p.book||p.best_book||p.sportsbook))}</div><div class="chip mono">Score ${esc(val(p.final_score||p.confidence||p.edge_pct))}</div></div>`).join(''):'<div class="empty mono">No qualified game picks yet.</div>';
    return `<div class="previewPanel"><div class="previewHead"><div><div class="label mono">Quick Game Preview</div><div class="previewTitle mono">${esc(name)}</div><div class="small mono">${esc(val(g.start_time,'Time TBD'))} · ${esc(val(g.status,'Pregame'))}</div></div><button class="previewBtn" onclick="closeGamePreview()">Close</button></div><div class="previewGrid"><div class="previewStat"><div class="label mono">Market Spread</div><div class="previewValue mono">${esc(marketSpread)}</div><div class="small mono">Prediction: ${esc(spreadPick)} ${spreadProb!=='-'?'· '+esc(pct(spreadProb)):''}</div></div><div class="previewStat"><div class="label mono">Projected Margin</div><div class="previewValue mono">${esc(projectedMargin)}</div><div class="small mono">Model spread estimate</div></div><div class="previewStat"><div class="label mono">Market Total</div><div class="previewValue mono">${esc(marketTotal)}</div><div class="small mono">Prediction: ${esc(totalPick)} ${totalProb!=='-'?'· '+esc(pct(totalProb)):''}</div></div><div class="previewStat"><div class="label mono">Projected Total</div><div class="previewValue mono">${esc(projectedTotal)}</div><div class="small mono">Model scoring estimate</div></div></div><h3 class="mono">Top 3 Game Picks</h3><div class="previewPickGrid">${pickHtml}</div><div class="previewActions"><button class="previewBtn" onclick="openGameProps('${js(name)}')">View Player Props</button><button class="previewBtn" onclick="render('best')">Open Best Bets</button></div></div>`;
  }

  window.setGame=function(g){activeGame=String(g||'');render('props')};
  window.openGameProps=function(g){window.setGame(g)};
  window.openGamePreview=function(g){previewGame=String(g||'');render('games')};
  window.closeGamePreview=function(){previewGame='';render('games')};

  window.games=function(){
    const today=arr(DATA.today_games), yesterday=arr(DATA.yesterday_games);
    const selected=today.find(g=>sameGame(gameName(g),previewGame));
    const todayHtml=today.map(g=>{const name=gameName(g);return `<div class="gameCard selectable" role="button" tabindex="0" onclick="openGamePreview('${js(name)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openGamePreview('${js(name)}')}"><div class="row"><div><b class="mono">${esc(name)}</b><div class="small mono">${esc(val(g.start_time,'Time TBD'))} · ${esc(val(g.status,'Pregame'))}</div><div class="clickHint mono">Tap for spread, total, predictions, and top picks</div></div><div class="score mono">${esc(scoreText(g))}</div></div><span class="chip mono">Spread ${esc(val(g.spread))}</span><span class="chip mono">Total ${esc(val(g.total))}</span><div class="gameAction mono">Quick preview →</div></div>`}).join('')||'<div class="empty mono">No games.</div>';
    const yesterdayHtml=yesterday.map(g=>`<div class="gameCard"><div class="row"><div><b class="mono">${esc(gameName(g))}</b><div class="small mono">${esc(val(g.status,'Final'))}</div></div><div class="score mono">${esc(scoreText(g))}</div></div></div>`).join('')||'<div class="empty mono">No results.</div>';
    return kpis()+`<div class="grid2"><div class="section"><h2 class="mono">Today's Games</h2>${todayHtml}</div><div class="section"><h2 class="mono">Yesterday Results</h2>${yesterdayHtml}</div></div>${selected?predictionCard(selected):''}`;
  };

  window.results=function(){
    const r=DATA.results||{}, yesterday=arr(DATA.yesterday_games), wins=Number(r.wins||0), losses=Number(r.losses||0), pushes=Number(r.pushes||0), graded=Number(r.graded_this_run||r.graded||0), decisions=wins+losses;
    const rate=r.win_rate!==undefined?`${(Number(r.win_rate)*100).toFixed(1)}%`:(decisions?`${(wins/decisions*100).toFixed(1)}%`:'—'), status=val(r.status,graded?'ok':'waiting_for_actuals');
    const cards=`<div class="resultsGrid"><div class="resultKpi"><div class="label mono">Graded</div><div class="value mono">${graded}</div></div><div class="resultKpi"><div class="label mono">Wins</div><div class="value mono qa-green">${wins}</div></div><div class="resultKpi"><div class="label mono">Losses</div><div class="value mono qa-red">${losses}</div></div><div class="resultKpi"><div class="label mono">Pushes</div><div class="value mono">${pushes}</div></div><div class="resultKpi"><div class="label mono">Win Rate</div><div class="value mono">${rate}</div></div></div>`;
    const completed=yesterday.map(g=>`<div class="gameCard"><div class="row"><div><b class="mono">${esc(gameName(g))}</b><div class="small mono">${esc(val(g.status,'Final'))}</div></div><div class="resultScore mono">${esc(scoreText(g))}</div></div></div>`).join('');
    const message=status==='waiting_for_actuals'?'<div class="empty mono">Player results are waiting for completed boxscore data. Completed game scores appear below.</div>':'';
    return `<div class="section"><h2 class="mono">Results & Grading</h2><div class="small mono">Target ${esc(val(r.target_date,DATA.master?.target_date))} · Updated ${esc(val(r.generated_at_utc,DATA.generated_at_utc))}</div><div class="resultStatus mono">${esc(status)}</div>${cards}${message}</div><div class="section"><h2 class="mono">Recent Completed Games</h2><div class="resultRows">${completed||'<div class="empty mono">No completed games loaded yet.</div>'}</div></div>`;
  };
})();
</script>
"""


def replace_block(html: str, marker: str, closing: str, replacement: str) -> str:
    start = html.find(marker)
    if start < 0:
        return html
    end = html.find(closing, start)
    if end < 0:
        return html
    return html[:start] + replacement.strip() + html[end + len(closing):]


def main() -> None:
    if not PATH.exists():
        raise SystemExit("docs/index.html does not exist")
    html = PATH.read_text(encoding="utf-8")
    html = replace_block(html, '<style id="v4-core-interactions-style">', '</style>', CSS) if 'id="v4-core-interactions-style"' in html else html.replace("</head>", CSS + "</head>")
    html = replace_block(html, '<script id="v4-core-interactions-script">', '</script>', SCRIPT) if 'id="v4-core-interactions-script"' in html else html.replace("</body>", SCRIPT + "</body>")
    PATH.write_text(html, encoding="utf-8")
    print("Dashboard V4 game preview and results restored")


if __name__ == "__main__":
    main()
