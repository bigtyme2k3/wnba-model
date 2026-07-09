from __future__ import annotations

from pathlib import Path

DOC = Path("docs/index.html")


def main() -> None:
    if not DOC.exists():
        raise SystemExit("docs/index.html missing")
    html = DOC.read_text(encoding="utf-8")

    # Only show actual today games as game chips. Do not add stale prop-market games.
    html = html.replace(
        "function propsRaw(){return A(DATA.master?.props)} function gamesList(){return [...new Set(A(DATA.today_games).map(game).concat(propsRaw().map(p=>p.game)).filter(Boolean))]}",
        "function propsRaw(){return A(DATA.master?.props)} function gamesList(){return [...new Set(A(DATA.today_games).map(game).filter(Boolean))]}"
    )

    # Make the prop grid fit better on tablet/desktop and switch to card rows on narrower screens.
    html = html.replace(
        ".propHead,.propRow{display:grid;grid-template-columns:270px 90px 85px 95px 95px 330px 95px 95px 90px;gap:14px;align-items:center;min-width:1240px}",
        ".propHead,.propRow{display:grid;grid-template-columns:minmax(210px,1.45fr) 60px 65px 72px 72px minmax(250px,1.15fr) 70px 70px 54px;gap:10px;align-items:center;min-width:0}"
    )
    html = html.replace(".propScroll{overflow:auto;border:1px solid var(--line);border-radius:18px}", ".propScroll{overflow:auto;border:1px solid var(--line);border-radius:18px;width:100%}")
    html = html.replace(".propRow{padding:20px 16px;border-top:1px solid #151f31;min-height:104px}", ".propRow{padding:16px;border-top:1px solid #151f31;min-height:94px}")
    html = html.replace(".box{width:44px;height:46px;", ".box{width:38px;height:42px;")
    html = html.replace(".num{font-size:18px;", ".num{font-size:16px;")
    html = html.replace(".lineVal{font-size:22px;", ".lineVal{font-size:18px;")
    html = html.replace(".stat{font-size:20px;", ".stat{font-size:18px;")
    html = html.replace(".odds{font-size:17px;", ".odds{font-size:15px;")
    html = html.replace(".hit .pct{font-size:20px}", ".hit .pct{font-size:16px}")

    mobile_css = """
@media(max-width:980px){
 .section{padding:14px}.tools{grid-template-columns:1fr 1fr}.propScroll{border:0;overflow:visible}.propHead{display:none}.propRow{min-width:0;display:grid;grid-template-columns:1fr;gap:10px;background:#08101c;border:1px solid var(--line);border-radius:16px;margin:10px 0;padding:14px}.propRow>*{min-width:0}.propRow .stat:before{content:'Stat ';color:#66748d;font-size:11px}.propRow .lineVal:before{content:'Line ';color:#66748d;font-size:11px}.propRow .odds:before{color:#66748d;font-size:11px}.propRow .odds:nth-child(4):before{content:'Over '}.propRow .odds:nth-child(5):before{content:'Under '}.boxes{flex-wrap:wrap}.hist{align-items:flex-start}.hit{text-align:left;display:inline-block;margin-right:16px}.propRow .small:before{content:'Match ';color:#66748d}.logo{width:34px;height:34px}.name{font-size:15px}.gameChips{padding-bottom:4px}
}
@media(min-width:981px){.propRow .player{overflow:hidden}.name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.team{white-space:nowrap}.boxes{flex-wrap:nowrap}}
"""
    html = html.replace("</style><script>const DATA=__DATA__;</script>", mobile_css + "\n</style><script>const DATA=__DATA__;</script>")

    # Filtering: when a prop came from a stale fallback and was mapped to no active game, keep it in All Games only.
    html = html.replace(
        "rows=rows.filter(r=>(!activeGame||r.game===activeGame)&&(!p||String(r.player||'').toLowerCase().includes(p))",
        "rows=rows.filter(r=>(!activeGame||r.game===activeGame)&&(!p||String(r.player||'').toLowerCase().includes(p))"
    )

    DOC.write_text(html, encoding="utf-8")
    print("Dashboard V4 layout/slate chip patch applied")


if __name__ == "__main__":
    main()
