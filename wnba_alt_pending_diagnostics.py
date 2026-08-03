"""Diagnose ungraded ALT archive rows and embed a screenshot-verifiable panel."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HISTORY = Path("data/history/wnba_alt_streak_history.jsonl")
REPORT = Path("data/dashboard/wnba_alt_performance.json")
OUTPUT = Path("data/dashboard/wnba_alt_pending_diagnostics.json")
WAREHOUSE = Path("data/warehouse/wnba_alt_pending_diagnostics.json")
HTML = Path("docs/index.html")
START = "<!-- WNBA_ALT_PENDING_DIAGNOSTICS_START -->"
END = "<!-- WNBA_ALT_PENDING_DIAGNOSTICS_END -->"


def load_rows() -> list[dict]:
    if not HISTORY.exists():
        return []
    rows=[]
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if not line:
            continue
        try:
            obj=json.loads(line)
        except json.JSONDecodeError:
            rows.append({"_malformed": True, "raw": line[:240]})
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def is_graded(row: dict) -> bool:
    return str(row.get("outcome") or "").upper() in {"WIN","LOSS","PUSH"} or row.get("actual") is not None


def category(row: dict) -> str:
    if row.get("_malformed"):
        return "malformed_archive_row"
    reason=str(row.get("grading_reason") or row.get("pending_reason") or "").lower()
    if "postpon" in reason or "cancel" in reason:
        return "postponed_or_cancelled"
    if "duplicate" in reason:
        return "duplicate_prediction"
    if "stat" in reason and ("map" in reason or "unsupported" in reason):
        return "stat_mapping_failure"
    if "player" in reason and ("map" in reason or "match" in reason):
        return "player_mapping_failure"
    if "game" in reason and ("map" in reason or "match" in reason or "date" in reason):
        return "game_or_date_mapping_failure"
    if "log" in reason or "actual" in reason or "result" in reason:
        return "missing_verified_game_log"
    if not row.get("player"):
        return "missing_player_name"
    if not (row.get("game") or row.get("opponent")):
        return "missing_game_identity"
    if not row.get("date"):
        return "missing_game_date"
    if not row.get("stat"):
        return "missing_stat_market"
    if row.get("actual_source") is None:
        return "missing_verified_game_log"
    return "unclassified_pending"


def build_payload() -> dict:
    rows=load_rows()
    pending=[r for r in rows if not is_graded(r)]
    counts=Counter(category(r) for r in pending)
    by_date=Counter(str(r.get("date") or "unknown") for r in pending)
    examples=defaultdict(list)
    for r in pending:
        c=category(r)
        if len(examples[c])<5:
            examples[c].append({
                "player": r.get("player"), "date": r.get("date"), "game": r.get("game") or r.get("opponent"),
                "stat": r.get("stat"), "side": r.get("side"), "line": r.get("alt_line") or r.get("line"),
                "reason": r.get("grading_reason") or r.get("pending_reason")
            })
    report=json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    reported=int((report.get("summary") or {}).get("pending") or 0)
    payload={
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "summary": {
            "pending_rows": len(pending),
            "reported_pending": reported,
            "reconciled": len(pending)==reported,
            "categories": len(counts),
            "oldest_pending_date": min(by_date) if by_date else None,
            "largest_category": counts.most_common(1)[0][0] if counts else None,
        },
        "by_category": [{"category": k, "count": v, "examples": examples[k]} for k,v in counts.most_common()],
        "by_date": [{"date": k, "count": v} for k,v in sorted(by_date.items())],
    }
    return payload


def label(name: str) -> str:
    return name.replace("_", " ").title()


def panel(payload: dict) -> str:
    s=payload["summary"]
    cats=payload.get("by_category", [])
    rows="".join(f'<div class="apd-row"><span>{label(x["category"])}</span><b>{x["count"]}</b></div>' for x in cats[:8]) or '<div class="apd-empty">No pending records.</div>'
    state="RECONCILED" if s["reconciled"] else "COUNT MISMATCH"
    cls="ok" if s["reconciled"] else "warn"
    return f'''{START}
<style id="wnba-alt-pending-diagnostics-style">
#wnba-alt-pending-diagnostics{{display:none;margin:0 0 18px;padding:14px;border:1px solid #263854;border-radius:18px;background:linear-gradient(135deg,rgba(9,22,38,.98),rgba(17,27,46,.98));font-family:Inter,system-ui,sans-serif}}
#wnba-alt-pending-diagnostics .apd-head{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}} .apd-title{{font-size:13px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#cbd5e1}} .apd-chip{{padding:5px 10px;border-radius:999px;font-size:11px;font-weight:900}} .apd-chip.ok{{background:#064e3b;color:#6ee7b7}} .apd-chip.warn{{background:#4a2d08;color:#facc15}}
#wnba-alt-pending-diagnostics .apd-summary{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:12px}} .apd-card{{padding:12px;border:1px solid #263854;border-radius:14px;background:rgba(5,15,28,.72)}} .apd-label{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#94a3b8}} .apd-value{{margin-top:5px;font-size:18px;font-weight:900;color:#e2e8f0}}
#wnba-alt-pending-diagnostics .apd-list{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}} .apd-row{{display:flex;justify-content:space-between;gap:12px;padding:9px 11px;border:1px solid #263854;border-radius:12px;color:#cbd5e1;font-size:12px}} .apd-row b{{color:#facc15}}
@media(max-width:760px){{#wnba-alt-pending-diagnostics .apd-summary,#wnba-alt-pending-diagnostics .apd-list{{grid-template-columns:1fr}}}}
</style>
<section id="wnba-alt-pending-diagnostics" aria-label="Pending ALT diagnostics">
<div class="apd-head"><div class="apd-title">Pending ALT Diagnostics</div><div class="apd-chip {cls}">{state}</div></div>
<div class="apd-summary"><div class="apd-card"><div class="apd-label">Pending rows</div><div class="apd-value">{s['pending_rows']}</div></div><div class="apd-card"><div class="apd-label">Reason groups</div><div class="apd-value">{s['categories']}</div></div><div class="apd-card"><div class="apd-label">Oldest date</div><div class="apd-value">{s['oldest_pending_date'] or 'None'}</div></div></div>
<div class="apd-list">{rows}</div></section>
<script id="wnba-alt-pending-diagnostics-script">
(function(){{const p=document.getElementById('wnba-alt-pending-diagnostics');if(!p)return;const norm=s=>(s||'').trim().toLowerCase();function visible(el){{if(!el)return false;const r=el.getBoundingClientRect();const st=getComputedStyle(el);return r.width>0&&r.height>0&&st.display!=='none'&&st.visibility!=='hidden';}}function sync(){{const h=[...document.querySelectorAll('h1,h2,h3')].find(el=>norm(el.textContent)==='alt performance'&&visible(el));p.style.display=h?'block':'none';if(h){{const host=h.closest('section,main,div');const checkpoint=document.getElementById('wnba-alt-grading-status');if(host&&p.parentElement!==host){{const anchor=checkpoint&&checkpoint.parentElement===host?checkpoint.nextSibling:(host.children[2]||null);host.insertBefore(p,anchor);}}}}}}document.addEventListener('click',()=>setTimeout(sync,80),true);new MutationObserver(sync).observe(document.body,{{subtree:true,childList:true,attributes:true,attributeFilter:['class','style','hidden']}});sync();setTimeout(sync,800);}})();
</script>
{END}'''


def main() -> None:
    payload=build_payload()
    OUTPUT.parent.mkdir(parents=True,exist_ok=True); WAREHOUSE.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(payload,indent=2)+"\n"; OUTPUT.write_text(text,encoding="utf-8"); WAREHOUSE.write_text(text,encoding="utf-8")
    if HTML.exists():
        html=HTML.read_text(encoding="utf-8"); block=panel(payload); pattern=re.escape(START)+r".*?"+re.escape(END)
        html=re.sub(pattern,block,html,flags=re.S) if re.search(pattern,html,flags=re.S) else html.replace("</body>",block+"\n</body>",1)
        HTML.write_text(html,encoding="utf-8")
    print(json.dumps(payload["summary"],indent=2))

if __name__=="__main__": main()
