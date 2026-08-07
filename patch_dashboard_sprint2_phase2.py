from __future__ import annotations

import json
import re
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_sprint2_phase2.json')
STYLE_ID='sprint2-phase2-style'
SCRIPT_ID='sprint2-phase2-script'

STYLE=r'''<style id="sprint2-phase2-style">
.s2Wrap{display:grid;gap:16px}.s2Game{background:linear-gradient(180deg,#101827,#08101b);border:1px solid #263854;border-radius:18px;padding:16px}.s2Head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.s2Grade{border:1px solid #31506d;border-radius:12px;padding:8px 12px;text-align:center;min-width:70px}.s2Grade b{font-size:22px;color:#00e39b}.s2Score{font-size:24px;font-weight:900;margin:8px 0}.s2Grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:12px}.s2Metric{background:#08111f;border:1px solid #1d2c43;border-radius:12px;padding:10px}.s2Metric .v{font-size:18px;font-weight:900;color:#eaf3ff;margin-top:4px}.s2Metric .good{color:#00e39b}.s2Metric .warn{color:#ffd166}.s2Teams{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.s2Team{background:#07101c;border:1px solid #1d2c43;border-radius:12px;padding:11px}.s2TeamGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px}.s2Mini{font-size:11px;color:#8190aa}.s2Mini b{display:block;color:#e9f1ff;font-size:14px;margin-top:2px}.s2Rec{margin-top:12px;padding:10px;border:1px solid #235444;background:#08261e;border-radius:12px}.s2Method{margin-top:14px;color:#6f809c;font-size:11px}.s2Quick{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.s2Quick button{border:1px solid #304365;border-radius:999px;padding:7px 10px;background:#0a1424;color:#cbd8ef}.s2Injury{color:#ffd166}.s2NoInjury{color:#72d8b3}@media(max-width:900px){.s2Grid{grid-template-columns:repeat(2,1fr)}.s2Teams{grid-template-columns:1fr}.s2TeamGrid{grid-template-columns:repeat(3,1fr)}}
</style>'''


