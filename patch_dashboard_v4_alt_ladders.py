from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_alt_market_warehouse.json')
PARLAYS=Path('data/dashboard/wnba_alt_parlays.json')
MASTER=Path('data/dashboard/wnba_master.json')
CSS=r'''<style id="v4-alt-ladders-style">.alWrap{display:grid;gap:14px}.alPlayer{border:1px solid #21314b;border-radius:16px;background:#08101c;padding:14px}.alPlayer summary{cursor:pointer;font-weight:950;font-size:17px}.alStat{margin-top:12px;border-top:1px solid #20304b;padding-top:10px}.alBooks{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}.alBook{border:1px solid #263854;border-radius:12px;padding:10px;background:#0a1322}.alBookTitle{font-weight:900;margin-bottom:7px}.alLine{display:grid;grid-template-columns:68px 64px 1fr 1fr 1fr;gap:6px;align-items:center;padding:6px 0;border-top:1px solid #1c2a42;font-size:11px}.alLine:first-of-type{border-top:0}.alGood{color:#00e39b}.alBad{color:#ff6b7c}.alMuted{color:#8fa0bd}.alPill{border:1px solid currentColor;border-radius:999px;padding:3px 6px;text-align:center;font-weight:900}.alEmpty{padding:18px;text-align:center;color:#8fa0bd}.alSlateNote{margin:10px 0 14px;padding:10px 12px;border:1px solid #263854;border-radius:12px;color:#aebbd1;background:#0a1322}.altParlayWrap{display:grid;gap:12px;margin-top:14px}.altParlayGame{border:1px solid #243653;border-radius:14px;padding:12px;background:#091321}.altParlayGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;margin-top:10px}.altParlayCard{border:1px solid #2c4163;border-radius:12px;padding:11px;background:#0b1627}.altParlayTier{font-size:10px;font-weight:900;letter-spacing:.08em}.altParlayTier.SAFE{color:#00e39b}.altParlayTier.BALANCED{color:#f3c969}.altParlayTier.UPSIDE{color:#9db6ff}.altLeg{padding:7px 0;border-top:1px solid #1b2b45}.altLeg:first-of-type{border-top:0}.altParlayPrice{font-size:18px;font-weight:950}.altParlayNote{font-size:10px;color:#8fa0bd;margin-top:8px}@media(max-width:700px){.alLine{grid-template-columns:60px 58px 1fr 1fr}.alLine .alEv{display:none}.altParlayGrid{grid-template-columns:1fr}}</style>'''
SCRIPT=r'''<script id="v4-alt-ladders-script">(function(){
function norm(v){return String(v??'').trim().toLowerCase().replace(/[’]/g,"'").replace(/\s+/g,' ')}
function pct(v){return v==null?'—':(Number(v)*100).toFixed(0)+'%'}
function odds(v){const n=Number(v);return Number.isFinite(n)?(n>0?'+'+n:n):'—'}
function activeGameSet(){return new Set((DATA.active_alt_games||[]).map(norm).filter(Boolean))}
function lineCard(r){const ev=Number(r.expected_value_per_unit);const cls=Number.isFinite(ev)?(ev>0?'alGood':'alBad'):'alMuted';return `<div class="alLine"><span class="alPill">${E(r.display_threshold||r.threshold)}</span><b class="mono">${odds(r.odds)}</b><span>L5 ${pct(r.l5?.rate)}</span><span>L10 ${pct(r.l10?.rate)}</span><span class="alEv ${cls}">EV ${Number.isFinite(ev)?(ev*100).toFixed(1)+'%':'—'}</span></div>`}
function bookCard(book){return `<div class="alBook"><div class="alBookTitle">${E(book.sportsbook)}</div>${(book.lines||[]).map(lineCard).join('')}</div>`}
function playerCard(player){const stats=Object.values(player.stats||{}).map(stat=>`<div class="alStat"><b>${E(stat.stat)}</b><div class="alBooks">${Object.values(stat.sportsbooks||{}).map(bookCard).join('')}</div></div>`).join('');return `<details class="alPlayer"><summary>${E(player.player)} <span class="small mono">${E(player.game||'')}</span></summary>${stats}</details>`}
function marketCount(players){let total=0;players.forEach(p=>Object.values(p.stats||{}).forEach(s=>Object.values(s.sportsbooks||{}).forEach(b=>{total+=(b.lines||[]).length})));return total}
function legHtml(l){const ev=Number(l.expected_value_per_unit);return `<div class="altLeg"><b>${E(l.player||'')}</b> · ${E(l.stat||'')} ${E(l.side||'')} ${E(l.display_threshold||l.threshold||'')}<div class="small mono">${E(l.sportsbook||'')} ${odds(l.odds)} · L5 ${pct(l.l5_rate)} · L10 ${pct(l.l10_rate)}${Number.isFinite(ev)?` · EV ${(ev*100).toFixed(1)}%`:''}</div></div>`}
function parlayCard(p){return `<div class="altParlayCard"><div class="row"><span class="altParlayTier ${E(p.tier||'')}">${E(p.tier||'')}</span><span class="altParlayPrice mono">${odds(p.estimated_independent_price)}</span></div><div class="small mono">${E(p.kind==='CROSS_GAME_ALT'?'Cross-game ALT':'Same-game ALT')} · ${E(p.leg_count||0)} legs</div>${(p.legs||[]).map(legHtml).join('')}<div class="altParlayNote">${E(p.note||'')}</div></div>`}
function altParlaysSection(){const src=DATA.alt_parlays||{},all=Array.isArray(src.parlays)?src.parlays:[];if(!all.length)return '<div class="section"><h2 class="mono">ALT Prop Parlays</h2><div class="empty mono">No ALT parlays cleared the current framework.</div></div>';const same=all.filter(p=>p.kind==='SAME_GAME_ALT');const cross=all.filter(p=>p.kind==='CROSS_GAME_ALT');const grouped={};same.forEach(p=>{const g=(p.games||[])[0]||'Game';(grouped[g]||(grouped[g]=[])).push(p)});let html=`<div class="section"><div class="row"><div><h2 class="mono">ALT Prop Parlays</h2><div class="small mono">Target: 2–3 same-game ALT parlays per matchup, plus cross-game mixed cards when multiple games are active.</div></div><div class="badge mono">${all.length} cards</div></div><div class="bestPolicy"><span class="chip mono">Exact book lines</span><span class="chip mono">No duplicate player/partlay</span><span class="chip mono">SAFE · BALANCED · UPSIDE</span><span class="chip mono">Cross-game mixing enabled</span></div><div class="altParlayWrap">`;Object.entries(grouped).forEach(([g,ps])=>{html+=`<div class="altParlayGame"><b class="mono">${E(g)}</b><div class="altParlayGrid">${ps.map(parlayCard).join('')}</div></div>`});if(cross.length)html+=`<div class="altParlayGame"><b class="mono">Cross-Game Mix</b><div class="altParlayGrid">${cross.map(parlayCard).join('')}</div></div>`;html+='</div></div>';return html}
window.altLadders=function(){
 const p=DATA.alt_market_warehouse||{},all=Array.isArray(p.players)?p.players:[],s=p.summary||{},active=activeGameSet();
 const players=active.size?all.filter(x=>active.has(norm(x.game))):[];
 const markets=marketCount(players),excluded=Math.max(0,all.length-players.length),games=[...active];
 const note=active.size
  ?`${games.length} active game${games.length===1?'':'s'} · ${excluded} off-slate player${excluded===1?'':'s'} excluded · canonical slate ${E(DATA.active_alt_target_date||'')}`
  :'No canonical active-slate game was available, so historical ALT ladders are hidden.';
 return `<div class="section"><h2 class="mono">Sportsbook ALT Ladders</h2><div class="small mono">Exact thresholds from FanDuel, DraftKings, and Fanatics only. Books and lines remain separate; lines are never averaged.</div><div class="alSlateNote mono">${E(note)}</div><div class="row"><span>${E(markets)} active markets</span><span>${E(players.length)} active players</span><span>${(s.sportsbooks||[]).map(E).join(', ')||'No books'}</span></div><div class="alWrap">${players.map(playerCard).join('')||'<div class="alEmpty mono">No active-slate sportsbook alternate ladders were returned.</div>'}</div></div>`
};
const prior=window.altStreaks;window.altStreaks=function(){const base=typeof prior==='function'?prior():'';return window.altLadders()+base}
const priorBest=window.best;window.best=function(){const base=typeof priorBest==='function'?priorBest():'';return base+altParlaysSection()}
})();</script>'''

