from __future__ import annotations

import re
from pathlib import Path

DOC = Path("docs/index.html")

CSS = r'''
/* Final V4 Player Props polish */
.gameChips{display:flex;flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:none;padding:2px 0 7px;white-space:nowrap}.gameChips::-webkit-scrollbar{display:none}.gameChip{flex:0 0 auto}
.tools{grid-template-columns:minmax(180px,1.35fr) minmax(120px,.75fr) minmax(120px,.75fr) minmax(140px,.85fr) minmax(180px,1.1fr);align-items:center}
.tools input,.tools select{height:46px;width:100%}
.propScroll{position:relative;overflow-x:auto;overflow-y:visible;overscroll-behavior-x:contain}
.propHead,.propRow{grid-template-columns:minmax(190px,1.35fr) 58px 64px 86px 86px minmax(230px,1.25fr) 70px 70px 54px;gap:8px}
.propHead{position:relative;top:auto;padding:12px 14px}.propHead button{appearance:none;border:0;background:transparent;color:inherit;font:inherit;text-transform:inherit;letter-spacing:inherit;padding:0;cursor:pointer;text-align:left}.propHead button:hover{color:#dce6ff}.propHead button.sortActive{color:var(--green)}
.propRow{padding:12px 14px;min-height:78px}.propRow.value-high{box-shadow:inset 4px 0 0 var(--green)}.propRow.value-medium{box-shadow:inset 4px 0 0 var(--gold)}.propRow.value-low{box-shadow:inset 4px 0 0 #53627d}
.player{min-width:0}.player>div:last-child{min-width:0}.name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.stat,.lineVal,.odds,.hit,.match{text-align:center}.hist{min-width:0}.boxes{justify-content:center;gap:5px}.box{width:36px;height:40px}.avg{white-space:nowrap}.bookPrice{display:flex;align-items:center;justify-content:center;gap:5px;white-space:nowrap}.bookTag{display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:20px;padding:0 5px;border:1px solid #334766;border-radius:6px;background:#111b2d;color:#a9bce0;font-size:9px;font-weight:900}.bookTag.dk{border-color:#4cc99a;color:#62e5b4}.bookTag.fd{border-color:#4b8cff;color:#7eb0ff}.bookTag.fanatics{border-color:#f15b68;color:#ff7e88}.bookTag.caesars{border-color:#c99a45;color:#e4bd69}.bookTag.br{border-color:#61a5c2;color:#7cc3df}
.propMeta{display:flex;justify-content:space-between;gap:12px;align-items:center;margin:4px 0 8px}.sortNote{color:#65728a;font-size:11px}
@media(max-width:980px){.tools{grid-template-columns:1fr 1fr}.tools input:last-child{grid-column:1/-1}.propHead,.propRow{min-width:1020px}.propScroll{margin-left:0;margin-right:0}.section{padding:14px}.propRow{min-height:74px}}
@media(max-width:620px){.tools{grid-template-columns:1fr}.tools input:last-child{grid-column:auto}.propHead,.propRow{min-width:980px}.gameChip{padding:9px 11px;font-size:12px}.section{padding:12px}.title{font-size:27px}}
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        print(f"[warn] {label}: target not found")
        return text
    return text.replace(old, new, 1)


def main() -> None:
    if not DOC.exists():
        raise SystemExit("docs/index.html missing")
    html = DOC.read_text(encoding="utf-8")

    if "/* Final V4 Player Props polish */" not in html:
        html = html.replace("</style>", CSS + "\n</style>", 1)

    html = replace_once(
        html,
        "let activeGame=''; const A=x=>Array.isArray(x)?x:[],",
        "let activeGame='',propSort={key:'',dir:1}; const A=x=>Array.isArray(x)?x:[],",
        "sort state",
    )

    html = re.sub(
        r"function propsRaw\(\)\{return A\(DATA\.master\?\.props\)\}",
        """function propsRaw(){let map=new Map();for(const r of A(DATA.master?.props)){let key=[r.player,r.stat,r.line??r.consensus_line,r.game,r.best_over_price??r.over_price,r.best_under_price??r.under_price].join('|').toLowerCase();let old=map.get(key);if(!old||Number(r.book_count||0)>Number(old.book_count||0)||Number(r.confidence||0)>Number(old.confidence||0))map.set(key,r)}return [...map.values()]}""",
        html,
        count=1,
    )

    # Keep game chips tied to the active slate only.
    html = re.sub(
        r"function gamesList\(\)\{return \[\.\.\.new Set\([^}]+\)\]\}",
        "function gamesList(){return [...new Set(A(DATA.today_games).map(game).filter(Boolean))]}",
        html,
        count=1,
    )

    helpers = r'''
