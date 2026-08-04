"""Build and embed ALT game-log recovery progress in the dashboard."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

RECOVERY = Path("data/dashboard/wnba_alt_game_log_recovery.json")
DIAGNOSTICS = Path("data/dashboard/wnba_alt_pending_diagnostics.json")
OUTPUT = Path("data/dashboard/wnba_alt_recovery_progress.json")
WAREHOUSE = Path("data/warehouse/wnba_alt_recovery_progress.json")
HTML = Path("docs/index.html")
START = "<!-- WNBA_ALT_RECOVERY_PROGRESS_START -->"
END = "<!-- WNBA_ALT_RECOVERY_PROGRESS_END -->"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def build(before_path: Path | None = None) -> dict:
    recovery = load(RECOVERY)
    diagnostics = load(DIAGNOSTICS)
    prior = load(before_path) if before_path and before_path.exists() else load(OUTPUT)
    before = recovery.get("before") or {}
    if prior.get("summary"):
        previous_queued = int(prior["summary"].get("queued") or 0)
    else:
        previous_queued = int(before.get("pending") or recovery.get("targets", {}).get("records") or 0)
    if before_path and before_path.exists():
        initial = load(before_path)
        previous_queued = int((initial.get("before") or {}).get("pending") or initial.get("targets", {}).get("records") or previous_queued)
    current = int((diagnostics.get("summary") or {}).get("pending_rows") or 0)
    recovered = max(0, previous_queued - current)
    dates = recovery.get("targets", {}).get("dates") or []
    by_date = {x.get("date"): int(x.get("records") or 0) for x in recovery.get("targets", {}).get("by_date") or []}
    timeline = []
    for date in dates:
        remaining = sum(1 for r in diagnostics.get("inspector", []) if str(r.get("date")) == str(date))
        targeted = by_date.get(date, remaining)
        state = "complete" if remaining == 0 else ("partial" if remaining < targeted else "waiting")
        timeline.append({"date": date, "targeted": targeted, "remaining": remaining, "recovered": max(0, targeted-remaining), "state": state})
    pct = round((recovered / previous_queued * 100), 1) if previous_queued else 100.0
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if current == 0 else ("progress" if recovered else "waiting"),
        "summary": {"queued": previous_queued, "recovered": recovered, "still_missing": current, "progress_pct": pct},
        "timeline": timeline,
    }


def panel(payload: dict) -> str:
    s = payload["summary"]
    rows = "".join(
        f'<div class="arp-row"><span>{"✓" if x["state"]=="complete" else "◐" if x["state"]=="partial" else "○"} {x["date"]}</span><b>{x["recovered"]}/{x["targeted"]} recovered</b><em>{x["remaining"]} missing</em></div>'
        for x in payload.get("timeline", [])
    ) or '<div class="arp-empty">No recovery dates are queued.</div>'
    state = payload["status"].upper()
    return f'''{START}
<style id="wnba-alt-recovery-progress-style">
#wnba-alt-recovery-progress{{display:none;margin:0 0 18px;padding:14px;border:1px solid #263854;border-radius:18px;background:linear-gradient(135deg,rgba(7,24,34,.98),rgba(15,28,47,.98));font-family:Inter,system-ui,sans-serif}}
.arp-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}}.arp-title{{font-size:13px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#cbd5e1}}.arp-state{{padding:5px 10px;border-radius:999px;background:#064e3b;color:#6ee7b7;font-size:11px;font-weight:900}}
.arp-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}.arp-card{{padding:12px;border:1px solid #263854;border-radius:14px;background:rgba(5,15,28,.72)}}.arp-label{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#94a3b8}}.arp-value{{margin-top:5px;font-size:20px;font-weight:900;color:#e2e8f0}}
.arp-bar{{height:10px;margin:12px 0 14px;border-radius:999px;background:#132238;overflow:hidden}}.arp-fill{{height:100%;width:{s['progress_pct']}%;background:linear-gradient(90deg,#10b981,#22d3ee)}}.arp-list{{display:grid;gap:8px}}.arp-row{{display:grid;grid-template-columns:1fr auto auto;gap:12px;padding:9px 11px;border:1px solid #263854;border-radius:12px;color:#cbd5e1;font-size:12px}}.arp-row b{{color:#6ee7b7}}.arp-row em{{color:#facc15;font-style:normal}}
@media(max-width:760px){{.arp-grid{{grid-template-columns:repeat(2,1fr)}}.arp-row{{grid-template-columns:1fr}}}}
</style>
<section id="wnba-alt-recovery-progress" aria-label="ALT auto-fix progress">
<div class="arp-head"><div class="arp-title">ALT Auto-Fix Progress</div><div class="arp-state">{state}</div></div>
<div class="arp-grid"><div class="arp-card"><div class="arp-label">Jobs queued</div><div class="arp-value">{s['queued']}</div></div><div class="arp-card"><div class="arp-label">Recovered</div><div class="arp-value">{s['recovered']}</div></div><div class="arp-card"><div class="arp-label">Still missing</div><div class="arp-value">{s['still_missing']}</div></div><div class="arp-card"><div class="arp-label">Progress</div><div class="arp-value">{s['progress_pct']}%</div></div></div>
<div class="arp-bar"><div class="arp-fill"></div></div><div class="arp-list">{rows}</div></section>
<script id="wnba-alt-recovery-progress-script">(function(){{const p=document.getElementById('wnba-alt-recovery-progress');if(!p)return;const norm=s=>(s||'').trim().toLowerCase();function vis(e){{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'}}function sync(){{const h=[...document.querySelectorAll('h1,h2,h3')].find(e=>norm(e.textContent)==='alt performance'&&vis(e));p.style.display=h?'block':'none';if(h){{const host=h.closest('section,main,div');const diag=document.getElementById('wnba-alt-pending-diagnostics');if(host&&p.parentElement!==host)host.insertBefore(p,diag?diag.nextSibling:(host.children[3]||null));}}}}document.addEventListener('click',()=>setTimeout(sync,80),true);new MutationObserver(sync).observe(document.body,{{subtree:true,childList:true,attributes:true,attributeFilter:['class','style','hidden']}});sync();setTimeout(sync,800);}})();</script>
{END}'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before")
    args = ap.parse_args()
    before = Path(args.before) if args.before else None
    payload = build(before)
    text = json.dumps(payload, indent=2) + "\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True); WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8"); WAREHOUSE.write_text(text, encoding="utf-8")
    if HTML.exists():
        html = HTML.read_text(encoding="utf-8"); block = panel(payload); pattern = re.escape(START)+r".*?"+re.escape(END)
        html = re.sub(pattern, block, html, flags=re.S) if re.search(pattern, html, flags=re.S) else html.replace("</body>", block+"\n</body>", 1)
        HTML.write_text(html, encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))

if __name__ == "__main__": main()
