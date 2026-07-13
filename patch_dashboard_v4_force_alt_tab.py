from __future__ import annotations
from pathlib import Path

HTML=Path('docs/index.html')
SCRIPT=r'''<script id="v4-force-alt-tab-script">(function(){function retire(){const tabs=document.getElementById('tabs');if(!tabs)return;tabs.querySelectorAll('[data-view="alt"]').forEach(button=>button.remove())}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',retire);else retire();setTimeout(retire,0);setTimeout(retire,500);const priorRender=window.render;if(typeof priorRender==='function'&&!priorRender.__altRetired){const wrapped=function(view){return priorRender.call(this,view==='alt'?'props':view)};wrapped.__altRetired=true;window.render=wrapped}})();</script>'''

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
    print('Standalone ALT tab retired; legacy ALT links redirect to Player Props')
if __name__=='__main__':main()
