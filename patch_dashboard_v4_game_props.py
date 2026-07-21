from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_game_props_q1.json')
CSS=r'''<style id="v4-game-props-style">
.gpGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.gpGame{background:#08101c;border:1px solid #1e2a43;border-radius:16px;padding:15px}.gpRace{display:grid;grid-template-columns:80px 1fr 1fr;gap:8px;align-items:center;padding:10px 0;border-top:1px solid #172238}.gpProb{font-size:20px;font-weight:900;color:#00e39b}.gpWarn{border:1px solid #745b18;background:#211a08;color:#ffe09a;border-radius:14px;padding:12px;margin:12px 0}.gpTableWrap{overflow:auto;border:1px solid #1e2a43;border-radius:16px}.gpTable{min-width:850px}.gpEmpty{padding:24px;color:#7e8ba3;text-align:center}.gpSource{font-size:10px;color:#7e8ba3;margin-top:4px}@media(max-width:900px){.gpGrid{grid-template-columns:1fr}}
</style>'''

def script(payload):
    data=json.dumps(payload,separators=(',',':'),ensure_ascii=False)
    return f'''<script id="v4-game-props-script">
(function(){{
 const GP={data}; const esc=v=>typeof E==='function'?E(v):String(v??''); const arr=v=>Array.isArray(v)?v:[]; const pct=v=>v===null||v===undefined?'-':(Number(v)*100).toFixed(1)+'%';
 window.gameProps=function(){{
  const s=GP.summary||{{}}, games=arr(GP.games), players=arr(GP.player_q1_points), money=arr(GP.sportsbook_q1_moneyline);
  const cards=`<div class="grid"><div class="card"><div class="label mono">Games</div><div class="big mono">${{s.games||0}}</div></div><div class="card"><div class="label mono">Q1 Player Props</div><div class="big mono">${{s.player_q1_props||0}}</div></div><div class="card"><div class="label mono">Race Models</div><div class="big mono">${{s.race_model_rows||0}}</div></div><div class="card"><div class="label mono">Sportsbook Q1 ML</div><div class="big mono">${{s.sportsbook_q1_moneylines||0}}</div></div></div>`;
  const gameHtml=games.map(g=>`<div class="gpGame"><h3 class="mono">${{esc(g.game)}}</h3><div class="small mono">Q1 averages: ${{esc(g.away_team)}} ${{esc(g.away_q1_average??'-')}} · ${{esc(g.home_team)}} ${{esc(g.home_q1_average??'-')}}</div><div class="small mono">Samples: ${{g.away_samples||0}} / ${{g.home_samples||0}}</div><div class="gpRace"><b>Q1 Winner</b><div><span class="gpProb">${{pct(g.q1_winner_model?.away_probability)}}</span><div class="small">${{esc(g.away_team)}}</div></div><div><span class="gpProb">${{pct(g.q1_winner_model?.home_probability)}}</span><div class="small">${{esc(g.home_team)}}</div></div></div>${{arr(g.race_markets).map(r=>`<div class="gpRace"><b>Race ${{r.threshold}}</b><div><span class="gpProb">${{pct(r.away_probability)}}</span><div class="small">${{esc(r.away_team)}}</div></div><div><span class="gpProb">${{pct(r.home_probability)}}</span><div class="small">${{esc(r.home_team)}}</div></div></div>`).join('')}}<div class="gpSource mono">Model estimates only until sportsbook odds are supplied.</div></div>`).join('')||'<div class="gpEmpty mono">No current games.</div>';
  const playerRows=players.map(p=>`<tr><td><b>${{esc(p.player)}}</b><div class="small mono">${{esc(p.game)}}</div></td><td>Q1 PTS</td><td>${{esc(p.line??'-')}}</td><td>${{esc(p.over_price??'-')}}</td><td>${{esc(p.under_price??'-')}}</td><td>${{esc(p.num_books||0)}}</td><td>${{esc(p.source||'-')}}</td></tr>`).join('');
  const moneyRows=money.map(m=>`<tr><td>${{esc(m.game)}}</td><td><b>${{esc(m.team)}}</b></td><td>${{esc(m.price??'-')}}</td><td>${{esc(m.sportsbook||'-')}}</td><td>${{esc(m.source||'-')}}</td></tr>`).join('');
  return cards+`<div class="section"><h2 class="mono">First Quarter Game Props</h2><div class="gpWarn"><b>Market guardrail:</b> race-to-10/15/20 values are model probabilities. They are not sportsbook odds and are not automatic bets.</div><div class="gpGrid">${{gameHtml}}</div></div><div class="section"><h2 class="mono">Q1 Player Points</h2><div class="gpTableWrap"><table class="gpTable"><thead><tr><th>Player</th><th>Stat</th><th>Line</th><th>Over</th><th>Under</th><th>Books</th><th>Source</th></tr></thead><tbody>${{playerRows||'<tr><td colspan="7" class="gpEmpty">The sportsbook feed has not supplied Q1 player-point lines.</td></tr>'}}</tbody></table></div></div><div class="section"><h2 class="mono">Team First-Quarter Winner</h2><div class="gpTableWrap"><table class="gpTable"><thead><tr><th>Game</th><th>Team</th><th>Odds</th><th>Book</th><th>Source</th></tr></thead><tbody>${{moneyRows||'<tr><td colspan="5" class="gpEmpty">No sportsbook Q1 moneyline rows are currently available. Model probabilities remain above.</td></tr>'}}</tbody></table></div></div>`;
 }};
}})();
</script>'''

def replace(html,start,end,replacement):
    i=html.find(start)
    if i<0:return html
    j=html.find(end,i)
    return html if j<0 else html[:i]+replacement+html[j+len(end):]

def main():
    if not HTML.exists():raise SystemExit('docs/index.html missing')
    payload=json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
    html=HTML.read_text(encoding='utf-8');js=script(payload)
    html=replace(html,'<style id="v4-game-props-style">','</style>',CSS) if 'id="v4-game-props-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace(html,'<script id="v4-game-props-script">','</script>',js) if 'id="v4-game-props-script"' in html else html.replace('</body>',js+'</body>')
    HTML.write_text(html,encoding='utf-8');print('Game Props Q1 dashboard active')
if __name__=='__main__':main()
