"""Render V5 promotion-readiness gates in the Data Health view."""
from __future__ import annotations
import json,re
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_v5_promotion_readiness.json')
STYLE_ID='v5-promotion-readiness-style'
SCRIPT_ID='v5-promotion-readiness-script'
STYLE=r'''<style id="v5-promotion-readiness-style">
.v5pr{margin:0 0 18px;border:1px solid #263854;border-radius:16px;background:#08111f;padding:14px}.v5prHead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.v5prTitle{font-size:18px;font-weight:900}.v5prSub{font-size:11px;color:#8fa0bb;margin-top:4px}.v5prState{border:1px solid #355071;border-radius:999px;padding:5px 9px;font-size:11px;font-weight:900}.v5prGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0}.v5prCard{border:1px solid #20304b;border-radius:13px;padding:11px;background:#091321}.v5prCard b{display:block;font-size:20px;margin-top:4px}.v5prGate{display:grid;grid-template-columns:1.4fr .7fr .7fr .5fr;gap:8px;padding:9px;border-top:1px solid #1b293e;align-items:center}.v5prGate:first-child{border-top:0}.v5prPass{color:#34d399}.v5prFail{color:#ffd166}.v5prBox{border:1px solid #20304b;border-radius:13px;overflow:hidden}.v5prPolicy{color:#8fa0bb;font-size:11px;margin-top:10px}@media(max-width:820px){.v5prGrid{grid-template-columns:1fr 1fr}.v5prHead{flex-direction:column}.v5prGate{grid-template-columns:1fr .7fr .7fr .4fr;font-size:11px}}
</style>'''

def build_script(p):
    blob=json.dumps(p,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('</','<\\/')
    return f'''<script id="{SCRIPT_ID}">(function(){{const P={blob};window.WNBA_V5_PROMOTION_READINESS=P;const prior=window.health;const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');function panel(){{const c=P.context||{{}},clv=P.clv||{{}},ch=P.challenger||{{}},g=P.gates||[];return `<div class="v5pr"><div class="v5prHead"><div><div class="v5prTitle mono">V5 Promotion Readiness</div><div class="v5prSub mono">Shadow evidence only · no automatic production promotion</div></div><div class="v5prState mono">${{esc(P.status||'—')}}</div></div><div class="v5prGrid"><div class="v5prCard"><span class="label mono">Resolved Context</span><b>${{esc(c.resolved_context_rows||0)}}</b><small>${{esc(c.minimum_promotion_rows||0)}} promotion target</small></div><div class="v5prCard"><span class="label mono">Pending Context</span><b>${{esc(c.pending_context_rows||0)}}</b><small>${{esc(c.captured_context_rows||0)}} captured</small></div><div class="v5prCard"><span class="label mono">Explicit CLV</span><b>${{Number(clv.coverage_pct||0).toFixed(1)}}%</b><small>${{Number(clv.required_pct||0).toFixed(1)}}% required</small></div><div class="v5prCard"><span class="label mono">Best Context Layer</span><b style="font-size:14px">${{esc(ch.best_contextual_group||'NOT SCORED')}}</b><small>n=${{esc(ch.chronologically_scored_rows||0)}}</small></div></div><div class="v5prBox">${{g.map(x=>`<div class="v5prGate"><div><b>${{esc(x.name)}}</b><div class="v5prSub">${{esc(x.detail||'')}}</div></div><div>${{esc(x.current)}}</div><div>${{esc(x.required)}}</div><div class="${{x.pass?'v5prPass':'v5prFail'}}"><b>${{x.pass?'PASS':'WAIT'}}</b></div></div>`).join('')}}</div><div class="v5prPolicy mono">Decision: ${{esc(P.decision||'—')}} · ${{esc(P.policy||'')}}</div></div>`}}window.health=function(){{let old='';try{{if(typeof prior==='function')old=prior()||''}}catch(e){{}}return panel()+old}};}})();</script>'''

def inject(html,tag,id_,block,anchor):
    pat=rf'<{tag} id="{re.escape(id_)}"[^>]*>.*?</{tag}>'
    if re.search(pat,html,flags=re.S):return re.sub(pat,block,html,count=1,flags=re.S)
    i=html.lower().rfind(anchor.lower());return html[:i]+block+'\n'+html[i:] if i>=0 else html+'\n'+block

def main():
    if not HTML.exists(): raise SystemExit('docs/index.html missing')
    if not DATA.exists():
        print('V5 promotion readiness artifact not available yet; renderer skipped');return
    p=json.loads(DATA.read_text(encoding='utf-8'))
    h=HTML.read_text(encoding='utf-8',errors='replace')
    h=inject(h,'style',STYLE_ID,STYLE,'</head>')
    h=inject(h,'script',SCRIPT_ID,build_script(p),'</body>')
    HTML.write_text(h,encoding='utf-8')
    print({'status':'PASS','promotion_status':p.get('status'),'decision':p.get('decision')})
if __name__=='__main__':main()
