from __future__ import annotations

from pathlib import Path

DOC = Path("docs/index.html")


def main() -> None:
    if not DOC.exists():
        raise SystemExit("docs/index.html missing")
    html = DOC.read_text(encoding="utf-8")

    marker = "function drawProps(){let rows=propsRaw(), p=S(q('fPlayer')?.value,'').toLowerCase(), st=S(q('fStat')?.value,''), si=S(q('fSide')?.value,''), b=S(q('fBook')?.value,''), se=S(q('fSearch')?.value,'').toLowerCase();rows=rows.filter(r=>(!activeGame||r.game===activeGame)&&(!p||String(r.player||'').toLowerCase().includes(p))"
    replacement = "function gameTeams(g){return String(g||'').split(' @ ').map(x=>x.trim()).filter(Boolean)}\nfunction propMatchesGame(r,g){if(!g)return true;let rg=String(r.game||''), rev=gameTeams(g).reverse().join(' @ ');if(rg===g||rg===rev)return true;let teams=gameTeams(g), pt=String(r.player_team||r.team||''), op=String(r.opponent||'');return teams.includes(pt)||teams.includes(op)}\nfunction drawProps(){let rows=propsRaw(), p=S(q('fPlayer')?.value,'').toLowerCase(), st=S(q('fStat')?.value,''), si=S(q('fSide')?.value,''), b=S(q('fBook')?.value,''), se=S(q('fSearch')?.value,'').toLowerCase();rows=rows.filter(r=>propMatchesGame(r,activeGame)&&(!p||String(r.player||'').toLowerCase().includes(p))"
    if marker not in html:
        raise SystemExit("drawProps marker not found")
    html = html.replace(marker, replacement)

    # Make selected game count label use the active game label, even when props are matched by team context.
    html = html.replace(
        "q('propCount').textContent=`Showing ${rows.length} of ${propsRaw().length} props${activeGame?' · '+activeGame:''}`;",
        "q('propCount').textContent=`Showing ${rows.length} of ${propsRaw().length} props${activeGame?' · '+activeGame:''}`;"
    )

    DOC.write_text(html, encoding="utf-8")
    print("Dashboard V4 game prop filtering fixed")


if __name__ == "__main__":
    main()
