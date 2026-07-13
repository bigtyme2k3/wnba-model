from __future__ import annotations
import json
from pathlib import Path
HTML=Path('docs/index.html');DATA=Path('data/dashboard/wnba_model_explainability.json')
CSS=r'''<style id="v4-explainability-style">.whyBtn{margin-top:8px;border:1px solid #30435f;background:#0a1322;color:#cbd7f1;border-radius:999px;padding:6px 10px;font-weight:900}.whyPanel{display:none;margin-top:10px;border-top:1px solid #20304b;padding-top:10px}.whyPanel.open{display:block}.whyFeature{display:grid;grid-template-columns:1fr auto;gap:8px;padding:6px 0;border-bottom:1px solid #172338}.whyPos{color:#00e39b}.whyNeg{color:#ff6b7c}.whyNeutral{color:#8fa0bd}.whySummary{font-size:12px;color:#cbd7f1;margin-bottom:8px}.whyUnavailable{font-size:10px;color:#8fa0bd;margin-top:8px}</style>'''
SCRIPT=r'''<script id="v4-explainability-script">(function(){const rows=DATA.model_explainability?.explanations||[];window.explainabilityIndex=Object.fromEntries(rows.map(r=>[String(r.rank),r]));window.toggleWhy=function(rank){document.getElementById(`why-${rank}`)?.classList.toggle('open')};window.whyMarkup=function(rank){const r=window.explainabilityIndex[String(rank)];if(!r)return '<div class="whyUnavailable">Explanation unavailable.</div>';const feats=(r.features||[]).filter(x=>x.available).slice(0,8).map(f=>{const cls=f.direction==='positive'?'whyPos':f.direction==='negative'?'whyNeg':'whyNeutral';const sign=Number(f.contribution)>0?'+':'';return `<div class="whyFeature"><div><b>${E(f.feature)}</b><div class="small">${E(f.detail)}</div></div><div class="${cls} mono">${sign}${E(f.contribution)}</div></div>`}).join('');const miss=(r.unavailable_inputs||[]).length?`<div class="whyUnavailable">Unavailable: ${(r.unavailable_inputs||[]).map(E).join(', ')}</div>`:'';return `<div class="whySummary">${E(r.summary||'')}</div>${feats}${miss}`};const previous=window.topPlays;window.topPlays=function(){let html=typeof previous==='function'?previous():'';html=html.replace(/<div class="tpUnits mono">Units ([\s\S]*?)<\/div><\/div>/g,(match,units)=>{const rank=(match.match(/#([^<]+)/)||[])[1];if(!rank)return match;return `<div class="tpUnits mono">Units ${units}</div><button class="whyBtn" onclick="toggleWhy('${rank}')">Why?</button><div class="whyPanel" id="why-${rank}">${window.whyMarkup(rank)}</div></div>`});return html};window.best=window.topPlays;})();</script>'''
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
 html=HTML.read_text(encoding='utf-8');data=f'<script id="v4-explainability-data">DATA.model_explainability={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
 html=replace_block(html,'<script id="v4-explainability-data">','</script>',data) if 'id="v4-explainability-data"' in html else html.replace('</body>',data+'</body>')
 html=replace_block(html,'<style id="v4-explainability-style">','</style>',CSS) if 'id="v4-explainability-style"' in html else html.replace('</head>',CSS+'</head>')
 html=replace_block(html,'<script id="v4-explainability-script">','</script>',SCRIPT) if 'id="v4-explainability-script"' in html else html.replace('</body>',SCRIPT+'</body>')
 HTML.write_text(html,encoding='utf-8');print('Top Plays explainability installed')
if __name__=='__main__':main()
