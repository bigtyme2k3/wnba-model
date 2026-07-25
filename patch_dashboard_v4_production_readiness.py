from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html'); DATA=Path('data/dashboard/wnba_production_readiness.json')
CSS=r'''<style id="v4-production-readiness-style">.prodBanner{border:1px solid #29405f;border-radius:16px;padding:16px;background:#091421}.prodBanner.ready{border-color:#1f805f}.prodBanner.blocked{border-color:#91344a}.prodTitle{font-size:25px;font-weight:950}.prodGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:12px}.prodCard{border:1px solid #22334f;border-radius:12px;padding:10px;background:#08101c}.prodGate{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid #17233a;padding:8px 0;font-size:12px}.prodPass{color:#34e6a1}.prodFail{color:#ff6b82}</style>'''
SCRIPT=r'''<script id="v4-production-readiness-script">(function(){const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));window.productionReadiness=function(){const p=(window.DATA&&DATA.production_readiness)||{},s=p.summary||{},g=p.gates||[];const cls=p.ready_for_live_slate?'ready':'blocked';return `<div class="section"><h2 class="mono">Production Readiness</h2><div class="prodBanner ${cls}"><div class="prodTitle">${e(p.message||p.status||'UNKNOWN')}</div><div class="small mono">${e(p.status||'UNKNOWN')} · ${e(p.operating_context?.pipeline_readiness||'UNKNOWN')}</div><div class="prodGrid"><div class="prodCard"><div class="small">Gates passed</div><b>${e(s.passed||0)}/${e(s.gates||0)}</b></div><div class="prodCard"><div class="small">Critical failures</div><b>${e(s.failed_critical||0)}</b></div><div class="prodCard"><div class="small">Daily edges</div><b>${e(s.daily_edges||0)}</b></div><div class="prodCard"><div class="small">Ensemble</div><b>${e(s.ensemble||0)}</b></div><div class="prodCard"><div class="small">Simulations</div><b>${e(s.simulations||0)}</b></div><div class="prodCard"><div class="small">Frozen records</div><b>${e(s.forward_validation_records||0)}</b></div></div></div><div class="section"><h3 class="mono">Production Gates</h3>${g.map(x=>`<div class="prodGate"><span>${e(x.name)}<br><small>${e(x.detail)}</small></span><b class="${x.passed?'prodPass':'prodFail'}">${x.passed?'PASS':'FAIL'}</b></div>`).join('')}</div></div>`};})();</script>'''
def rep(h,s,e,r):
 i=h.find(s)
 if i<0:return h
 j=h.find(e,i)
 if j<0:return h
 return h[:i]+r.strip()+h[j+len(e):]
def main():
 if not HTML.exists():raise SystemExit('docs/index.html missing')
 try:p=json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
 except Exception:p={}
 h=HTML.read_text(encoding='utf-8')
 data='<script id="v4-production-readiness-data">window.DATA=window.DATA||{};DATA.production_readiness='+json.dumps(p,separators=(',',':'))+';</script>'
 h=rep(h,'<script id="v4-production-readiness-data">','</script>',data) if 'id="v4-production-readiness-data"' in h else h.replace('</body>',data+'</body>')
 h=rep(h,'<style id="v4-production-readiness-style">','</style>',CSS) if 'id="v4-production-readiness-style"' in h else h.replace('</head>',CSS+'</head>')
 h=rep(h,'<script id="v4-production-readiness-script">','</script>',SCRIPT) if 'id="v4-production-readiness-script"' in h else h.replace('</body>',SCRIPT+'</body>')
 h=h.replace("['pipeline','Pipeline']","['production','Production'],['pipeline','Pipeline']") if "['production','Production']" not in h else h
 h=h.replace("else if(view==='pipeline')root.innerHTML=safe(window.pipelineStatus)","else if(view==='production')root.innerHTML=safe(window.productionReadiness);else if(view==='pipeline')root.innerHTML=safe(window.pipelineStatus)") if "view==='production'" not in h else h
 HTML.write_text(h,encoding='utf-8');print('Sprint 13 Production tab embedded')
if __name__=='__main__':main()
