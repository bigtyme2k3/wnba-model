from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/index.html")
STYLE_ID = "v4-games-simplify-style"
SCRIPT_ID = "v4-games-simplify-script"

STYLE = r'''<style id="v4-games-simplify-style">
/* Games is a small-slate decision page: remove filter chrome and tighten spacing. */
#gamesFilterBar,.gamesFilterBar,.gamesUxFilters,.gamesQuickFilters,.gameFilterMeta{display:none!important}
.gamesSummary{margin-top:0}.bestPlay{margin-top:0}.gameCard{margin-top:12px}
@media(max-width:900px){.gamesSummary{gap:10px}.bestPlay{margin-bottom:14px}.gameCard{padding:14px}.marketGrid{gap:10px}}
</style>'''

SCRIPT = r'''<script id="v4-games-simplify-script">(function(){
function stripGamesFilters(){
  const root=document.getElementById('root');
  if(!root)return;
  const labels=['All Games','Model Bets','Leans','Passes','Large Edges','Player Props'];

  /* Never inspect or hide broad containers such as #root or .section. */
  for(const node of root.querySelectorAll('button,a')){
    const text=(node.textContent||'').replace(/\s+/g,' ').trim();
    if(labels.includes(text))node.style.display='none';
  }

  /* Hide only a compact wrapper whose direct buttons are the Games quick filters. */
  for(const wrapper of root.querySelectorAll('nav,[role="toolbar"],.gamesFilterBar,.gamesUxFilters,.gamesQuickFilters,#gamesFilterBar')){
    const directLabels=[...wrapper.querySelectorAll(':scope > button,:scope > a')]
      .map(node=>(node.textContent||'').replace(/\s+/g,' ').trim());
    if(directLabels.filter(text=>labels.includes(text)).length>=2)wrapper.style.display='none';
  }

  for(const node of root.querySelectorAll('.gameFilterMeta,[data-games-filter-meta]'))node.style.display='none';
  for(const node of root.querySelectorAll('small,span,div')){
    if(node===root||node.contains(root))continue;
    const text=(node.textContent||'').replace(/\s+/g,' ').trim();
    if(/^Showing \d+ of \d+ game cards$/i.test(text)||text==="Tap a matchup's player candidates to expand")node.style.display='none';
  }
}
const previous=window.render;
if(typeof previous==='function'){
  window.render=function(view){
    const out=previous(view);
    if((view||'games')==='games')setTimeout(stripGamesFilters,0);
    return out;
  };
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(stripGamesFilters,0));
else setTimeout(stripGamesFilters,0);
window.addEventListener('load',()=>setTimeout(stripGamesFilters,0),{once:true});
window.WNBA_GAMES_SIMPLIFIED={version:'1.1',filters:false};
})();</script>'''

def replace_block(html: str, start: str, end: str, replacement: str) -> str:
    s = html.find(start)
    if s < 0:
        return html
    e = html.find(end, s)
    if e < 0:
        return html
    return html[:s] + replacement.strip() + html[e + len(end):]


def main() -> None:
    if not DASHBOARD.exists():
        raise SystemExit("docs/index.html missing")
    html = DASHBOARD.read_text(encoding="utf-8")
    if f'id="{STYLE_ID}"' in html:
        html = replace_block(html, f'<style id="{STYLE_ID}">', '</style>', STYLE)
    else:
        html = html.replace('</head>', STYLE + '</head>')
    if f'id="{SCRIPT_ID}"' in html:
        html = replace_block(html, f'<script id="{SCRIPT_ID}">', '</script>', SCRIPT)
    else:
        html = html.replace('</body>', SCRIPT + '</body>')
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Games tab simplified safely: quick filters removed without hiding content")


if __name__ == "__main__":
    main()
