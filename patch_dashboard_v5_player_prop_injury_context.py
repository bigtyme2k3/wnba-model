from __future__ import annotations

from pathlib import Path

HTML = Path('docs/index.html')

STYLE = r'''<style id="v5-player-prop-injury-style">
.propInjuryContext{margin:6px 0 4px;padding:7px 8px;border:1px solid #29405f;border-radius:9px;background:#0a1728;font-size:10px;line-height:1.35;min-width:150px}.propInjuryTop{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.propInjuryBadge{display:inline-flex;border-radius:999px;padding:2px 6px;font-size:9px;font-weight:900;letter-spacing:.04em}.propInjuryAvailable{color:#42e7b3;border:1px solid #17634e;background:#082019}.propInjuryReview{color:#ffd06b;border:1px solid #70551f;background:#241b08}.propInjuryBlocked{color:#ff7188;border:1px solid #7b2639;background:#260d16}.propInjuryMetrics{margin-top:4px;color:#aebbd1}.propInjuryPositive{color:#42e7b3;font-weight:800}.propInjuryNegative{color:#ff7188;font-weight:800}.propInjuryReason{margin-top:3px;color:#8291aa;white-space:normal}
</style>'''

SCRIPT = r'''<script id="v5-player-prop-injury-script">(function(){
const norm=v=>String(v??'').toLowerCase().replace(/[’']/g,'').replace(/\b(jr\.?|sr\.?|ii|iii|iv)\b/g,'').replace(/[^a-z0-9 -]/g,' ').replace(/\s+/g,' ').trim();
const num=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');
function adjustmentMap(){const data=window.WNBA_INJURY_DATA||{};const map=new Map();for(const row of Array.isArray(data.adjustments)?data.adjustments:[]){const key=norm(row.player);if(key)map.set(key,row)}return map}
function statusClass(status){status=String(status||'').toUpperCase();if(['OUT','DOUBTFUL'].includes(status))return 'propInjuryBlocked';if(['QUESTIONABLE','UNKNOWN'].includes(status))return 'propInjuryReview';return 'propInjuryAvailable'}
function context(row){const adj=adjustmentMap().get(norm(row?.player));if(!adj&&!row?.injury_adjusted)return '';
 const status=String(row?.injury_status||adj?.severity||'ADJUSTED').toUpperCase();
 const base=num(row?.base_minutes??adj?.base_minutes);const projected=num(row?.projected_minutes??adj?.projected_minutes);const delta=num(row?.minutes_delta??adj?.minutes_delta);
 const usage=num(row?.usage_delta??adj?.usage_delta);const before=num(row?.projection_pre_injury);const after=num(row?.projection??row?.proj);const pd=num(row?.projection_delta);
 const cd=num(row?.confidence_delta);const reason=row?.injury_detail||adj?.detail||'Availability and role adjustment applied.';
 const parts=[];
 if(base!==null&&projected!==null)parts.push(`Minutes ${base.toFixed(1)} → ${projected.toFixed(1)}`);
 if(delta!==null&&Math.abs(delta)>=0.05)parts.push(`<span class="${delta>=0?'propInjuryPositive':'propInjuryNegative'}">${delta>=0?'+':''}${delta.toFixed(1)} min</span>`);
 if(usage!==null&&Math.abs(usage)>=0.01)parts.push(`<span class="${usage>=0?'propInjuryPositive':'propInjuryNegative'}">${usage>=0?'+':''}${usage.toFixed(1)}% usage</span>`);
 if(before!==null&&after!==null)parts.push(`Proj ${before.toFixed(2)} → ${after.toFixed(2)}`);else if(pd!==null&&Math.abs(pd)>=0.01)parts.push(`Proj Δ ${pd>=0?'+':''}${pd.toFixed(2)}`);
 if(cd!==null&&Math.abs(cd)>=0.05)parts.push(`Conf Δ ${cd>=0?'+':''}${cd.toFixed(1)}`);
 return `<div class="propInjuryContext"><div class="propInjuryTop"><span class="propInjuryBadge ${statusClass(status)}">${esc(status)}</span><b>Injury-adjusted</b></div>${parts.length?`<div class="propInjuryMetrics">${parts.join(' · ')}</div>`:''}<div class="propInjuryReason">${esc(reason)}</div></div>`}
function install(){const original=window.propRow;if(typeof original!=='function'||original.__injuryContext)return false;const wrapped=function(row){let html=original(row);const panel=context(row);if(!panel||typeof html!=='string')return html;const anchor='<div class="team mono">';return html.includes(anchor)?html.replace(anchor,panel+anchor):html};wrapped.__injuryContext=true;wrapped.__original=original;window.propRow=wrapped;return true}
let tries=0;const timer=setInterval(()=>{tries++;if(install()||tries>80)clearInterval(timer)},50);install();
window.WNBA_PLAYER_PROP_INJURY_CONTEXT={version:'1.0',install};
})();</script>'''


def replace_block(text: str, start: str, end: str, replacement: str) -> str:
    i = text.find(start)
    if i < 0:
        return text
    j = text.find(end, i)
    if j < 0:
        return text
    return text[:i] + replacement + text[j + len(end):]


def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    html = HTML.read_text(encoding='utf-8')
    if 'id="v5-player-prop-injury-style"' in html:
        html = replace_block(html, '<style id="v5-player-prop-injury-style">', '</style>', STYLE)
    else:
        html = html.replace('</head>', STYLE + '</head>')
    if 'id="v5-player-prop-injury-script"' in html:
        html = replace_block(html, '<script id="v5-player-prop-injury-script">', '</script>', SCRIPT)
    else:
        html = html.replace('</body>', SCRIPT + '</body>')
    HTML.write_text(html, encoding='utf-8')
    print('Player Props injury context installed.')


if __name__ == '__main__':
    main()
