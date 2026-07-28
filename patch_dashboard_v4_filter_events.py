from __future__ import annotations

from pathlib import Path

DOC = Path("docs/index.html")
MARKER = "/* Sprint 25 Phase 1: working Player Props filters */"

SCRIPT = r'''
/* Sprint 25 Phase 1: working Player Props filters */
function wirePropFilters(){
  if(window.__wnbaPropFiltersWired)return;
  window.__wnbaPropFiltersWired=true;
  const ids=new Set(['fPlayer','fStat','fBook','fSide','fSearch','fConfidence','fTime','fTeam','fOdds']);
  const refresh=(event)=>{
    const target=event.target;
    if(!target||!ids.has(target.id))return;
    if(typeof drawProps==='function')drawProps();
  };
  document.addEventListener('input',refresh,true);
  document.addEventListener('change',refresh,true);
  document.addEventListener('keyup',(event)=>{
    if(event.key==='Escape'&&event.target&&ids.has(event.target.id)){
      event.target.value='';
      if(typeof drawProps==='function')drawProps();
    }
  },true);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wirePropFilters);
else wirePropFilters();
'''


def main() -> None:
    if not DOC.exists():
        raise SystemExit("docs/index.html missing")
    html = DOC.read_text(encoding="utf-8")
    if MARKER in html:
        print("Player Props filter wiring already present")
        return
    closing = html.rfind("</script>")
    if closing < 0:
        raise SystemExit("dashboard script closing tag not found")
    html = html[:closing] + "\n" + SCRIPT + "\n" + html[closing:]
    DOC.write_text(html, encoding="utf-8")
    print("Dashboard V4 Player Props filters wired")


if __name__ == "__main__":
    main()
