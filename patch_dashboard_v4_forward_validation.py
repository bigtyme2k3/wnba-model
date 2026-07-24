from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_forward_validation.json')
CSS=r'''<style id="v4-forward-validation-style">.fvGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.fvCard{border:1px solid #263854;border-radius:14px;padding:14px;background:#091321}.fvBig{font-size:27px;font-weight:950}.fvTable{overflow:auto}.fvGood{color:#34e6a1}.fvWarn{color:#ffd166}</style>'''
SCRIPT=r'''<script id="v4-forward-validation-script">(function(){const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const pct=v=>v==null?'—':(Number(v)*100).toFixed(1)+'%';window.forwardValidation=function(){const p=(window.DATA&&DATA.forward_validation)||{},s=p.summary||{},by=p.by_source||{};const cards=[['Frozen',s.frozen_predictions||0],['Settled',s.settled_predictions||0],['Hit Rate',pct(s.hit_rate)],['ROI',pct(s.roi)],['Units',s.units??'—'],['Chronology',s.chronology_valid?'PASS':'CHECK']].map(x=>`<div class="fvCard"><div class="small mono">${e(x[0])}</div><div class="fvBig">${e(x[1])}</div></div>`).join('');const rows=Object.entries(by).map(([k,v])=>`<tr><td>${e(k)}</td><td>${e(v.frozen)}</td><td>${e(v.graded)}</td><td>${pct(v.hit_rate)}</td></tr>`).join('');return `<div class="section"><h2 class="mono">Forward Validation</h2><div class="small mono">Immutable pregame snapshots graded only after outcomes. This is the live out-of-sample record.</div><div class="fvGrid">${cards}</div><div class="fvTable"><table><thead><tr><th>Source</th><th>Frozen</th><th>Graded</th><th>Hit Rate</th></tr></thead><tbody>${rows||'<tr><td colspan="4">Awaiting the first frozen live slate.</td></tr>'}</tbody></table></div></div>`}})();</script>'''
def repl(h,s,e,r):
 i=h.find(s)
 if i<0:return h
 j=h.find(e,i)
 return h if j<0 else h[:i]+r.strip()+h[j+len(e):]
def main():
 if not HTML.exists():raise SystemExit('docs/index.html missing')
 try:p=json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
 except Exception:p={}
 h=HTML.read_text(encoding='utf-8');d='<script id="v4-forward-validation-data">window.DATA=window.DATA||{};DATA.forward_validation='+json.dumps(p,separators=(',',':'),allow_nan=False)+'</script>'
 h=repl(h,'<script id="v4-forward-validation-data">','</script>',d) if 'id="v4-forward-validation-data"' in h else h.replace('</body>',d+'</body>')
 h=repl(h,'<style id="v4-forward-validation-style">','</style>',CSS) if 'id="v4-forward-validation-style"' in h else h.replace('</head>',CSS+'</head>')
 h=repl(h,'<script id="v4-forward-validation-script">','</script>',SCRIPT) if 'id="v4-forward-validation-script"' in h else h.replace('</body>',SCRIPT+'</body>')
 # extend consolidated navigation/render safely
 h=h.replace("['pipeline','Pipeline']", "['pipeline','Pipeline'],['validation','Validation']") if "['validation','Validation']" not in h else h
 h=h.replace("else if(view==='pipeline')root.innerHTML=safe(window.pipelineStatus)","else if(view==='pipeline')root.innerHTML=safe(window.pipelineStatus);else if(view==='validation')root.innerHTML=safe(window.forwardValidation)") if "view==='validation'" not in h else h
 HTML.write_text(h,encoding='utf-8');print('Forward Validation dashboard embedded')
if __name__=='__main__':main()
