"""Render the canonical current-data health audit inside the Data Health tab."""
from __future__ import annotations

import json
import re
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_v5_current_data_health.json')
STYLE_ID = 'v5-current-data-health-style'
SCRIPT_ID = 'v5-current-data-health-script'

STYLE = r'''<style id="v5-current-data-health-style">
.v5dhWrap{margin:0 0 18px}.v5dhHead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;border:1px solid #263854;border-radius:16px;padding:14px;background:#08111f}.v5dhTitle{font-size:18px;font-weight:900}.v5dhSub{font-size:11px;color:#8fa0bb;margin-top:4px}.v5dhStatus{border:1px solid currentColor;border-radius:999px;padding:5px 9px;font-size:11px;font-weight:900}.v5dhGREEN{color:#34d399}.v5dhYELLOW{color:#ffd166}.v5dhRED{color:#ff7188}.v5dhGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0}.v5dhCard{border:1px solid #20304b;border-radius:13px;padding:11px;background:#091321}.v5dhCard .n{font-size:24px;font-weight:900;margin-top:5px}.v5dhTableWrap{overflow:auto;border:1px solid #20304b;border-radius:14px}.v5dhTable{width:100%;min-width:860px;border-collapse:collapse}.v5dhTable th,.v5dhTable td{padding:9px;border-bottom:1px solid #1b293e;text-align:left;vertical-align:top;font-size:12px}.v5dhPill{display:inline-block;border:1px solid currentColor;border-radius:999px;padding:3px 7px;font-size:10px;font-weight:900}.v5dhFind{color:#a7b5cb;font-size:11px}.v5dhLegacy{margin-top:10px;color:#73839d;font-size:11px}.v5dhPolicy{margin:10px 0;color:#8fa0bb;font-size:11px}@media(max-width:820px){.v5dhGrid{grid-template-columns:1fr 1fr}.v5dhHead{flex-direction:column}}
</style>'''


def build_script(payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('</', '<\\/')
    return f'''<script id="{SCRIPT_ID}">(function(){{
const H={blob};window.WNBA_V5_CURRENT_DATA_HEALTH=H;
const prior=window.health;
const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');
const cls=s=>'v5dh'+String(s||'').toUpperCase();
const pill=s=>`<span class="v5dhPill ${{cls(s)}}">${{esc(String(s||'unknown').toUpperCase())}}</span>`;
function row(r){{const f=Array.isArray(r.findings)?r.findings:[];return `<tr><td><b>${{esc(r.name)}}</b><div class="v5dhFind">${{esc(r.path||'')}}</div></td><td>${{pill(r.status)}}</td><td>${{esc(r.target_date||r.modified_date||'—')}}</td><td>${{esc(r.reported_status||'—')}}</td><td class="v5dhFind">${{f.length?f.map(esc).join('<br>'):'None'}}</td></tr>`}}
function panel(){{const s=H.summary||{{}},rows=[...(H.critical||[]),...(H.prospective_context||[])];const legacy=(H.legacy_observability||[]).filter(x=>x.status==='legacy_stale');return `<div class="v5dhWrap"><div class="v5dhHead"><div><div class="v5dhTitle mono">Current V5 Data Health</div><div class="v5dhSub mono">Canonical target ${{esc(H.target_date||'—')}} · generated ${{esc(H.generated_at_utc||'—')}}</div></div><div class="v5dhStatus ${{cls(H.status)}}">${{esc(H.status||'UNKNOWN')}}</div></div><div class="v5dhGrid"><div class="v5dhCard"><div class="label mono">Critical Checks</div><div class="n mono">${{esc(s.critical_checks||0)}}</div></div><div class="v5dhCard"><div class="label mono">Green</div><div class="n mono v5dhGREEN">${{esc(s.green||0)}}</div></div><div class="v5dhCard"><div class="label mono">Warnings</div><div class="n mono v5dhYELLOW">${{esc(s.yellow||0)}}</div></div><div class="v5dhCard"><div class="label mono">Failed</div><div class="n mono v5dhRED">${{esc(s.red||0)}}</div></div></div><div class="v5dhPolicy mono">${{esc(H.policy||'')}}</div><div class="v5dhTableWrap"><table class="v5dhTable"><thead><tr><th>Artifact</th><th>Health</th><th>Date</th><th>Runtime</th><th>Findings</th></tr></thead><tbody>${{rows.map(row).join('')}}</tbody></table></div>${{legacy.length?`<div class="v5dhLegacy mono">Legacy/stale observability kept out of the production gate: ${{legacy.map(x=>esc(x.name)).join(', ')}}</div>`:''}}</div>`}}
window.health=function(){{let old='';try{{if(typeof prior==='function')old=prior()||''}}catch(e){{console.error('legacy health renderer',e)}}return panel()+old}};
}})();</script>'''


def replace_or_inject(html: str, tag: str, marker: str, block: str, close: str) -> str:
    pattern = rf'<{tag} id="{re.escape(marker)}"[^>]*>.*?</{tag}>'
    if re.search(pattern, html, flags=re.S):
        return re.sub(pattern, block, html, count=1, flags=re.S)
    idx = html.lower().rfind(close.lower())
    return html[:idx] + block + '\n' + html[idx:] if idx >= 0 else html + '\n' + block


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    if not DATA.exists():
        raise SystemExit('current V5 data health artifact missing')
    payload = json.loads(DATA.read_text(encoding='utf-8'))
    html = HTML.read_text(encoding='utf-8', errors='replace')
    html = replace_or_inject(html, 'style', STYLE_ID, STYLE, '</head>')
    html = replace_or_inject(html, 'script', SCRIPT_ID, build_script(payload), '</body>')
    HTML.write_text(html, encoding='utf-8')
    verify = HTML.read_text(encoding='utf-8')
    for token in (STYLE_ID, SCRIPT_ID, 'Current V5 Data Health', str(payload.get('target_date') or '')):
        if token not in verify:
            raise SystemExit(f'current data-health dashboard patch missing {token!r}')
    print({'status':'PASS','target_date':payload.get('target_date'),'health_status':payload.get('status'),'checks':(payload.get('summary') or {}).get('critical_checks')})


if __name__ == '__main__':
    main()
