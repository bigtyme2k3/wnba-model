"""Render prospective Player Prop Action Policy v2 evidence in Data Health."""
from __future__ import annotations
import json,re
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_v5_player_prop_action_policy_v2.json')
STYLE_ID='v5-player-prop-shadow-monitor-style'
SCRIPT_ID='v5-player-prop-shadow-monitor-script'
STYLE=r'''<style id="v5-player-prop-shadow-monitor-style">
.v5psm{margin:0 0 18px;border:1px solid #263854;border-radius:16px;background:#08111f;padding:14px}.v5psmHead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.v5psmTitle{font-size:18px;font-weight:900}.v5psmSub{font-size:11px;color:#8fa0bb;margin-top:4px}.v5psmState{border:1px solid #355071;border-radius:999px;padding:5px 9px;font-size:11px;font-weight:900}.v5psmGrid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px;margin:12px 0}.v5psmCard{border:1px solid #20304b;border-radius:13px;padding:10px;background:#091321}.v5psmCard b{display:block;font-size:19px;margin-top:4px}.v5psmBar{height:9px;border-radius:99px;background:#15243a;overflow:hidden}.v5psmFill{height:100%;background:#34d399}.v5psmPolicy{color:#8fa0bb;font-size:11px;margin-top:9px}.v5psmReady{color:#34d399}.v5psmWait{color:#ffd166}@media(max-width:900px){.v5psmGrid{grid-template-columns:repeat(3,1fr)}}@media(max-width:560px){.v5psmGrid{grid-template-columns:repeat(2,1fr)}.v5psmHead{flex-direction:column}}
</style>'''

def build_script(p):
    blob=json.dumps(p,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('</','<\\/')
    return f'''<script id="{SCRIPT_ID}">(function(){{const P={blob};window.WNBA_V5_PLAYER_PROP_SHADOW=P;const prior=window.health;const e=v=>typeof window.E==='function'?window.E(v):String(v??'');const pct=v=>v==null?'—':(Number(v)*100).toFixed(1)+'%';function panel(){{const x=P.prospective||{{}},goal=Number(x.minimum_resolved_for_review||60),n=Number(x.decisions||0),progress=Math.min(100,goal?100*n/goal:0),ready=!!x.ready_for_human_review;return `<div class="v5psm"><div class="v5psmHead"><div><div class="v5psmTitle mono">Player Props · Shadow Action Policy v2</div><div class="v5psmSub mono">Prospective evidence only · production BET/WATCH routing unchanged</div></div><div class="v5psmState mono ${{ready?'v5psmReady':'v5psmWait'}}">${{ready?'REVIEW READY':'ACCUMULATING'}}</div></div><div class="v5psmGrid"><div class="v5psmCard"><span class="label mono">Shadow Bets</span><b>${{e(x.rows||0)}}</b></div><div class="v5psmCard"><span class="label mono">Resolved W-L</span><b>${{e(x.wins||0)}}-${{e(x.losses||0)}}</b></div><div class="v5psmCard"><span class="label mono">Hit Rate</span><b>${{pct(x.hit_rate)}}</b></div><div class="v5psmCard"><span class="label mono">Units</span><b>${{Number(x.profit_units||0).toFixed(2)}}u</b></div><div class="v5psmCard"><span class="label mono">ROI</span><b>${{pct(x.roi)}}</b></div><div class="v5psmCard"><span class="label mono">Pending</span><b>${{e(x.pending||0)}}</b></div></div><div class="v5psmSub mono">Promotion evidence: ${{n}} / ${{goal}} resolved decisions</div><div class="v5psmBar"><div class="v5psmFill" style="width:${{progress.toFixed(1)}}%"></div></div><div class="v5psmPolicy mono">Gate: at least ${{goal}} resolved decisions + positive prospective ROI. Historical support is diagnostic only; no automatic promotion.</div></div>`}}window.health=function(){{let old='';try{{if(typeof prior==='function')old=prior()||''}}catch(_){{}}return panel()+old}};}})();</script>'''

def inject(html,tag,id_,block,anchor):
    pat=rf'<{tag} id="{re.escape(id_)}"[^>]*>.*?</{tag}>'
    if re.search(pat,html,flags=re.S):return re.sub(pat,block,html,count=1,flags=re.S)
    i=html.lower().rfind(anchor.lower())
    return html[:i]+block+'\n'+html[i:] if i>=0 else html+'\n'+block

def main():
    if not HTML.exists(): raise SystemExit('docs/index.html missing')
    if not DATA.exists():
        print('Player prop shadow artifact unavailable; monitor skipped');return
    p=json.loads(DATA.read_text(encoding='utf-8'))
    h=HTML.read_text(encoding='utf-8',errors='replace')
    h=inject(h,'style',STYLE_ID,STYLE,'</head>')
    h=inject(h,'script',SCRIPT_ID,build_script(p),'</body>')
    HTML.write_text(h,encoding='utf-8')
    x=p.get('prospective') or {}
    print({'status':'PASS','shadow_rows':x.get('rows',0),'decisions':x.get('decisions',0),'roi':x.get('roi'),'ready':x.get('ready_for_human_review',False)})
if __name__=='__main__':main()
