from __future__ import annotations
from pathlib import Path

HTML=Path('docs/index.html')
SCRIPT=r'''<script id="v4-force-alt-tab-script">(function(){function install(){const tabs=document.getElementById('tabs');if(!tabs)return false;let button=tabs.querySelector('[data-view="alt"]');if(!button){button=document.createElement('button');button.className='tab';button.dataset.view='alt';button.textContent='ALT Streaks';button.onclick=()=>window.render('alt');const all=[...tabs.querySelectorAll('.tab')];const props=all.find(x=>x.dataset.view==='props'||x.textContent.trim()==='Player Props');if(props)props.insertAdjacentElement('afterend',button);else tabs.appendChild(button)}return true}function guard(){install();const tabs=document.getElementById('tabs');if(tabs&&!tabs.dataset.altGuard){tabs.dataset.altGuard='1';new MutationObserver(()=>install()).observe(tabs,{childList:true})}}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',guard);else guard();setTimeout(guard,0);setTimeout(guard,500);const priorRender=window.render;if(typeof priorRender==='function'&&!priorRender.__altGuarded){const wrapped=function(view){const result=priorRender.apply(this,arguments);guard();if(view==='alt'&&typeof window.altStreaks==='function'){const root=document.getElementById('root');if(root)root.innerHTML=window.altStreaks()}return result};wrapped.__altGuarded=true;window.render=wrapped}})();</script>'''

def replace_block(html,start,end,replacement):
    i=html.find(start)
    if i<0:return html
    j=html.find(end,i)
    if j<0:return html
    return html[:i]+replacement.strip()+html[j+len(end):]

def main():
    if not HTML.exists():raise SystemExit('docs/index.html missing')
    html=HTML.read_text(encoding='utf-8')
    if 'id="v4-force-alt-tab-script"' in html:
        html=replace_block(html,'<script id="v4-force-alt-tab-script">','</script>',SCRIPT)
    else:
        html=html.replace('</body>',SCRIPT+'</body>')
    HTML.write_text(html,encoding='utf-8')
    print('Permanent ALT tab navigation guard installed')
if __name__=='__main__':main()
