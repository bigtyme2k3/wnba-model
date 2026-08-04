"""Diagnose ungraded ALT archive rows and embed an interactive pending inspector."""
from __future__ import annotations

import html
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
    rows: list[dict] = []
    for line_no, line in enumerate(HISTORY.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            rows.append({"_malformed": True, "_line_no": line_no, "raw": line[:240]})
            continue
        if isinstance(obj, dict):
            obj.setdefault("_line_no", line_no)
            rows.append(obj)
    return rows


def is_graded(row: dict) -> bool:
    return str(row.get("outcome") or "").upper() in {"WIN", "LOSS", "PUSH"} or row.get("actual") is not None


def category(row: dict) -> str:
    if row.get("_malformed"):
        return "malformed_archive_row"
    reason = str(row.get("grading_reason") or row.get("pending_reason") or "").lower()
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


def expected_game_id(row: dict) -> str:
    raw = f"{row.get('date') or 'unknown'}|{row.get('game') or row.get('opponent') or 'unknown'}"
    return re.sub(r"[^a-z0-9|@]+", "-", raw.lower()).strip("-")


def inspector_row(row: dict, generated: str) -> dict:
    reason_key = category(row)
    required = bool(row.get("player") and row.get("date") and (row.get("game") or row.get("opponent")) and row.get("stat"))
    auto_fix = reason_key == "missing_verified_game_log" and required
    attempts = int(row.get("grading_attempts") or row.get("retry_attempts") or 0)
    return {
        "date": row.get("date"),
        "player": row.get("player"),
        "team": row.get("team"),
        "game": row.get("game") or row.get("opponent"),
        "stat": row.get("stat"),
        "side": row.get("side"),
        "line": row.get("alt_line") if row.get("alt_line") is not None else row.get("line"),
        "reason_key": reason_key,
        "reason": row.get("grading_reason") or row.get("pending_reason") or label(reason_key),
        "source_searched": row.get("actual_source") or "player_game_log_warehouse",
        "retry_attempts": attempts,
        "last_checked_utc": row.get("last_grading_attempt_utc") or row.get("graded_at_utc") or generated,
        "expected_game_id": expected_game_id(row),
        "auto_fix_available": auto_fix,
        "archive_line": row.get("_line_no"),
    }


def build_payload() -> dict:
    rows = load_rows()
    pending = [r for r in rows if not is_graded(r)]
    generated = datetime.now(timezone.utc).isoformat()
    counts = Counter(category(r) for r in pending)
    by_date = Counter(str(r.get("date") or "unknown") for r in pending)
    inspector = [inspector_row(r, generated) for r in pending]
    examples = defaultdict(list)
    for item in inspector:
        if len(examples[item["reason_key"]]) < 5:
            examples[item["reason_key"]].append(item)
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    reported = int((report.get("summary") or {}).get("pending") or 0)
    return {
        "generated_at_utc": generated,
        "status": "ok",
        "summary": {
            "pending_rows": len(pending),
            "reported_pending": reported,
            "reconciled": len(pending) == reported,
            "categories": len(counts),
            "oldest_pending_date": min(by_date) if by_date else None,
            "largest_category": counts.most_common(1)[0][0] if counts else None,
            "auto_fix_available": sum(1 for x in inspector if x["auto_fix_available"]),
        },
        "by_category": [{"category": k, "count": v, "examples": examples[k]} for k, v in counts.most_common()],
        "by_date": [{"date": k, "count": v} for k, v in sorted(by_date.items())],
        "inspector": inspector,
    }


def label(name: str) -> str:
    return name.replace("_", " ").title()


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def panel(payload: dict) -> str:
    s = payload["summary"]
    cats = payload.get("by_category", [])
    inspector = payload.get("inspector", [])
    category_rows = "".join(
        f'<button type="button" class="apd-row" data-reason="{esc(x["category"])}"><span>{esc(label(x["category"]))}</span><b>{x["count"]}</b></button>'
        for x in cats[:8]
    ) or '<div class="apd-empty">No pending records.</div>'
    table_rows = "".join(
        "<tr data-reason=\"{reason}\"><td>{date}</td><td>{player}</td><td>{market}</td><td>{game}</td><td>{source}</td><td>{attempts}</td><td>{checked}</td><td><code>{game_id}</code></td><td><span class=\"apd-fix {fix_cls}\">{fix}</span></td></tr>".format(
            reason=esc(x["reason_key"]),
            date=esc(x["date"] or "Unknown"),
            player=esc(x["player"] or "Unknown"),
            market=esc(f'{x["side"] or ""} {x["stat"] or ""} {x["line"] if x["line"] is not None else ""}'.strip()),
            game=esc(x["game"] or "Unknown"),
            source=esc(x["source_searched"]),
            attempts=x["retry_attempts"],
            checked=esc(str(x["last_checked_utc"])[:19].replace("T", " ")),
            game_id=esc(x["expected_game_id"]),
            fix_cls="yes" if x["auto_fix_available"] else "no",
            fix="YES" if x["auto_fix_available"] else "NO",
        ) for x in inspector
    ) or '<tr><td colspan="9">No pending records.</td></tr>'
    state = "RECONCILED" if s["reconciled"] else "COUNT MISMATCH"
    cls = "ok" if s["reconciled"] else "warn"
    return f'''{START}
<style id="wnba-alt-pending-diagnostics-style">
#wnba-alt-pending-diagnostics{{display:none;margin:0 0 18px;padding:14px;border:1px solid #263854;border-radius:18px;background:linear-gradient(135deg,rgba(9,22,38,.98),rgba(17,27,46,.98));font-family:Inter,system-ui,sans-serif}}
#wnba-alt-pending-diagnostics .apd-head{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}} .apd-title{{font-size:13px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#cbd5e1}} .apd-chip{{padding:5px 10px;border-radius:999px;font-size:11px;font-weight:900}} .apd-chip.ok{{background:#064e3b;color:#6ee7b7}} .apd-chip.warn{{background:#4a2d08;color:#facc15}}
#wnba-alt-pending-diagnostics .apd-summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px}} .apd-card{{padding:12px;border:1px solid #263854;border-radius:14px;background:rgba(5,15,28,.72)}} .apd-label{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#94a3b8}} .apd-value{{margin-top:5px;font-size:18px;font-weight:900;color:#e2e8f0}}
#wnba-alt-pending-diagnostics .apd-list{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}} .apd-row{{display:flex;width:100%;justify-content:space-between;gap:12px;padding:9px 11px;border:1px solid #263854;border-radius:12px;background:transparent;color:#cbd5e1;font-size:12px;text-align:left;cursor:pointer}} .apd-row:hover,.apd-row.active{{border-color:#10b981;background:rgba(16,185,129,.08)}} .apd-row b{{color:#facc15}}
#wnba-alt-pending-diagnostics .apd-inspector{{display:none;margin-top:14px;border:1px solid #263854;border-radius:14px;overflow:hidden}} #wnba-alt-pending-diagnostics .apd-inspector.open{{display:block}} .apd-inspector-head{{display:flex;justify-content:space-between;align-items:center;padding:11px 13px;background:rgba(5,15,28,.85)}} .apd-inspector-title{{font-weight:900;color:#e2e8f0}} .apd-close{{border:1px solid #334155;border-radius:999px;background:transparent;color:#cbd5e1;padding:5px 10px;cursor:pointer}} .apd-table-wrap{{overflow:auto;max-height:430px}} .apd-table{{width:100%;border-collapse:collapse;min-width:1180px;font-size:11px}} .apd-table th,.apd-table td{{padding:9px 10px;border-top:1px solid #1e293b;text-align:left;vertical-align:top}} .apd-table th{{position:sticky;top:0;background:#0b1728;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em}} .apd-table td{{color:#cbd5e1}} .apd-table code{{font-size:10px;color:#93c5fd}} .apd-fix{{font-weight:900}} .apd-fix.yes{{color:#6ee7b7}} .apd-fix.no{{color:#94a3b8}}
@media(max-width:760px){{#wnba-alt-pending-diagnostics .apd-summary,#wnba-alt-pending-diagnostics .apd-list{{grid-template-columns:1fr}}}}
</style>
<section id="wnba-alt-pending-diagnostics" aria-label="Pending ALT diagnostics">
<div class="apd-head"><div class="apd-title">Pending ALT Diagnostics</div><div class="apd-chip {cls}">{state}</div></div>
<div class="apd-summary"><div class="apd-card"><div class="apd-label">Pending rows</div><div class="apd-value">{s['pending_rows']}</div></div><div class="apd-card"><div class="apd-label">Reason groups</div><div class="apd-value">{s['categories']}</div></div><div class="apd-card"><div class="apd-label">Oldest date</div><div class="apd-value">{s['oldest_pending_date'] or 'None'}</div></div><div class="apd-card"><div class="apd-label">Auto-fix ready</div><div class="apd-value">{s['auto_fix_available']}</div></div></div>
<div class="apd-list">{category_rows}</div>
<div class="apd-inspector" id="wnba-alt-pending-inspector"><div class="apd-inspector-head"><div class="apd-inspector-title">Pending Inspector · <span id="apd-filter-label">All records</span></div><button class="apd-close" type="button">Close</button></div><div class="apd-table-wrap"><table class="apd-table"><thead><tr><th>Date</th><th>Player</th><th>Market</th><th>Game</th><th>Source searched</th><th>Retries</th><th>Last checked UTC</th><th>Expected game ID</th><th>Auto-fix</th></tr></thead><tbody>{table_rows}</tbody></table></div></div>
</section>
<script id="wnba-alt-pending-diagnostics-script">
(function(){{const p=document.getElementById('wnba-alt-pending-diagnostics');if(!p)return;const norm=s=>(s||'').trim().toLowerCase();function visible(el){{if(!el)return false;const r=el.getBoundingClientRect();const st=getComputedStyle(el);return r.width>0&&r.height>0&&st.display!=='none'&&st.visibility!=='hidden';}}function sync(){{const h=[...document.querySelectorAll('h1,h2,h3')].find(el=>norm(el.textContent)==='alt performance'&&visible(el));p.style.display=h?'block':'none';if(h){{const host=h.closest('section,main,div');const checkpoint=document.getElementById('wnba-alt-grading-status');if(host&&p.parentElement!==host){{const anchor=checkpoint&&checkpoint.parentElement===host?checkpoint.nextSibling:(host.children[2]||null);host.insertBefore(p,anchor);}}}}}}const inspector=p.querySelector('.apd-inspector');const labelEl=p.querySelector('#apd-filter-label');const rows=[...p.querySelectorAll('tbody tr[data-reason]')];p.querySelectorAll('.apd-row[data-reason]').forEach(btn=>btn.addEventListener('click',()=>{{const reason=btn.dataset.reason;p.querySelectorAll('.apd-row').forEach(x=>x.classList.toggle('active',x===btn));rows.forEach(r=>r.style.display=r.dataset.reason===reason?'':'none');labelEl.textContent=btn.querySelector('span').textContent;inspector.classList.add('open');inspector.scrollIntoView({{behavior:'smooth',block:'nearest'}});}}));const close=p.querySelector('.apd-close');if(close)close.addEventListener('click',()=>{{inspector.classList.remove('open');p.querySelectorAll('.apd-row').forEach(x=>x.classList.remove('active'));rows.forEach(r=>r.style.display='');}});document.addEventListener('click',()=>setTimeout(sync,80),true);new MutationObserver(sync).observe(document.body,{{subtree:true,childList:true,attributes:true,attributeFilter:['class','style','hidden']}});sync();setTimeout(sync,800);}})();
</script>
{END}'''


def main() -> None:
    payload = build_payload()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    OUTPUT.write_text(text, encoding="utf-8")
    WAREHOUSE.write_text(text, encoding="utf-8")
    if HTML.exists():
        html_text = HTML.read_text(encoding="utf-8")
        block = panel(payload)
        pattern = re.escape(START) + r".*?" + re.escape(END)
        html_text = re.sub(pattern, block, html_text, flags=re.S) if re.search(pattern, html_text, flags=re.S) else html_text.replace("</body>", block + "\n</body>", 1)
        HTML.write_text(html_text, encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
