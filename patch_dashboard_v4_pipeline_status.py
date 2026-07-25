from __future__ import annotations
import json
from pathlib import Path

HTML=Path('docs/index.html');PIPE=Path('data/dashboard/wnba_autonomous_pipeline.json');READY=Path('data/dashboard/wnba_pipeline_readiness.json');QA=Path('data/dashboard/wnba_final_qa.json')
CSS=r'''<style id="v4-pipeline-status-style">.pipeBanner{border:1px solid #29405f;border-radius:16px;padding:14px;margin:14px 0;background:#091421}.pipeBanner.ready{border-color:#1f805f}.pipeBanner.fail{border-color:#91344a}.pipeGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:12px}.pipeCard{border:1px solid #22334f;border-radius:12px;padding:10px;background:#08101c}.pipeStatus{font-size:22px;font-weight:950}.pipeReason{color:#91a1ba;font-size:12px;margin-top:5px}.pipeStep{font-size:11px;padding:5px 0;border-bottom:1px solid #17233a}</style>'''
SCRIPT=r'''<script id="v4-pipeline-status-script">(function(){const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));window.pipelineStatus=function(){const p=(window.DATA&&DATA.pipeline_status)||{},r=(window.DATA&&DATA.pipeline_readiness)||{},q=(window.DATA&&DATA.final_qa)||{};const status=p.status||r.status||'WAIT';const cls=status==='READY'?'ready':status==='FAIL'?'fail':'';const steps=(p.steps||[]).map(s=>`<div class="pipeStep"><b>${esc(s.name)}</b> · ${esc(s.status)}</div>`).join('');return `<div class="section"><h2 class="mono">Pipeline Control</h2><div class="pipeBanner ${cls}"><div class="pipeStatus">${esc(status)}</div><div class="pipeReason">${esc(r.reason||'No readiness report yet.')}</div><div class="pipeGrid"><div class="pipeCard"><div class="small">Games</div><b>${esc(r.counts?.today_games??0)}</b></div><div class="pipeCard"><div class="small">Props</div><b>${esc(r.counts?.props??0)}</b></div><div class="pipeCard"><div class="small">Markets</div><b>${esc(r.counts?.sportsbook_markets??0)}</b></div><div class="pipeCard"><div class="small">QA</div><b>${esc(q.status||'—')}</b></div><div class="pipeCard"><div class="small">Green light</div><b>${q.green_light?'YES':'NO'}</b></div></div></div><div class="section"><h3 class="mono">Pipeline Steps</h3>${steps||'<div class="empty mono">No run recorded yet.</div>'}</div></div>`};})();</script>'''
def load(path):
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else {}
    except Exception:return {}
def replace(html,start,end,replacement):
    i=html.find(start)
    if i<0:return html
    j=html.find(end,i)
    if j<0:return html
    return html[:i]+replacement.strip()+html[j+len(end):]
def main():
    if not HTML.exists():raise SystemExit('docs/index.html missing')
    html=HTML.read_text(encoding='utf-8')
    data='<script id="v4-pipeline-status-data">window.DATA=window.DATA||{};DATA.pipeline_status='+json.dumps(load(PIPE),separators=(',',':'))+';DATA.pipeline_readiness='+json.dumps(load(READY),separators=(',',':'))+';DATA.final_qa='+json.dumps(load(QA),separators=(',',':'))+';</script>'
    html=replace(html,'<script id="v4-pipeline-status-data">','</script>',data) if 'id="v4-pipeline-status-data"' in html else html.replace('</body>',data+'</body>')
    html=replace(html,'<style id="v4-pipeline-status-style">','</style>',CSS) if 'id="v4-pipeline-status-style"' in html else html.replace('</head>',CSS+'</head>')
    html=replace(html,'<script id="v4-pipeline-status-script">','</script>',SCRIPT) if 'id="v4-pipeline-status-script"' in html else html.replace('</body>',SCRIPT+'</body>')
    html=html.replace("['health','V4 Health']","['pipeline','Pipeline'],['health','V4 Health']") if "['pipeline','Pipeline']" not in html else html
    html=html.replace("else if(view==='health')root.innerHTML=healthView()","else if(view==='pipeline')root.innerHTML=safe(window.pipelineStatus);else if(view==='health')root.innerHTML=healthView()") if "view==='pipeline'" not in html else html
    HTML.write_text(html,encoding='utf-8')
    try:
        from patch_dashboard_v4_forward_validation import main as patch_validation
        patch_validation()
    except Exception as exc:print('Sprint 12 dashboard persistence warning:',exc)
    try:
        from patch_dashboard_v4_production_readiness import main as patch_production
        patch_production()
    except Exception as exc:print('Sprint 13 dashboard persistence warning:',exc)
    print('Sprint 11 Pipeline, Sprint 12 Validation, and Sprint 13 Production tabs embedded')
if __name__=='__main__':main()
