from __future__ import annotations

from pathlib import Path

DOC = Path("docs/index.html")
MARKER = "v4-player-props-filter-events-script"

SCRIPT = r'''<script id="v4-player-props-filter-events-script">
/* Sprint 25 Phase 1: working Player Props filters */
function wirePropFilters(){
  if(window.__wnbaPropFiltersWired)return;
  window.__wnbaPropFiltersWired=true;
  const ids=new Set(['fPlayer','fStat','fBook','fSide','fSearch','fConfidence','fTime','fTeam','fOdds']);
  const refresh=(event)=>{
    const target=event.target;
    if(!target||!ids.has(target.id))return;
    if(typeof window.drawProps==='function')window.drawProps();
  };
  document.addEventListener('input',refresh,true);
  document.addEventListener('change',refresh,true);
  document.addEventListener('keyup',(event)=>{
    if(event.key==='Escape'&&event.target&&ids.has(event.target.id)){
      event.target.value='';
      if(typeof window.drawProps==='function')window.drawProps();
    }
  },true);
}
window.wirePropFilters=wirePropFilters;
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wirePropFilters);
else wirePropFilters();
</script>'''


def replace_block(html: str, start: str, end: str, replacement: str) -> str:
    i = html.find(start)
    if i < 0:
        return html
    j = html.find(end, i)
    if j < 0:
        return html
    return html[:i] + replacement.strip() + html[j + len(end):]


def main() -> None:
    if not DOC.exists():
        raise SystemExit("docs/index.html missing")
    html = DOC.read_text(encoding="utf-8")
    start = '<script id="v4-player-props-filter-events-script">'
    if start in html:
        html = replace_block(html, start, "</script>", SCRIPT)
        print("Player Props filter wiring refreshed")
    else:
        html = html.replace("</body>", SCRIPT + "\n</body>", 1)
        print("Dashboard V4 Player Props filters wired")
    DOC.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