def replace_block(html,start,end,replacement):
    i=html.find(start)
    if i<0:return html
    j=html.find(end,i)
    if j<0:return html
    return html[:i]+replacement.strip()+html[j+len(end):]

def main():
    if not HTML.exists():raise SystemExit('docs/index.html missing')
    try:payload=json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
    except Exception:payload={}
    try:parlays=json.load(PARLAYS.open(encoding='utf-8')) if PARLAYS.exists() else {}
    except Exception:parlays={}
    try:master=json.load(MASTER.open(encoding='utf-8')) if MASTER.exists() else {}
    except Exception:master={}
    target=str(master.get('target_date') or '')
    games=[]
    for game in master.get('games',[]):
        if not isinstance(game,dict):continue
        if game.get('bucket')=='today' or (target and str(game.get('game_date') or '')==target):
            name=str(game.get('game') or '').strip()
            if name and name not in games:games.append(name)
    html=HTML.read_text(encoding='utf-8')
    data_payload={'alt_market_warehouse':payload,'alt_parlays':parlays,'active_alt_games':games,'active_alt_target_date':target}
    data=f'<script id="v4-alt-ladders-data">Object.assign(DATA,{json.dumps(data_payload,separators=(",",":"),ensure_ascii=False)});</script>'
    html=replace_block(html,'<script id="v4-alt-ladders-data">','</script>',data) if 'id="v4-alt-ladders-data"' in html else html.replace('</body>',data+'</body>')
    html=replace_block(html,'<style id="v4-alt-ladders-style">','</style>',CSS) if 'id="v4-alt-ladders-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace_block(html,'<script id="v4-alt-ladders-script">','</script>',SCRIPT) if 'id="v4-alt-ladders-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8')
    print({'alt_ladders':'filtered','target_date':target,'active_games':games,'alt_parlays':len(parlays.get('parlays') or [])})
if __name__=='__main__':main()
