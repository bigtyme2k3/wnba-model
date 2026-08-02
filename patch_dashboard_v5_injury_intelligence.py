from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html')
DATA=Path('data/dashboard/wnba_injury_intelligence.json')

STYLE='''<style id="v5-injury-intelligence-style">
.injuryGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.injuryCard{border:1px solid #263854;border-radius:16px;padding:16px;background:#091321}.injuryRow{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid #1c2a40}.injuryRow:last-child{border-bottom:0}.injuryBadge{border-radius:999px;padding:5px 9px;font-size:11px;font-weight:800}.injury-out{color:#ff7188;border:1px solid #7b2639;background:#260d16}.injury-questionable{color:#ffd06b;border:1px solid #70551f;background:#241b08}.injury-beneficiary{color:#3de6b0;border:1px solid #17634e;background:#082019}.injury-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0}.injury-kpi{border:1px solid #263854;border-radius:14px;padding:14px;background:#08111f}.injury-kpi b{display:block;font-size:25px;margin-top:5px}.injuryDelta{font-weight:800}.injury-source{font-size:11px;color:#8392ad}.injuryFresh{color:#3de6b0}.injuryAging{color:#ffd06b}.injuryStale{color:#ff7188}.injuryLeaderGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:14px 0}.injuryImpact{border:1px solid #263854;border-radius:16px;padding:16px;background:#08111f}.injuryImpact h3{margin-top:0}.impactBar{height:7px;border-radius:999px;background:#101d31;overflow:hidden;margin-top:8px}.impactBar span{display:block;height:100%;background:currentColor}.impact-high{color:#ff7188}.impact-med{color:#ffd06b}.impact-low{color:#3de6b0}.injuryMetric{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid #1c2a40}.injuryMetric:last-child{border-bottom:0}.injuryNote{border:1px solid #263854;border-radius:14px;padding:12px;margin:12px 0;background:#07101d}.injuryUp{color:#3de6b0;font-weight:800}
</style>'''