def main():
    if not HTML.exists(): raise SystemExit('docs/index.html missing')
    if not DATA.exists(): raise SystemExit('Sprint 2 Phase 2 data missing')
    payload=json.loads(DATA.read_text(encoding='utf-8'))
    raw=json.dumps(payload,separators=(',',':')).replace('</','<\\/')
    script=r'''<script id="sprint2-phase2-script">(function(){
const D=__PAYLOAD__;window.WNBA_SPRINT2_PHASE2=D;
const esc=v=>String(v??'—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const num=(v,d=1)=>v===null||v===undefined||v===''?'—':Number(v).toFixed(d);
const pct=v=>v===null||v===undefined?'—':(Number(v)*100).toFixed(1)+'%';
function injuryText(t){const i=t?.injury||{};if(!(i.players||i.out||i.questionable))return '<span class="s2NoInjury">No current-date injury adjustment</span>';return `<span class="s2Injury">${i.out||0} OUT · ${i.questionable||0} Q/D · ${num(i.minutes_lost,1)} min lost</span>`}
function teamBlock(name,t){return `<div class="s2Team"><b>${esc(name)}</b><div class="s2TeamGrid"><div class="s2Mini">OFF INDEX<b>${num(t?.offense_index,1)}</b></div><div class="s2Mini">DEF INDEX<b>${num(t?.defense_index,1)}</b></div><div class="s2Mini">POWER<b>${num(t?.power_rating,1)}</b></div><div class="s2Mini">L5 NET<b>${num(t?.last5_net_margin,1)}</b></div><div class="s2Mini">PACE IDX<b>${num(t?.pace_index,1)}</b></div><div class="s2Mini">REST<b>${t?.rest_days==null?'—':esc(t.rest_days)+'d'}</b></div></div><div class="small mono" style="margin-top:8px">${injuryText(t)}</div></div>`}
function quick(game){const q=String(game||'').replace(/'/g,"\\'");return `<div class="s2Quick"><button onclick="window.render('props');setTimeout(()=>{if(typeof window.setGame==='function')window.setGame('${q}')},0)">Player Props</button><button onclick="window.render('alt-props')">ALT Props</button><button onclick="window.render('matchups')">Matchup Detail</button></div>`}
window.gamesV25=function(){const games=Array.isArray(D.games)?D.games:[];const cards=games.map(g=>{const p=g.projection||{},m=g.market||{},e=g.edge||{},r=g.recommendation||{},a=g.teams?.away||{},h=g.teams?.home||{};const spreadGood=Math.abs(Number(e.spread||0))>=2,totalGood=Math.abs(Number(e.total||0))>=3;return `<div class="s2Game"><div class="s2Head"><div><div class="label mono">${esc(g.start_time||'Pregame')}</div><h2 class="mono" style="margin:4px 0">${esc(g.game)}</h2><div class="s2Score mono">${esc(g.away_team)} ${num(p.away_score,1)} · ${esc(g.home_team)} ${num(p.home_score,1)}</div></div><div class="s2Grade"><div class="label mono">GRADE</div><b class="mono">${esc(g.model_grade)}</b><div class="small mono">${num(g.confidence,0)} conf</div></div></div><div class="s2Grid"><div class="s2Metric"><div class="label mono">WIN PROB</div><div class="v mono">${esc(g.home_team)} ${pct(p.home_win_probability)}</div></div><div class="s2Metric"><div class="label mono">SPREAD</div><div class="v mono">Book ${num(m.home_spread,1)} · Model ${num(p.model_home_spread,1)}</div><div class="small mono ${spreadGood?'good':''}">Edge ${num(e.spread,1)}</div></div><div class="s2Metric"><div class="label mono">TOTAL</div><div class="v mono">Book ${num(m.total,1)} · Model ${num(p.total,1)}</div><div class="small mono ${totalGood?'good':''}">Edge ${num(e.total,1)}</div></div><div class="s2Metric"><div class="label mono">PACE</div><div class="v mono">${num(g.pace_index,1)} ${esc(g.pace_label)}</div><div class="small mono">Score-tempo proxy</div></div><div class="s2Metric"><div class="label mono">SPREAD PICK</div><div class="v mono ${spreadGood?'good':''}">${esc(r.spread||'PASS')}</div></div><div class="s2Metric"><div class="label mono">TOTAL PICK</div><div class="v mono ${totalGood?'good':''}">${esc(r.total||'PASS')}</div></div><div class="s2Metric"><div class="label mono">REST ADV HOME</div><div class="v mono">${g.rest_advantage_home==null?'—':num(g.rest_advantage_home,0)+'d'}</div></div><div class="s2Metric"><div class="label mono">INJURY ADJ</div><div class="v mono">${g.injury_adjusted?'YES':'NO'}</div></div></div><div class="s2Teams">${teamBlock(g.away_team,a)}${teamBlock(g.home_team,h)}</div><div class="s2Rec mono"><b>Model:</b> Spread ${esc(r.spread||'PASS')} · Total ${esc(r.total||'PASS')} · Confidence ${num(g.confidence,0)} · Grade ${esc(g.model_grade)}</div>${quick(g.game)}</div>`}).join('');return `<div class="section"><h2 class="mono">Today's Games · Prediction Intelligence</h2><div class="small mono">Projected score, market comparison, team form, pace, rest and current-date injury adjustments.</div><div class="s2Wrap" style="margin-top:14px">${cards||'<div class="empty mono">No current-slate projections.</div>'}</div><div class="s2Method mono">Phase 2 transparency: OFF/DEF and pace are model indices/proxies, not official possession-based ratings. Edge value is model-vs-market gap, not guaranteed ROI.</div></div>`};
if(window.WNBA_V4_UI_FREEZE&&typeof window.render==='function')window.render('games');
})();</script>'''.replace('__PAYLOAD__',raw)
    html=HTML.read_text(encoding='utf-8')
    html=re.sub(r'<style id="sprint2-phase2-style">.*?</style>','',html,flags=re.S)
    html=re.sub(r'<script id="sprint2-phase2-script">.*?</script>','',html,flags=re.S)
    html=html.replace('</head>',STYLE+'\n</head>',1)
    html=html.replace('</body>',script+'\n</body>',1)
    HTML.write_text(html,encoding='utf-8')
    print({'status':'PASS','sprint':'2','phase':'2','games':len(payload.get('games') or [])})

if __name__=='__main__': main()
