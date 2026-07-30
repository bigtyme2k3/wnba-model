from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/index.html")
SCRIPT_ID = "v4-player-props-interactions-fix"

SCRIPT = r'''<script id="v4-player-props-interactions-fix">
(function(){
  const IDS=['pxSearch','pxStat','pxSide','pxBook','pxGame'];
  const saved=window.WNBA_PROPS_FILTER_STATE||{pxSearch:'',pxStat:'',pxSide:'',pxBook:'',pxGame:''};
  window.WNBA_PROPS_FILTER_STATE=saved;

  function capture(){
    for(const id of IDS){const el=document.getElementById(id);if(el)saved[id]=el.value||'';}
  }
  function restore(){
    for(const id of IDS){const el=document.getElementById(id);if(el)el.value=saved[id]||'';}
  }
  function paint(){
    const root=document.getElementById('root');
    if(!root||typeof window.props!=='function')return;
    root.innerHTML=String(window.props()||'');
    restore();
  }
  function apply(){capture();paint();}

  document.addEventListener('input',function(event){
    const target=event.target;
    if(!target||!IDS.includes(target.id))return;
    saved[target.id]=target.value||'';
    requestAnimationFrame(paint);
  },true);

  document.addEventListener('change',function(event){
    const target=event.target;
    if(!target||!IDS.includes(target.id))return;
    saved[target.id]=target.value||'';
    event.preventDefault();
    event.stopImmediatePropagation();
    requestAnimationFrame(paint);
  },true);

  document.addEventListener('click',function(event){
    const button=event.target.closest('.propsUxChip,.propsUxClear,.propsUxHead button');
    if(!button)return;
    event.preventDefault();
    event.stopImmediatePropagation();
    capture();

    if(button.classList.contains('propsUxClear')){
      for(const id of IDS)saved[id]='';
      if(window.PLAYER_PROPS_UX_STATE){window.PLAYER_PROPS_UX_STATE.quick='';}
      if(typeof window.clearPropsUx==='function')window.clearPropsUx();
      requestAnimationFrame(paint);
      return;
    }

    const handler=button.getAttribute('onclick')||'';
    if(button.classList.contains('propsUxChip')){
      const match=handler.match(/setPropsQuick\(['\"]([^'\"]+)['\"]\)/);
      if(match&&typeof window.setPropsQuick==='function')window.setPropsQuick(match[1]);
      requestAnimationFrame(paint);
      return;
    }

    const match=handler.match(/setPropsUxSort\(['\"]([^'\"]+)['\"]\)/);
    if(match&&typeof window.setPropsUxSort==='function')window.setPropsUxSort(match[1]);
    requestAnimationFrame(paint);
  },true);

  const observer=new MutationObserver(function(){if(document.getElementById('pxSearch'))restore();});
  observer.observe(document.documentElement,{subtree:true,childList:true});
  restore();
  window.PLAYER_PROPS_INTERACTIONS={version:'2.0',capture,restore,paint,apply};
})();
</script>'''


def replace_or_insert(html: str) -> str:
    start = html.find(f'<script id="{SCRIPT_ID}">')
    if start >= 0:
        end = html.find('</script>', start)
        if end >= 0:
            return html[:start] + SCRIPT + html[end + len('</script>'):]
    return html.replace('</body>', SCRIPT + '\n</body>', 1)


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding='utf-8')
    DASHBOARD.write_text(replace_or_insert(html), encoding='utf-8')
    print('Player Props filters and quick actions repaired v2')


if __name__ == '__main__':
    main()
