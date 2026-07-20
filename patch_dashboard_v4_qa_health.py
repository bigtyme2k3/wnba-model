from __future__ import annotations
from pathlib import Path
PATH=Path('docs/index.html')
CSS=r'''<style id="v4-qa-health-style">
.healthKpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:16px 0}.healthKpi{background:#08101c;border:1px solid #1e2a43;border-radius:16px;padding:15px}.healthKpi .v{font-size:27px;font-weight:900;margin-top:6px}.qa-green{color:#00e39b}.qa-blue{color:#80a8ff}.qa-yellow{color:#ffd166}.qa-red{color:#ff4d67}.qa-unknown{color:#7e8ba3}.qaPill{display:inline-flex;border:1px solid currentColor;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:900;text-transform:uppercase}.readyYes{color:#00e39b}.readyNo{color:#7e8ba3}.healthTableWrap{overflow:auto;border:1px solid #1e2a43;border-radius:16px;margin-top:14px}.healthTable{min-width:1220px}.healthTable tr.health-blue{background:rgba(128,168,255,.045)}.healthTable tr.health-yellow{background:rgba(255,209,102,.045)}.healthTable tr.health-red{background:rgba(255,77,103,.055)}.issueList{margin:4px 0;padding-left:17px;color:#ff7f91}.warnList{margin:4px 0;padding-left:17px;color:#ffe09a}.qaMeta{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.qaSummary{background:#07101d;border:1px solid #1e2a43;border-radius:14px;padding:12px;margin-top:12px}.qaSummary code{white-space:pre-wrap;color:#a9b9d8}.healthEmpty{color:#7e8ba3;padding:14px 0}.issueNone{color:#6f7d94;font-size:12px}.issueCell{min-width:260px;max-width:390px}.freshCell{min-width:185px}.healthMessage{margin-top:4px;color:#93a0b8;font-size:11px;line-height:1.35}.legend{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.legend span{display:inline-flex;gap:6px;align-items:center;font-size:11px;color:#aab7cf}.legend i{width:9px;height:9px;border-radius:50%;display:inline-block}.legend .g{background:#00e39b}.legend .b{background:#80a8ff}.legend .y{background:#ffd166}.legend .r{background:#ff4d67}@media(max-width:900px){.healthKpis{grid-template-columns:1fr 1fr}.healthKpi:last-child{grid-column:1/-1}}
</style>'''
SCRIPT=r'''<script id="v4-qa-health-script">
(function(){
 const esc=v=>typeof E==='function'?E(v):String(v??'');const arr=v=>Array.isArray(v)?v:[];const val=(v,d='-')=>v===undefined||v===null||v===''?d:v;
 const cls=g=>['green','blue','yellow','red'].includes(String(g))?'qa-'+g:'qa-unknown';
 const pill=g=>`<span class="qaPill ${cls(g)}">${esc(val(g,'unknown'))}</span>`;
 const ago=m=>{if(m===undefined||m===null)return 'Unknown';m=Number(m);if(m<60)return `${Math.round(m)} min ago`;if(m<1440)return `${(m/60).toFixed(1)} hr ago`;return `${(m/1440).toFixed(1)} days ago`};
 const issues=(b,w)=>{b=arr(b);w=arr(w);if(!b.length&&!w.length)return '<span class="issueNone mono">None</span>';return `${b.length?`<ul class="issueList">${b.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${w.length?`<ul class="warnList">${w.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}`};
 window.health=function(){
  const v=DATA.v4||{},s=v.summary||{},qa=v.qa||{},mods=arr(v.modules),hc=s.health_state_counts||{},qac=s.qa_status_counts||{};
  const cards=`<div class="healthKpis"><div class="healthKpi"><div class="label mono">Overall QA</div><div class="v mono ${cls(qa.overall_status)}">${esc(String(qa.overall_status||'unknown').toUpperCase())}</div></div><div class="healthKpi"><div class="label mono">Green</div><div class="v mono qa-green">${esc(val(hc.green,0))}</div></div><div class="healthKpi"><div class="label mono">Valid No-op</div><div class="v mono qa-blue">${esc(val(hc.blue,0))}</div></div><div class="healthKpi"><div class="label mono">Needs Attention</div><div class="v mono qa-yellow">${esc(val(hc.yellow,0))}</div></div><div class="healthKpi"><div class="label mono">Failed</div><div class="v mono qa-red">${esc(val(hc.red,0))}</div></div></div>`;
  const legend=`<div class="legend"><span><i class="g"></i>Active and fresh</span><span><i class="b"></i>Valid no-op / no qualifying rows</span><span><i class="y"></i>Stale or unexpectedly empty</span><span><i class="r"></i>Missing or failed</span></div>`;
  const rows=mods.map(m=>`<tr class="health-${esc(m.health_state||'unknown')}"><td>${esc(m.id)}</td><td><b>${esc(m.name)}</b><div class="small mono">${esc(val(m.owner_file))}</div></td><td>${pill(m.health_state)}</td><td>${esc(val(m.runtime_status))}</td><td class="mono">${esc(val(m.rows,0))}</td><td class="freshCell"><div class="mono">${esc(ago(m.age_minutes))}</div><div class="small mono">${esc(val(m.last_updated_utc,'No timestamp'))}</div></td><td><div>${esc(val(m.health_message))}</div><div class="healthMessage">${m.valid_zero_output?'Zero rows are expected for the current slate.':'Output is expected when the module has work to process.'}</div></td><td>${issues(m.blockers,m.warnings)}</td></tr>`).join('');
  const table=`<div class="healthTableWrap"><table class="healthTable"><thead><tr><th>ID</th><th>Module</th><th>Health</th><th>Runtime</th><th>Rows</th><th>Last Updated</th><th>Explanation</th><th>Issues</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  return kpis()+cards+`<div class="section"><h2 class="mono">V4 Module Health</h2><div class="small mono">Status now reflects freshness, output availability, and valid no-bet states—not just whether code exists.</div>${legend}${table}</div>`;
 };
})();
</script>'''
def replace(html,marker,end,replacement):
 i=html.find(marker)
 if i<0:return html
 j=html.find(end,i)
 return html if j<0 else html[:i]+replacement.strip()+html[j+len(end):]
def main():
 if not PATH.exists():raise SystemExit('docs/index.html does not exist')
 html=PATH.read_text(encoding='utf-8')
 html=replace(html,'<style id="v4-qa-health-style">','</style>',CSS) if 'id="v4-qa-health-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace(html,'<script id="v4-qa-health-script">','</script>',SCRIPT) if 'id="v4-qa-health-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 PATH.write_text(html,encoding='utf-8');print('Dashboard V4 freshness-aware health integration applied')
if __name__=='__main__':main()
