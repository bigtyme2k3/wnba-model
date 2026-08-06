from __future__ import annotations

import re
from pathlib import Path

HTML = Path('docs/index.html')
MARKER = 'v5-injury-navigation-runtime'

RUNTIME = r'''<script id="v5-injury-navigation-runtime">
(function(){
  function renderInjuries(){
    const root=document.getElementById('root')||document.querySelector('[data-dashboard-root]')||document.querySelector('main');
    if(!root||typeof window.injuryIntelligence!=='function') return false;
    root.innerHTML=window.injuryIntelligence();
    document.querySelectorAll('[data-injury-runtime-tab],.tab.active,.nav-tab.active').forEach(el=>el.classList.remove('active'));
    const btn=document.querySelector('[data-injury-runtime-tab]');
    if(btn) btn.classList.add('active');
    try{history.replaceState(null,'','#injuries')}catch(_e){}
    return true;
  }
  function install(){
    if(document.querySelector('[data-injury-runtime-tab]')) return true;
    const candidates=[...document.querySelectorAll('nav,.tabs,.tabbar,.nav-tabs,[role="tablist"],header div')]
      .filter(el=>el.querySelector('button,a,[role="tab"]'));
    const nav=candidates.find(el=>/Games|Player Props|Best Bets|Results|AI Center/.test(el.textContent||''));
    if(!nav) return false;
    const sample=nav.querySelector('button,a,[role="tab"]');
    const btn=document.createElement(sample&&sample.tagName==='A'?'a':'button');
    if(sample) btn.className=sample.className;
    btn.textContent='Injuries';
    btn.setAttribute('data-injury-runtime-tab','1');
    btn.setAttribute('type','button');
    btn.addEventListener('click',function(ev){ev.preventDefault();renderInjuries();});
    nav.appendChild(btn);
    if(location.hash==='#injuries') setTimeout(renderInjuries,0);
    return true;
  }
  window.WNBA_INJURY_RUNTIME_NAV={install:install,render:renderInjuries};
  if(!install()){
    const obs=new MutationObserver(function(){if(install())obs.disconnect();});
    obs.observe(document.documentElement,{childList:true,subtree:true});
    setTimeout(function(){obs.disconnect();install();},5000);
  }
})();
</script>'''


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    html = HTML.read_text(encoding='utf-8')
    html = re.sub(rf'<script id="{MARKER}">.*?</script>', '', html, flags=re.S)
    if '</body>' in html:
        html = html.replace('</body>', RUNTIME + '</body>', 1)
    else:
        html += RUNTIME
    HTML.write_text(html, encoding='utf-8')
    check = HTML.read_text(encoding='utf-8')
    required = [MARKER, 'data-injury-runtime-tab', 'window.WNBA_INJURY_RUNTIME_NAV', 'renderInjuries']
    missing = [x for x in required if x not in check]
    if missing:
        raise SystemExit('Injury runtime navigation verification failed: ' + ', '.join(missing))
    print('Router-independent Injury Intelligence runtime navigation installed')


if __name__ == '__main__':
    main()