function gameTeams(g){return String(g||'').split(' @ ').map(x=>x.trim()).filter(Boolean)}
function sameGame(a,b){let aa=gameTeams(a),bb=gameTeams(b);return aa.length===2&&bb.length===2&&aa.every(x=>bb.includes(x))}
function propMatchesGame(r,g){if(!g)return true;if(sameGame(r.game,g))return true;let ts=gameTeams(g),pt=String(r.player_team||r.team||''),op=String(r.opponent||'');return ts.includes(pt)&&(!op||ts.includes(op))}
function bookCode(b){let s=String(b||'').toLowerCase();if(s.includes('draft'))return ['DK','dk'];if(s.includes('fanduel'))return ['FD','fd'];if(s.includes('fanatics'))return ['FAN','fanatics'];if(s.includes('caesar'))return ['CZR','caesars'];if(s.includes('betrivers'))return ['BR','br'];if(s.includes('betonline'))return ['BOL',''];return [String(b||'').slice(0,3).toUpperCase(),'']}
function priceHtml(book,price){let c=bookCode(book);return `<span class="bookPrice"><span class="bookTag ${c[1]}">${E(c[0]||'--')}</span><span>${E(S(price))}</span></span>`}
function setPropSort(key){if(propSort.key===key)propSort.dir*=-1;else propSort={key,dir:1};drawProps()}
function sortValue(r,key){if(key==='player'||key==='stat')return String(r[key]||'').toLowerCase();if(key==='line')return Number(r.line??r.consensus_line??-999);if(key==='over')return Number(r.best_over_price??r.over_price??-9999);if(key==='under')return Number(r.best_under_price??r.under_price??-9999);let side=S(r.signal||r.side,'OVER'),line=Number(r.line??r.consensus_line??0);if(key==='l5')return hit(hist(r,5),line,side).p;if(key==='l10')return hit(hist(r,10),line,side).p;if(key==='match')return Number(r.confidence||r.final_score||0);return 0}
function sortRows(rows){if(!propSort.key)return rows;return [...rows].sort((a,b)=>{let x=sortValue(a,propSort.key),y=sortValue(b,propSort.key);return (typeof x==='string'?x.localeCompare(y):x-y)*propSort.dir})}
function sortLabel(key,label){let mark=propSort.key===key?(propSort.dir>0?' ▲':' ▼'):'';return `<button class="${propSort.key===key?'sortActive':''}" onclick="setPropSort('${key}')">${label}${mark}</button>`}
'''
    if "function bookCode(" not in html:
        html = html.replace("function propRow(r){", helpers + "\nfunction propRow(r){", 1)

    # Upgrade the row with book labels and value highlighting.
    pattern = re.compile(r"function propRow\(r\)\{.*?\}\nfunction props\(\)", re.S)
    new_row = r'''function propRow(r){let team=teamFor(r),opp=S(r.opponent_abbr||abbr(oppFor(r,team))),side=S(r.signal||r.side,'OVER'),line=Number(S(r.line||r.consensus_line,0)),v5=hist(r,5),v10=hist(r,10),h5=hit(v5,line,side),h10=hit(v10,line,side),conf=Number(r.confidence||r.final_score||0),valueClass=conf>=80?'value-high':conf>=65?'value-medium':'value-low',ob=r.best_over_book||r.book||'',ub=r.best_under_book||r.book||'';return `<div class="propRow ${valueClass}"><div class="player"><div class="logo mono">${r.team_logo?`<img src="${E(r.team_logo)}" alt="${E(abbr(team))}">`:E(abbr(team).slice(0,2)||String(r.player||'?').slice(0,2))}</div><div><div class="name">${E(r.player)}</div><div class="team mono">${E(r.team_abbr||abbr(team))}</div></div></div><div class="stat mono">${E(r.stat)}</div><div class="lineVal mono">${E(S(r.line||r.consensus_line))}</div><div class="odds mono">${priceHtml(ob,r.best_over_price||r.over_price)}</div><div class="odds mono">${priceHtml(ub,r.best_under_price||r.under_price)}</div><div class="hist"><div class="boxes">${v5.map(v=>`<div class="box ${isHit(v,line,side)?'':'miss'}"><div class="num mono">${v}</div><div class="opp mono">${E(opp)}</div></div>`).join('')}</div><div class="avg mono">L5 ${E(r.stat)} avg ${(v5.reduce((a,b)=>a+b,0)/5).toFixed(1)}</div></div><div class="hit ${h5.p<50?'bad':''} mono"><div class="pct">${h5.p}%</div><div>${E(side)}</div><div class="rec">${h5.h}/5</div></div><div class="hit ${h10.p<50?'bad':''} mono"><div class="pct">${h10.p}%</div><div>${E(side)}</div><div class="rec">${h10.h}/10</div></div><div class="small mono match">${E(S(conf||'-'))}</div></div>`}
