"""Add immutable prediction/CLV evidence integrity to the Data Health view."""
from __future__ import annotations

import json
import re
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_v5_evidence_integrity.json')
STYLE_ID = 'v5-evidence-integrity-style'
SCRIPT_ID = 'v5-evidence-integrity-script'

STYLE = r'''<style id="v5-evidence-integrity-style">
.v5ei{margin:0 0 18px;border:1px solid #263854;border-radius:16px;background:#08111f;padding:14px}.v5eiHead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.v5eiTitle{font-size:18px;font-weight:900}.v5eiSub{font-size:11px;color:#8fa0bb;margin-top:4px}.v5eiStatus{border:1px solid currentColor;border-radius:999px;padding:5px 9px;font-size:11px;font-weight:900}.v5eiGREEN{color:#34d399}.v5eiYELLOW{color:#ffd166}.v5eiRED{color:#ff7188}.v5eiGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0}.v5eiCard{border:1px solid #20304b;border-radius:13px;padding:11px;background:#091321}.v5eiCard b{display:block;font-size:20px;margin-top:4px}.v5eiSections{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.v5eiSection{border:1px solid #20304b;border-radius:13px;padding:11px;background:#091321}.v5eiSectionHead{display:flex;justify-content:space-between;gap:8px}.v5eiMsg{color:#9babc1;font-size:11px;margin-top:7px;line-height:1.45}.v5eiWarn{color:#ffd166}.v5eiBad{color:#ff7188}@media(max-width:820px){.v5eiGrid,.v5eiSections{grid-template-columns:1fr 1fr}.v5eiHead{flex-direction:column}}@media(max-width:560px){.v5eiGrid,.v5eiSections{grid-template-columns:1fr}}
</style>'''


def script(payload: dict) -> str:
    blob=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('</','<\\/')
    return f'''<script id="{SCRIPT_ID}">(function(){{
const A={blob};window.WNBA_V5_EVIDENCE_INTEGRITY=A;const prior=window.health;
const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');const cls=s=>'v5ei'+String(s||'').toUpperCase();
function section(name,s){{const hard=Array.isArray(s.hard_violations)?s.hard_violations:[],warn=Array.isArray(s.warnings)?s.warnings:[];const stats=[];if(name==='forward_ledger')stats.push(`Rows ${{s.rows||0}} · resolved ${{s.resolved_rows||0}} · context ${{s.context_rows||0}}`);if(name==='model_history')stats.push(`Current rows ${{s.current_model_rows||0}} · resolved ${{s.current_model_resolved_rows||0}}`);if(name==='explicit_closing_evidence')stats.push(`Explicit close rows ${{s.rows||0}} · queue ${{s.queue_status||'—'}}`);if(name==='clv_readiness')stats.push(`Coverage ${{Number(s.explicit_clv_coverage_pct||0).toFixed(1)}}% / ${{Number(s.minimum_promotion_clv_coverage_pct||0).toFixed(1)}}% required`);return `<div class="v5eiSection"><div class="v5eiSectionHead"><b class="mono">${{esc(name.replaceAll('_',' '))}}</b><span class="v5eiStatus ${{cls(s.status)}}">${{esc(s.status||'—')}}</span></div><div class="v5eiMsg">${{esc(stats.join(' · '))}}</div>${{hard.length?`<div class="v5eiMsg v5eiBad">${{hard.map(esc).join('<br>')}}</div>`:''}}${{warn.length?`<div class="v5eiMsg v5eiWarn">${{warn.map(esc).join('<br>')}}</div>`:''}}</div>`}}
function panel(){{const s=A.summary||{{}},sections=A.sections||{{}};return `<div class="v5ei"><div class="v5eiHead"><div><div class="v5eiTitle mono">V5 Evidence Integrity</div><div class="v5eiSub mono">Immutable predictions · verified grading chronology · explicit pre-tip closes · CLV readiness</div></div><div class="v5eiStatus ${{cls(A.status)}}">${{esc(A.status||'UNKNOWN')}}</div></div><div class="v5eiGrid"><div class="v5eiCard"><span class="label mono">Sections</span><b>${{s.sections||0}}</b></div><div class="v5eiCard"><span class="label mono">Hard Violations</span><b class="v5eiRED">${{s.hard_violation_count||0}}</b></div><div class="v5eiCard"><span class="label mono">Warnings</span><b class="v5eiYELLOW">${{s.warning_count||0}}</b></div><div class="v5eiCard"><span class="label mono">Generated</span><b style="font-size:12px">${{esc(A.generated_at_utc||'—')}}</b></div></div><div class="v5eiSections">${{Object.entries(sections).map(([n,v])=>section(n,v)).join('')}}</div><div class="v5eiMsg">${{esc(A.policy||'')}}</div></div>`}}
window.health=function(){{let old='';try{{if(typeof prior==='function')old=prior()||''}}catch(e){{console.error('prior health renderer',e)}}return panel()+old}};
}})();</script>'''


def replace(html: str, tag: str, marker: str, block: str, anchor: str):
    pattern=rf'<{tag} id="{re.escape(marker)}"[^>]*>.*?</{tag}>'
    if re.search(pattern,html,flags=re.S):return re.sub(pattern,block,html,count=1,flags=re.S)
    i=html.lower().rfind(anchor.lower());return html[:i]+block+'\n'+html[i:] if i>=0 else html+'\n'+block


def main():
    if not HTML.exists(): raise SystemExit('docs/index.html missing')
    if not DATA.exists():
        print('V5 evidence integrity artifact not available yet; renderer skipped')
        return
    p=json.loads(DATA.read_text(encoding='utf-8'))
    html=HTML.read_text(encoding='utf-8',errors='replace')
    html=replace(html,'style',STYLE_ID,STYLE,'</head>')
    html=replace(html,'script',SCRIPT_ID,script(p),'</body>')
    HTML.write_text(html,encoding='utf-8')
    print({'status':'PASS','evidence_integrity':p.get('status'),'hard_violations':(p.get('summary') or {}).get('hard_violation_count')})

if __name__=='__main__':main()
