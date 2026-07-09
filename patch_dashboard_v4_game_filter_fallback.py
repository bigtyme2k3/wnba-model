from __future__ import annotations

from pathlib import Path

DOC = Path("docs/index.html")


def main() -> None:
    if not DOC.exists():
        raise SystemExit("docs/index.html missing")
    html = DOC.read_text(encoding="utf-8")

    old = """function drawProps(){let rows=propsRaw(), p=S(q('fPlayer')?.value,'').toLowerCase(), st=S(q('fStat')?.value,''), si=S(q('fSide')?.value,''), b=S(q('fBook')?.value,''), se=S(q('fSearch')?.value,'').toLowerCase();rows=rows.filter(r=>(!activeGame||r.game===activeGame)&&(!p||String(r.player||'').toLowerCase().includes(p))&&(!st||r.stat===st)&&(!si||(r.signal||r.side)===si)&&(!b||(r.book||r.best_book||r.best_over_book)===b)&&(!se||JSON.stringify(r).toLowerCase().includes(se)));q('propCount').textContent=`Showing ${rows.length} of ${propsRaw().length} props${activeGame?' · '+activeGame:''}`;q('propRows').innerHTML=rows.map(propRow).join('')||'<div class="empty mono">No props match.</div>'} function setGame(g){activeGame=g;render('props')}"""
    new = """function teamsFromGame(g){return String(g||'').split(' @ ').map(x=>x.trim()).filter(Boolean)}
function sameGame(a,b){if(!a||!b)return false;if(a===b)return true;let aa=teamsFromGame(a),bb=teamsFromGame(b);return aa.length===2&&bb.length===2&&aa.includes(bb[0])&&aa.includes(bb[1])}
function propBelongsToGame(r,g){if(!g)return true;if(sameGame(r.game,g))return true;let teams=teamsFromGame(g),pt=r.player_team||r.team||'',op=r.opponent||'';return teams.includes(pt)&&(!op||teams.includes(op))}
function drawProps(){let all=propsRaw(), p=S(q('fPlayer')?.value,'').toLowerCase(), st=S(q('fStat')?.value,''), si=S(q('fSide')?.value,''), b=S(q('fBook')?.value,''), se=S(q('fSearch')?.value,'').toLowerCase();let gameRows=activeGame?all.filter(r=>propBelongsToGame(r,activeGame)):all;let gameMatched=gameRows.length;if(activeGame&&gameRows.length===0){gameRows=all}let rows=gameRows.filter(r=>(!p||String(r.player||'').toLowerCase().includes(p))&&(!st||r.stat===st)&&(!si||(r.signal||r.side)===si)&&(!b||(r.book||r.best_book||r.best_over_book)===b)&&(!se||JSON.stringify(r).toLowerCase().includes(se)));let note=activeGame?` · ${activeGame}`:'';if(activeGame&&gameMatched===0)note+=` · no exact prop feed yet, showing all available props`;q('propCount').textContent=`Showing ${rows.length} of ${all.length} props${note}`;q('propRows').innerHTML=rows.map(propRow).join('')||'<div class="empty mono">No props match.</div>'} function setGame(g){activeGame=g;render('props')}"""

    if old not in html:
        raise SystemExit("drawProps block not found; V4 template changed")
    html = html.replace(old, new)
    DOC.write_text(html, encoding="utf-8")
    print("Dashboard V4 single-game prop filter fallback applied")


if __name__ == "__main__":
    main()