SCRIPT='''<script id="v5-injury-intelligence-script">(function(){
const D=window.WNBA_INJURY_DATA||{};const arr=v=>Array.isArray(v)?v:[];const esc=v=>window.E?window.E(v):String(v??'');const num=v=>{const n=Number(v);return Number.isFinite(n)?n:0};
function badge(s){s=String(s||'UNKNOWN').toUpperCase();const c=s==='OUT'||s==='DOUBTFUL'?'injury-out':s==='QUESTIONABLE'?'injury-questionable':'injury-beneficiary';return `<span class="injuryBadge ${c}">${esc(s)}</span>`}
function ageMinutes(){const t=Date.parse(D.generated_at_utc||'');if(!Number.isFinite(t))return num(D.freshness_minutes||999);return Math.max(0,Math.round((Date.now()-t)/60000))}
function freshness(){const m=ageMinutes();if(m<=30)return {label:'FRESH',cls:'injuryFresh',note:'Current enough for active decisions'};if(m<=90)return {label:'AGING',cls:'injuryAging',note:'Refresh before final bet lock'};return {label:'STALE',cls:'injuryStale',note:'Do not trust final availability until refreshed'}}
function impactClass(level){level=String(level||'LOW').toUpperCase();return level==='HIGH'?'impact-high':level==='MED'?'impact-med':'impact-low'}
function impactWidth(row){return Math.min(100,Math.max(8,num(row.missing_minutes)/60*100))}
window.injuryIntelligence=function(){
 const injuries=arr(D.injuries),adj=arr(D.adjustments),impacts=arr(D.team_impacts);const out=injuries.filter(x=>['OUT','DOUBTFUL'].includes(String(x.severity||'').toUpperCase()));const q=injuries.filter(x=>String(x.severity||'').toUpperCase()==='QUESTIONABLE');const boosts=adj.filter(x=>String(x.severity||'').toUpperCase()==='BENEFICIARY').sort((a,b)=>num(b.minutes_delta)-num(a.minutes_delta));const usage=boosts.slice().sort((a,b)=>num(b.usage_delta)-num(a.usage_delta));const teams=[...new Set([...(D.teams||[]),...injuries.map(x=>x.team)])];const f=freshness();
 return `<div class="section"><h2 class="mono">Injury Intelligence</h2><div class="small mono">Official availability, minutes redistribution and projection impact for ${esc(D.target_date||'current slate')}.</div>
 <div class="injury-kpis"><div class="injury-kpi"><span class="small mono">Feed status</span><b class="${f.cls}">${f.label}</b><span class="small mono">${ageMinutes()} min · ${f.note}</span></div><div class="injury-kpi"><span class="small mono">Out / doubtful</span><b>${out.length}</b></div><div class="injury-kpi"><span class="small mono">Questionable</span><b>${q.length}</b></div><div class="injury-kpi"><span class="small mono">Minutes boosts</span><b>${boosts.length}</b></div></div>
 <div class="injuryLeaderGrid"><div class="injuryImpact"><h3 class="mono">Biggest Injury Winners</h3>${boosts.slice(0,8).map((x,i)=>`<div class="injuryMetric"><div><b>${i+1}. ${esc(x.player)}</b><div class="injury-source">${esc(x.team)} · ${esc(x.base_minutes)} → ${esc(x.projected_minutes)} min</div></div><div class="injuryUp">+${num(x.minutes_delta).toFixed(1)}</div></div>`).join('')||'<div class="small mono">No verified beneficiaries.</div>'}</div><div class="injuryImpact"><h3 class="mono">Largest Usage Boosts</h3>${usage.slice(0,8).map((x,i)=>`<div class="injuryMetric"><div><b>${i+1}. ${esc(x.player)}</b><div class="injury-source">${esc(x.team)} · projection factor ${num(x.projection_factor).toFixed(3)}</div></div><div class="injuryUp">+${num(x.usage_delta).toFixed(1)}%</div></div>`).join('')||'<div class="small mono">No verified usage redistribution.</div>'}</div></div>
 ${impacts.length?`<div class="injuryLeaderGrid">${impacts.sort((a,b)=>num(b.missing_minutes)-num(a.missing_minutes)).map(x=>`<div class="injuryImpact ${impactClass(x.impact_level)}"><h3>${esc(x.team)}</h3><div class="injuryMetric"><span>Impact level</span><b>${esc(x.impact_level)}</b></div><div class="injuryMetric"><span>Missing minutes</span><b>${num(x.missing_minutes).toFixed(1)}</b></div><div class="injuryMetric"><span>Minutes reallocated</span><b>${num(x.minutes_reallocated).toFixed(1)}</b></div><div class="injuryMetric"><span>Listed injuries</span><b>${num(x.injuries)}</b></div><div class="impactBar"><span style="width:${impactWidth(x)}%"></span></div></div>`).join('')}</div>`:''}
 <div class="injuryGrid">${teams.map(team=>{const rows=injuries.filter(x=>x.team===team);const b=boosts.filter(x=>x.team===team).slice(0,6);return `<div class="injuryCard"><h3>${esc(team)}</h3>${rows.length?rows.map(x=>`<div class="injuryRow"><div><b>${esc(x.player)}</b><div class="injury-source">${esc(x.injury_type||x.detail||'')}</div></div>${badge(x.severity||x.status)}</div>`).join(''):'<div class="small mono">No listed injuries.</div>'}${b.length?`<h4 class="mono">Minutes redistribution</h4>${b.map(x=>`<div class="injuryRow"><div><b>${esc(x.player)}</b><div class="injury-source">${esc(x.base_minutes)} → ${esc(x.projected_minutes)} min · usage +${num(x.usage_delta).toFixed(1)}%</div></div><div class="injuryDelta">+${num(x.minutes_delta).toFixed(1)}</div></div>`).join('')}`:''}</div>`}).join('')}</div><div class="small mono" style="margin-top:14px">Source: ${esc((injuries[0]||{}).source||'verified injury feed')} · Generated ${esc(D.generated_at_utc||'')}</div></div>`};
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
    print({'injuries':len(payload.get('injuries',[])),'adjustments':len(payload.get('adjustments',[])),'team_impacts':len(payload.get('team_impacts',[]))})

if __name__=='__main__': main()
