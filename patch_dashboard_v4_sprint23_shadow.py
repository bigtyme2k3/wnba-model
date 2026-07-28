from __future__ import annotations
import json
from pathlib import Path

HTML = Path("docs/index.html")
DATA = Path("data/dashboard/sprint23_shadow_intelligence.json")

CSS = r'''<style id="s23-shadow-style">
#s23ShadowPanel{margin:18px 0;padding:16px;border:1px solid #725b18;border-radius:16px;background:linear-gradient(180deg,#151207,#0d1018);color:#eef3ff}.s23Head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}.s23Badge{font-size:11px;font-weight:900;padding:5px 9px;border-radius:999px;background:#44370c;color:#ffd95e;border:1px solid #8d7222}.s23Grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-top:14px}.s23Card{border:1px solid #293750;background:#0b1422;border-radius:14px;padding:13px}.s23Title{font-weight:900;font-size:15px}.s23Meta{font-size:11px;color:#9fb0cc;margin-top:3px}.s23Nums{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0}.s23Num{background:#111d30;border-radius:9px;padding:7px;text-align:center;font-size:10px;color:#9fb0cc}.s23Num b{display:block;color:#fff;font-size:13px}.s23Why{margin-top:8px;border-top:1px solid #24324a;padding-top:8px}.s23Reason{font-size:11px;color:#c7d2e8;padding:4px 0}.s23Reason b{color:#7ff0bd}.s23Validation{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.s23Stat{background:#111d30;border-radius:9px;padding:7px 10px;font-size:11px}.s23Warn{font-size:11px;color:#ffd95e;margin-top:7px}
</style>'''

SCRIPT = r'''<script id="s23-shadow-script">(function(){const D=window.S23_SHADOW||{};const esc=x=>String(x??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const pct=x=>x==null?'—':(Number(x)*100).toFixed(1)+'%';const odds=x=>Number(x)>0?'+'+x:x;const v=D.validation||{};const cards=(D.cards||[]).map(c=>`<div class="s23Card"><div class="s23Title">#${c.rank} ${esc(c.player)} — ${esc(c.side)} ${esc(c.line)} ${esc(c.stat).toUpperCase()}</div><div class="s23Meta">${esc(c.sportsbook)} ${odds(c.odds)} · ${esc(c.game||c.game_date)}</div><div class="s23Nums"><div class="s23Num"><b>${esc(c.projection)}</b>Projection</div><div class="s23Num"><b>${pct(c.probability_edge)}</b>Prob. edge</div><div class="s23Num"><b>${pct(c.expected_value_per_dollar)}</b>Est. EV/$1</div></div><div class="s23Why">${(c.reasons||[]).slice(0,6).map(r=>`<div class="s23Reason"><b>${esc(r.label)}:</b> ${esc(r.value)} — ${esc(r.detail)}</div>`).join('')}</div></div>`).join('');const html=`<section id="s23ShadowPanel"><div class="s23Head"><div><h2 style="margin:0">Sprint 23 Shadow Intelligence</h2><div class="s23Warn">${esc(D.disclaimer||'Research-only shadow signals.')}</div></div><span class="s23Badge">SHADOW ONLY</span></div><div class="s23Validation"><div class="s23Stat">Ledger: <b>${v.ledger_rows||0}</b></div><div class="s23Stat">Graded: <b>${v.graded_rows||0}</b> / ${v.minimum_graded_for_promotion_review||200}</div><div class="s23Stat">Pending: <b>${v.pending_rows||0}</b></div><div class="s23Stat">ROI: <b>${pct(v.roi_per_dollar)}</b></div><div class="s23Stat">Review: <b>${esc(v.promotion_review_status||'INSUFFICIENT_EVIDENCE')}</b></div></div><div class="s23Grid">${cards||'<div class="s23Meta">No positive-EV shadow opportunities available.</div>'}</div></section>`;const host=document.querySelector('main,.container,#app')||document.body;host.insertAdjacentHTML('afterbegin',html);})();</script>'''


def replace_block(html: str, start: str, end: str, replacement: str) -> str:
    i = html.find(start)
    if i < 0:
        return html
    j = html.find(end, i)
    if j < 0:
        return html
    return html[:i] + replacement + html[j + len(end):]


def main():
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    payload = json.loads(DATA.read_text()) if DATA.exists() else {}
    html = HTML.read_text(encoding="utf-8")
    data = f'<script id="s23-shadow-data">window.S23_SHADOW={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html = replace_block(html, '<script id="s23-shadow-data">', '</script>', data) if 'id="s23-shadow-data"' in html else html.replace('</body>', data + '</body>')
    html = replace_block(html, '<style id="s23-shadow-style">', '</style>', CSS) if 'id="s23-shadow-style"' in html else html.replace('</head>', CSS + '</head>')
    html = replace_block(html, '<script id="s23-shadow-script">', '</script>', SCRIPT) if 'id="s23-shadow-script"' in html else html.replace('</body>', SCRIPT + '</body>')
    HTML.write_text(html, encoding="utf-8")
    print("Sprint 23 shadow intelligence panel installed")


if __name__ == "__main__":
    main()
