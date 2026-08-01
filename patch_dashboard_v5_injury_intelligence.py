from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_injury_intelligence.json')

STYLE='''<style id="v5-injury-intelligence-style">
.injuryGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.injuryCard{border:1px solid #263854;border-radius:16px;padding:16px;background:#091321}.injuryRow{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid #1c2a40}.injuryRow:last-child{border-bottom:0}.injuryBadge{border-radius:999px;padding:5px 9px;font-size:11px;font-weight:800}.injury-out{color:#ff7188;border:1px solid #7b2639;background:#260d16}.injury-questionable{color:#ffd06b;border:1px solid #70551f;background:#241b08}.injury-beneficiary{color:#3de6b0;border:1px solid #17634e;background:#082019}.injury-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0}.injury-kpi{border:1px solid #263854;border-radius:14px;padding:14px;background:#08111f}.injury-kpi b{display:block;font-size:25px;margin-top:5px}.injuryDelta{font-weight:800}.injury-source{font-size:11px;color:#8392ad}.injuryFresh{color:#3de6b0}.injuryStale{color:#ff7188}
</style>'''

SCRIPT='''<script id="v5-injury-intelligence-script">(function(){
const D=window.WNBA_INJURY_DATA||{};const arr=v=>Array.isArray(v)?v:[];const esc=v=>window.E?window.E(v):String(v??'');
function badge(s){s=String(s||'UNKNOWN').toUpperCase();const c=s==='OUT'||s==='DOUBTFUL'?'injury-out':s==='QUESTIONABLE'?'injury-questionable':'injury-beneficiary';return `<span class="injuryBadge ${c}">${esc(s)}</span>`}
window.injuryIntelligence=function(){const injuries=arr(D.injuries),adj=arr(D.adjustments);const out=injuries.filter(x=>['OUT','DOUBTFUL'].includes(String(x.severity||'').toUpperCase()));const q=injuries.filter(x=>String(x.severity||'').toUpperCase()==='QUESTIONABLE');const boosts=adj.filter(x=>String(x.severity||'').toUpperCase()==='BENEFICIARY').sort((a,b)=>Number(b.minutes_delta||0)-Number(a.minutes_delta||0));const teams=[...new Set([...(D.teams||[]),...injuries.map(x=>x.team)])];const fresh=Number(D.freshness_minutes||999)<=30;return `<div class="section"><h2 class="mono">Injury Intelligence</h2><div class="small mono">Official availability, minutes redistribution and projection impact for ${esc(D.target_date||'current slate')}.</div><div class="injury-kpis"><div class="injury-kpi"><span class="small mono">Feed status</span><b class="${fresh?'injuryFresh':'injuryStale'}">${fresh?'FRESH':'STALE'}</b><span class="small mono">${esc(D.freshness_minutes)} min</span></div><div class="injury-kpi"><span class="small mono">Out / doubtful</span><b>${out.length}</b></div><div class="injury-kpi"><span class="small mono">Questionable</span><b>${q.length}</b></div><div class="injury-kpi"><span class="small mono">Minutes boosts</span><b>${boosts.length}</b></div></div><div class="injuryGrid">${teams.map(team=>{const rows=injuries.filter(x=>x.team===team);const b=boosts.filter(x=>x.team===team).slice(0,6);return `<div class="injuryCard"><h3>${esc(team)}</h3>${rows.length?rows.map(x=>`<div class="injuryRow"><div><b>${esc(x.player)}</b><div class="injury-source">${esc(x.injury_type||x.detail||'')}</div></div>${badge(x.severity||x.status)}</div>`).join(''):'<div class="small mono">No listed injuries.</div>'}${b.length?`<h4 class="mono">Minutes redistribution</h4>${b.map(x=>`<div class="injuryRow"><div><b>${esc(x.player)}</b><div class="injury-source">${esc(x.base_minutes)} → ${esc(x.projected_minutes)} min</div></div><div class="injuryDelta">+${Number(x.minutes_delta||0).toFixed(1)}</div></div>`).join('')}`:''}</div>`}).join('')}</div><div class="small mono" style="margin-top:14px">Source: ${esc((injuries[0]||{}).source||'verified injury feed')} · Generated ${esc(D.generated_at_utc||'')}</div></div>`};
})();</script>'''

def block_replace(text, start, end, repl):
    i=text.find(start)
    if i<0:return text
    j=text.find(end,i)
    if j<0:return text
    return text[:i]+repl+text[j+len(end):]

def main():
    if not HTML.exists(): raise SystemExit('docs/index.html missing')
    payload=json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
    html=HTML.read_text(encoding='utf-8')
    data='<script id="v5-injury-intelligence-data">window.WNBA_INJURY_DATA='+json.dumps(payload,separators=(',',':'))+';</script>'
    for ident,content in [('v5-injury-intelligence-style',STYLE),('v5-injury-intelligence-data',data),('v5-injury-intelligence-script',SCRIPT)]:
        marker=f'id="{ident}"'
        if marker in html:
            tag='style' if 'style' in ident else 'script'
            html=block_replace(html,f'<{tag} id="{ident}">',f'</{tag}>',content)
        else:
            html=html.replace('</head>',content+'</head>') if ident.endswith('style') else html.replace('</body>',content+'</body>')
    html=html.replace("['market','Market Intelligence'],['mission'", "['market','Market Intelligence'],['injuries','Injuries'],['mission'")
    html=html.replace("else if(view==='market')html=invoke('Market Intelligence',[window.marketIntelligence]);else if(view==='mission')", "else if(view==='market')html=invoke('Market Intelligence',[window.marketIntelligence]);else if(view==='injuries')html=invoke('Injury Intelligence',[window.injuryIntelligence]);else if(view==='mission')")
    HTML.write_text(html,encoding='utf-8')
    print({'injuries':len(payload.get('injuries',[])),'adjustments':len(payload.get('adjustments',[]))})

if __name__=='__main__': main()