function props()'''
    html, n = pattern.subn(new_row, html, count=1)
    if not n:
        print("[warn] propRow replacement not applied")

    old_head = '<div class="small mono" id="propCount"></div><div class="propScroll"><div class="propHead mono"><div>Player</div><div>Stat</div><div>Line</div><div>Over</div><div>Under</div><div>L5 Stats</div><div>L5 Hit</div><div>L10 Hit</div><div>Match</div></div><div id="propRows"></div></div>'
    new_head = '<div class="propMeta"><div class="small mono" id="propCount"></div><div class="sortNote mono">Tap a header to sort</div></div><div class="propScroll"><div class="propHead mono"><div>${sortLabel(\'player\',\'Player\')}</div><div>${sortLabel(\'stat\',\'Stat\')}</div><div>${sortLabel(\'line\',\'Line\')}</div><div>${sortLabel(\'over\',\'Over\')}</div><div>${sortLabel(\'under\',\'Under\')}</div><div>L5 Stats</div><div>${sortLabel(\'l5\',\'L5 Hit\')}</div><div>${sortLabel(\'l10\',\'L10 Hit\')}</div><div>${sortLabel(\'match\',\'Match\')}</div></div><div id="propRows"></div></div>'
    html = replace_once(html, old_head, new_head, "sortable header")

    draw_pattern = re.compile(r"function drawProps\(\)\{.*?\} function setGame\(g\)\{activeGame=g;render\('props'\)\}", re.S)
    draw_new = r'''function drawProps(){let all=propsRaw(),p=S(q('fPlayer')?.value,'').toLowerCase(),st=S(q('fStat')?.value,''),si=S(q('fSide')?.value,''),b=S(q('fBook')?.value,''),se=S(q('fSearch')?.value,'').toLowerCase();let rows=all.filter(r=>propMatchesGame(r,activeGame)&&(!p||String(r.player||'').toLowerCase().includes(p))&&(!st||r.stat===st)&&(!si||(r.signal||r.side)===si)&&(!b||[r.book,r.best_book,r.best_over_book,r.best_under_book].includes(b))&&(!se||JSON.stringify(r).toLowerCase().includes(se)));rows=sortRows(rows);q('propCount').textContent=`Showing ${rows.length} of ${all.length} unique props${activeGame?' · '+activeGame:''}`;q('propRows').innerHTML=rows.map(propRow).join('')||'<div class="empty mono">No current props are available for this game.</div>'} function setGame(g){activeGame=g;render('props')}'''
    html, n = draw_pattern.subn(draw_new, html, count=1)
    if not n:
        print("[warn] drawProps replacement not applied")

    DOC.write_text(html, encoding="utf-8")
    print("Dashboard V4 Player Props polish applied")


if __name__ == "__main__":
    main()
