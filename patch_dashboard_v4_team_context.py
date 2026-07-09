from __future__ import annotations

from pathlib import Path

DOC = Path("docs/index.html")


def main() -> None:
    if not DOC.exists():
        raise SystemExit("docs/index.html missing")
    html = DOC.read_text(encoding="utf-8")

    html = html.replace(
        ".logo{width:38px;height:38px;border-radius:50%;border:1px solid #2a3b5b;background:#111a2c;display:flex;align-items:center;justify-content:center;font-weight:900;color:#d7e4ff}",
        ".logo{width:38px;height:38px;border-radius:50%;border:1px solid #2a3b5b;background:#111a2c;display:flex;align-items:center;justify-content:center;font-weight:900;color:#d7e4ff;overflow:hidden}.logo img{width:100%;height:100%;object-fit:contain;padding:3px}"
    )
    html = html.replace(
        "function teamFor(r){let parts=String(r.game||'').split(' @ ');return parts[(String(r.player||'').length)%2]||parts[0]||''} function oppFor(r,t){let parts=String(r.game||'').split(' @ ');return parts.find(x=>x!==t)||parts[0]||''}",
        "function teamFor(r){return r.player_team||r.team||String(r.game||'').split(' @ ')[0]||''} function oppFor(r,t){return r.opponent||String(r.game||'').split(' @ ').find(x=>x!==t)||''}"
    )
    html = html.replace(
        "<div class=\"logo mono\">${E(abbr(team).slice(0,2)||String(r.player||'?').slice(0,2))}</div>",
        "<div class=\"logo mono\">${r.team_logo?`<img src=\"${E(r.team_logo)}\" alt=\"${E(abbr(team))}\">`:E(abbr(team).slice(0,2)||String(r.player||'?').slice(0,2))}</div>"
    )
    html = html.replace(
        "let team=teamFor(r), opp=abbr(oppFor(r,team)), side=S(r.signal||r.side,'OVER')",
        "let team=teamFor(r), opp=S(r.opponent_abbr||abbr(oppFor(r,team))), side=S(r.signal||r.side,'OVER')"
    )
    DOC.write_text(html, encoding="utf-8")
    print("Dashboard V4 team context patch applied")


if __name__ == "__main__":
    main()
