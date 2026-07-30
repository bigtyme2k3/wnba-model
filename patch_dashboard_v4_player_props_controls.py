from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/index.html")
SCRIPT_ID = "v4-player-props-controls-fix-script"

SCRIPT = r'''<script id="v4-player-props-controls-fix-script">
(function(){
  const EXCLUDED_STATS=new Set(['DD']);
  const CITY={
    'atlanta dream':'ATL','dream':'ATL','chicago sky':'CHI','sky':'CHI',
    'connecticut sun':'CON','sun':'CON','dallas wings':'DAL','wings':'DAL',
    'golden state valkyries':'GSV','valkyries':'GSV','indiana fever':'IND','fever':'IND',
    'las vegas aces':'LVA','aces':'LVA','los angeles sparks':'LAS','sparks':'LAS',
    'minnesota lynx':'MIN','lynx':'MIN','new york liberty':'NYL','liberty':'NYL',
    'phoenix mercury':'PHX','mercury':'PHX','seattle storm':'SEA','storm':'SEA',
    'toronto tempo':'TOR','tempo':'TOR','washington mystics':'WAS','mystics':'WAS'
  };
  const city=v=>{const s=String(v||'').trim();return CITY[s.toLowerCase()]||s.toUpperCase().replace(/[^A-Z]/g,'').slice(0,3)||'-'};
  function cleanProps(){
    try{
      if(typeof DATA!=='undefined'&&DATA?.master&&Array.isArray(DATA.master.props)){
        DATA.master.props=DATA.master.props.filter(r=>!EXCLUDED_STATS.has(String(r?.stat||'').toUpperCase()));
      }
      if(window.DATA?.master&&Array.isArray(window.DATA.master.props)){
        window.DATA.master.props=window.DATA.master.props.filter(r=>!EXCLUDED_STATS.has(String(r?.stat||'').toUpperCase()));
      }
    }catch(err){console.warn('Player Props cleanup failed',err)}
  }
  cleanProps();

  const originalActual=typeof window.actualHistory==='function'?window.actualHistory:null;
  if(originalActual&&!originalActual.__cityWrapped){
    const wrapped=function(r,n){return (originalActual(r,n)||[]).map(x=>Object.assign({},x,{opponent_abbr:city(x?.opponent_abbr||x?.opponent||x?.team)}))};
    wrapped.__cityWrapped=true;
    window.actualHistory=wrapped;
  }

  function redrawLegacy(){
    cleanProps();
    if(typeof window.drawProps==='function')window.drawProps();
  }
  function redrawFlagship(){
    cleanProps();
    const root=document.getElementById('root');
    if(root&&typeof window.props==='function')root.innerHTML=window.props();
  }
  function wire(){
    ['fPlayer','fStat','fSide','fBook','fSearch'].forEach(id=>{
      const el=document.getElementById(id);
      if(!el||el.dataset.controlsFixed)return;
      el.dataset.controlsFixed='1';
      el.addEventListener(id==='fSearch'?'input':'change',redrawLegacy);
    });
  }
  document.addEventListener('input',e=>{
    if(e.target?.matches?.('#pxSearch'))setTimeout(redrawFlagship,0);
    if(e.target?.matches?.('#fSearch'))setTimeout(redrawLegacy,0);
  },true);
  document.addEventListener('change',e=>{
    if(e.target?.matches?.('#pxStat,#pxSide,#pxBook,#pxGame'))setTimeout(redrawFlagship,0);
    if(e.target?.matches?.('#fPlayer,#fStat,#fSide,#fBook'))setTimeout(redrawLegacy,0);
  },true);
  document.addEventListener('click',e=>{
    if(e.target?.closest?.('.tab'))setTimeout(wire,20);
  },true);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{wire();cleanProps()},{once:true});
  else setTimeout(()=>{wire();cleanProps()},0);
  window.WNBA_PLAYER_PROPS_CONTROLS={cleanProps,city,wire,version:'1.1'};
})();
</script>'''


def replace_block(html: str, marker: str, replacement: str) -> str:
    start = html.find(f'<script id="{marker}">')
    if start < 0:
        return html
    end = html.find('</script>', start)
    if end < 0:
        return html
    return html[:start] + replacement + html[end + len('</script>'):]


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding='utf-8')
    if f'id="{SCRIPT_ID}"' in html:
        html = replace_block(html, SCRIPT_ID, SCRIPT)
    else:
        html = html.replace('</body>', SCRIPT + '\n</body>', 1)
    DASHBOARD.write_text(html, encoding='utf-8')
    print('Player Props controls repaired; DD removed; history labels normalized')


if __name__ == '__main__':
    main()
