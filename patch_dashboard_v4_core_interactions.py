from __future__ import annotations

from pathlib import Path

PATH = Path("docs/index.html")

CSS = r"""
<style id="v4-core-interactions-style">
.gameCard.selectable{cursor:pointer;transition:transform .12s ease,border-color .12s ease}.gameCard.selectable:hover,.gameCard.selectable:focus{border-color:#80a8ff;transform:translateY(-1px);outline:none}.gameAction{margin-top:10px;display:inline-flex;border:1px solid #304365;border-radius:999px;padding:6px 10px;color:#b8c8e8;font-size:12px;font-weight:800}.resultsGrid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:14px 0}.resultKpi{background:#08101c;border:1px solid #1e2a43;border-radius:15px;padding:14px}.resultKpi .value{font-size:25px;font-weight:900;margin-top:5px}.resultStatus{display:inline-flex;border:1px solid #304365;border-radius:999px;padding:6px 10px;margin-top:8px}.resultRows{display:grid;grid-template-columns:1fr 1fr;gap:12px}.resultScore{font-size:22px;font-weight:900}.clickHint{color:#80a8ff;font-size:11px;margin-top:5px}@media(max-width:900px){.resultsGrid,.resultRows{grid-template-columns:1fr 1fr}.resultsGrid .resultKpi:last-child{grid-column:1/-1}}
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

  window.setGame=function(g){
    activeGame=String(g||'');
    render('props');
  };
  window.openGameProps=function(g){window.setGame(g)};

  window.games=function(){
    const today=arr(DATA.today_games), yesterday=arr(DATA.yesterday_games);
    const todayHtml=today.map(g=>{
      const name=gameName(g);
      return `<div class="gameCard selectable" role="button" tabindex="0" onclick="openGameProps('${js(name)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openGameProps('${js(name)}')}"><div class="row"><div><b class="mono">${esc(name)}</b><div class="small mono">${esc(val(g.start_time,'Time TBD'))} · ${esc(val(g.status,'Pregame'))}</div><div class="clickHint mono">Tap to view this game's player props</div></div><div class="score mono">${esc(scoreText(g))}</div></div><span class="chip mono">Spread ${esc(val(g.spread))}</span><span class="chip mono">Total ${esc(val(g.total))}</span><div class="gameAction mono">Select game →</div></div>`;
    }).join('')||'<div class="empty mono">No games.</div>';
    const yesterdayHtml=yesterday.map(g=>`<div class="gameCard"><div class="row"><div><b class="mono">${esc(gameName(g))}</b><div class="small mono">${esc(val(g.status,'Final'))}</div></div><div class="score mono">${esc(scoreText(g))}</div></div></div>`).join('')||'<div class="empty mono">No results.</div>';
    return kpis()+`<div class="grid2"><div class="section"><h2 class="mono">Today's Games</h2>${todayHtml}</div><div class="section"><h2 class="mono">Yesterday Results</h2>${yesterdayHtml}</div></div>`;
  };

  window.results=function(){
    const r=DATA.results||{};
    const yesterday=arr(DATA.yesterday_games);
    const wins=Number(r.wins||0), losses=Number(r.losses||0), pushes=Number(r.pushes||0);
    const graded=Number(r.graded_this_run||r.graded||0);
    const decisions=wins+losses;
    const rate=r.win_rate!==undefined?`${(Number(r.win_rate)*100).toFixed(1)}%`:(decisions?`${(wins/decisions*100).toFixed(1)}%`:'—');
    const status=val(r.status,graded?'ok':'waiting_for_actuals');
    const cards=`<div class="resultsGrid"><div class="resultKpi"><div class="label mono">Graded</div><div class="value mono">${graded}</div></div><div class="resultKpi"><div class="label mono">Wins</div><div class="value mono qa-green">${wins}</div></div><div class="resultKpi"><div class="label mono">Losses</div><div class="value mono qa-red">${losses}</div></div><div class="resultKpi"><div class="label mono">Pushes</div><div class="value mono">${pushes}</div></div><div class="resultKpi"><div class="label mono">Win Rate</div><div class="value mono">${rate}</div></div></div>`;
    const completed=yesterday.map(g=>`<div class="gameCard"><div class="row"><div><b class="mono">${esc(gameName(g))}</b><div class="small mono">${esc(val(g.status,'Final'))}</div></div><div class="resultScore mono">${esc(scoreText(g))}</div></div></div>`).join('');
    const message=status==='waiting_for_actuals'?'<div class="empty mono">Player results are waiting for completed boxscore data. Completed game scores appear below.</div>':'';
    return `<div class="section"><h2 class="mono">Results & Grading</h2><div class="small mono">Target ${esc(val(r.target_date,DATA.master?.target_date))} · Updated ${esc(val(r.generated_at_utc,DATA.generated_at_utc))}</div><div class="resultStatus mono">${esc(status)}</div>${cards}${message}</div><div class="section"><h2 class="mono">Recent Completed Games</h2><div class="resultRows">${completed||'<div class="empty mono">No completed games loaded yet.</div>'}</div></div>`;
  };

  // Repaint the active view so this patch takes effect immediately after load.
  const active=document.querySelector('.tab.a');
  const label=active?active.textContent.trim():'';
  if(label==='Games') render('games');
  else if(label==='Results') render('results');
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
    if 'id="v4-core-interactions-style"' in html:
        html = replace_block(html, '<style id="v4-core-interactions-style">', '</style>', CSS)
    else:
        html = html.replace("</head>", CSS + "</head>")
    if 'id="v4-core-interactions-script"' in html:
        html = replace_block(html, '<script id="v4-core-interactions-script">', '</script>', SCRIPT)
    else:
        html = html.replace("</body>", SCRIPT + "</body>")
    PATH.write_text(html, encoding="utf-8")
    print("Dashboard V4 core interactions restored")


if __name__ == "__main__":
    main()
