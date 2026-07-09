from __future__ import annotations

from pathlib import Path

DOC = Path("docs/index.html")


def main() -> None:
    if not DOC.exists():
        raise SystemExit("docs/index.html not found")
    html = DOC.read_text(encoding="utf-8")

    old_css = ".box{min-width:38px;height:42px;border:1px solid #1d5b3c;background:#0d3327;border-radius:7px;text-align:center;padding-top:4px}.box .num{color:var(--g);font-size:17px;font-weight:900}.box .opp{font-size:9px;color:#778399}"
    new_css = ".box{min-width:38px;height:42px;border:1px solid #1d5b3c;background:#0d3327;border-radius:7px;text-align:center;padding-top:4px}.box.hitBox{border-color:#1d5b3c;background:#0d3327}.box.missBox{border-color:#6b2230;background:#35121c}.box .num{color:var(--g);font-size:17px;font-weight:900}.box.missBox .num{color:var(--r)}.box .opp{font-size:9px;color:#778399}"
    html = html.replace(old_css, new_css)

    old_func = "function propRow(r){let team=playerTeam(r),abbr=abbrTeam(team),opp=oppsForGame(r.game,team),vals5=histVals(r,5),vals10=histVals(r,10),line=S(r.line||r.consensus_line,0),side=S(r.signal||r.side,'OVER'),h5=hitInfo(vals5,line,side),h10=hitInfo(vals10,line,side),over=S(r.best_over_price||r.over_price,'-'),under=S(r.best_under_price||r.under_price,'-');return `"
    new_func = "function boxWin(v,line,side){line=Number(line);let over=side!=='UNDER';return over?v>line:v<line}\nfunction propRow(r){let team=playerTeam(r),abbr=abbrTeam(team),opp=oppsForGame(r.game,team),vals5=histVals(r,5),vals10=histVals(r,10),line=S(r.line||r.consensus_line,0),side=S(r.signal||r.side,'OVER'),h5=hitInfo(vals5,line,side),h10=hitInfo(vals10,line,side),over=S(r.best_over_price||r.over_price,'-'),under=S(r.best_under_price||r.under_price,'-');return `"
    html = html.replace(old_func, new_func)

    old_boxes = "${vals5.map(v=>`<div class=\"box\"><div class=\"num\">${v}</div><div class=\"opp\">${opp}</div></div>`).join('')}"
    new_boxes = "${vals5.map(v=>`<div class=\"box ${boxWin(v,line,side)?'hitBox':'missBox'}\"><div class=\"num\">${v}</div><div class=\"opp\">${opp}</div></div>`).join('')}"
    html = html.replace(old_boxes, new_boxes)

    DOC.write_text(html, encoding="utf-8")
    print("Prop history box colors patched: green hit / red miss")


if __name__ == "__main__":
    main()
