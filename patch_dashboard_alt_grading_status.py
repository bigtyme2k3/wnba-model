"""Embed a screenshot-verifiable grading status panel in ALT Performance."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

HTML = Path("docs/index.html")
REPORT = Path("data/dashboard/wnba_alt_performance.json")
START = "<!-- WNBA_ALT_GRADING_STATUS_START -->"
END = "<!-- WNBA_ALT_GRADING_STATUS_END -->"


def fmt_time(value: str | None) -> str:
    if not value:
        return "Unavailable"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%b %d, %Y · %I:%M %p UTC")
    except ValueError:
        return value


def build_block() -> str:
    payload = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    summary = payload.get("summary") or {}
    archived = int(summary.get("archived_candidates") or summary.get("archived") or 0)
    graded = int(summary.get("graded") or 0)
    pending = int(summary.get("pending") if summary.get("pending") is not None else max(archived - graded, 0))
    coverage = (graded / archived * 100.0) if archived else 0.0
    target = payload.get("target_date") or "Unknown"
    generated = fmt_time(payload.get("generated_at_utc"))
    status = "COMPLETE" if pending == 0 and archived > 0 else "REVIEW"
    cls = "complete" if status == "COMPLETE" else "review"
    return f'''{START}
<style id="wnba-alt-grading-status-style">
#wnba-alt-grading-status{{display:none;margin:0 0 18px;padding:14px;border:1px solid #263854;border-radius:18px;background:linear-gradient(135deg,rgba(9,22,38,.98),rgba(12,31,48,.98));font-family:Inter,system-ui,sans-serif}}
#wnba-alt-grading-status .ags-head{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}}
#wnba-alt-grading-status .ags-title{{font-size:13px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#cbd5e1}}
#wnba-alt-grading-status .ags-chip{{padding:5px 10px;border-radius:999px;font-size:11px;font-weight:900}} .ags-chip.complete{{background:#064e3b;color:#6ee7b7}} .ags-chip.review{{background:#4a2d08;color:#facc15}}
#wnba-alt-grading-status .ags-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}
#wnba-alt-grading-status .ags-card{{padding:12px;border:1px solid #263854;border-radius:14px;background:rgba(5,15,28,.72)}}
#wnba-alt-grading-status .ags-label{{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:#94a3b8}} .ags-value{{margin-top:5px;font-size:18px;font-weight:900;color:#e2e8f0}} .ags-note{{margin-top:4px;font-size:10px;color:#64748b}}
@media(max-width:760px){{#wnba-alt-grading-status .ags-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
</style>
<section id="wnba-alt-grading-status" aria-label="ALT grading freshness status">
<div class="ags-head"><div class="ags-title">ALT Grading Checkpoint</div><div class="ags-chip {cls}">{status}</div></div>
<div class="ags-grid">
<div class="ags-card"><div class="ags-label">Last graded</div><div class="ags-value">{target}</div><div class="ags-note">Generated {generated}</div></div>
<div class="ags-card"><div class="ags-label">Coverage</div><div class="ags-value">{graded}/{archived}</div><div class="ags-note">{coverage:.1f}% of archived rows</div></div>
<div class="ags-card"><div class="ags-label">Pending</div><div class="ags-value">{pending}</div><div class="ags-note">Awaiting a verified result or mapping</div></div>
<div class="ags-card"><div class="ags-label">QA state</div><div class="ags-value">{status}</div><div class="ags-note">Screenshot-verifiable grading freshness</div></div>
</div></section>
<script id="wnba-alt-grading-status-script">
(function(){{
  const panel=document.getElementById('wnba-alt-grading-status');
  if(!panel)return;
  const norm=s=>(s||'').trim().toLowerCase();
  let selected='';
  const visible=el=>!!(el&&el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden');
  function altHeading(){{return [...document.querySelectorAll('h1,h2,h3')].find(el=>norm(el.textContent)==='alt performance'&&visible(el));}}
  function place(){{
    const heading=altHeading();
    if(!heading)return false;
    const host=heading.closest('section,main,article')||heading.parentElement;
    if(host&&panel.parentElement!==host)host.insertBefore(panel,heading.nextElementSibling||null);
    return true;
  }}
  function sync(){{
    const headingVisible=place();
    panel.style.display=(selected==='alt performance'||(!selected&&headingVisible))?'block':'none';
  }}
  document.addEventListener('click',event=>{{
    const tab=event.target.closest('button,[role="tab"],a');
    if(tab){{const label=norm(tab.textContent);if(label)selected=label;}}
    setTimeout(sync,50);
  }},true);
  new MutationObserver(sync).observe(document.body,{{subtree:true,childList:true,attributes:true,attributeFilter:['class','style','hidden','aria-selected']}});
  sync();setTimeout(sync,400);setTimeout(sync,1000);
}})();
</script>
{END}'''


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html is missing")
    html = HTML.read_text(encoding="utf-8")
    block = build_block()
    pattern = re.escape(START) + r".*?" + re.escape(END)
    html = re.sub(pattern, block, html, flags=re.S) if re.search(pattern, html, flags=re.S) else html.replace("</body>", block + "\n</body>", 1)
    HTML.write_text(html, encoding="utf-8")
    print("ALT grading status panel embedded")


if __name__ == "__main__":
    main()
