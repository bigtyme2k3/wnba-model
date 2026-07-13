from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_controlled_recalibration.json')
CSS=r'''<style id="v4-calibration-lab-style">.calGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}.calCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}.calApproved{color:#00e39b}.calRejected{color:#ff4d67}.calTesting{color:#ffd166}.calLocked{color:#8fa0bd}.calValue{font-size:22px;font-weight:950}.calNote{font-size:11px;color:#8fa0bd;margin-top:8px}</style>'''
SCRIPT=r'''<script id="v4-calibration-lab-script">(function(){window.calibrationLab=function(){const p=DATA.controlled_recalibration||{},rows=Array.isArray(p.proposals)?p.proposals:[];const cards=rows.map(r=>{const cls=r.status==='APPROVED'?'calApproved':r.status==='REJECTED'?'calRejected':r.status==='TESTING'?'calTesting':'calLocked';return `<div class="calCard"><div class="row"><b>${E(r.stat)}</b><span class="${cls} mono">${E(r.status)}</span></div><div class="small mono">N ${E(r.sample_size)} · Holdout ${E(r.holdout_size)}</div><div class="calValue mono">Mean ×${E(r.proposed?.mean_multiplier??1)}</div><div class="small mono">Variance ×${E(r.proposed?.variance_multiplier??1)}</div><div class="small mono">MAE ${r.backtest?.baseline_mae==null?'—':E(r.backtest.baseline_mae)} → ${r.backtest?.proposed_mae==null?'—':E(r.backtest.proposed_mae)}</div><div class="calNote">${E(r.reason)}</div></div>`}).join('');return `<div class="section"><h2 class="mono">Calibration Lab</h2><div class="small mono">Bounded holdout-tested proposals. Production weights remain unchanged until manual review.</div><div class="calGrid">${cards||'<div class="empty mono">No graded sample available for proposals.</div>'}</div></div>`};const previous=window.unifiedSimulation;window.unifiedSimulation=function(){const base=typeof previous==='function'?previous():'';return window.calibrationLab()+base};})();</script>'''
def replace_block(html,start,end,replacement):
 i=html.find(start)
 if i<0:return html
 j=html.find(end,i)
 if j<0:return html
 return html[:i]+replacement.strip()+html[j+len(end):]
def main():
 if not HTML.exists():raise SystemExit('docs/index.html missing')
 try:payload=json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
 except Exception:payload={}
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-calibration-lab-data">DATA.controlled_recalibration={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-calibration-lab-data">','</script>',data) if 'id="v4-calibration-lab-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-calibration-lab-style">','</style>',CSS) if 'id="v4-calibration-lab-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-calibration-lab-script">','</script>',SCRIPT) if 'id="v4-calibration-lab-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Calibration Lab added to Model Center')
if __name__=='__main__':main()
