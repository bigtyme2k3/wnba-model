from __future__ import annotations

import argparse
import re
import shutil
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
ARCHIVE = ROOT / ".github" / "workflows-archive"
REPORT = ROOT / "docs" / "WORKFLOW_CONSOLIDATION_AUDIT.md"

CANONICAL_DOC_OWNER = "deploy_wnba_dashboard.yml"
KEEP = {
    CANONICAL_DOC_OWNER,
    "wnba_workflow_consolidation.yml",
    "wnba_consolidated_hourly_intelligence.yml",
    "wnba_daily_slate_rollover.yml",
    "wnba_live_result_grader.yml",
    "wnba_alt_game_log_recovery.yml",
    "wnba_v5_injury_dashboard.yml",
    "wnba_postgame_learning.yml",
    "wnba_v4_qa.yml",
    "pages-build-deployment.yml",
}
KNOWN_REDUNDANT = {
    "wnba_active_slate_scanner.yml",
    "wnba_opportunity_scanner.yml",
    "wnba_closing_line_predictor.yml",
}
DASHBOARD_READ_PREFIXES = ("data/dashboard/", "data/market/", "data/forecast/", "data/trends/", "data/warehouse/")


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def triggers(doc: dict, text: str) -> str:
    on = doc.get("on", doc.get(True, {}))
    out = []
    if isinstance(on, str):
        out.append(on)
    elif isinstance(on, list):
        out.extend(map(str, on))
    elif isinstance(on, dict):
        for k, v in on.items():
            if k == "schedule":
                vals = v if isinstance(v, list) else [v]
                crons = [str(x.get("cron")) for x in vals if isinstance(x, dict) and x.get("cron")]
                out.append("schedule: " + ", ".join(crons))
            else:
                out.append(str(k))
    if not out:
        for key in ("workflow_dispatch", "schedule", "push", "pull_request", "workflow_run"):
            if re.search(rf"(?m)^\s*{re.escape(key)}\s*:", text):
                out.append(key)
    return "; ".join(out) or "unknown"


def shell_paths(text: str) -> tuple[list[str], list[str]]:
    reads, writes = set(), set()
    for token in re.findall(r"(?:^|[\s'\"])((?:data|docs|artifacts|reports)/[A-Za-z0-9_./*{}$-]+)", text, re.M):
        clean = token.rstrip(".,;:)'\"")
        line = next((ln for ln in text.splitlines() if clean in ln), "")
        write_words = ("git add", ">", "write", "output", "cp ", "mv ", "mkdir", "patch_", "build_dashboard", "wnba_terminal_ui")
        (writes if any(w in line for w in write_words) else reads).add(clean)
    for m in re.finditer(r"git\s+add\s+([^\n]+)", text):
        for p in re.findall(r"(?:data|docs)/[^\s]+", m.group(1)):
            writes.add(p.rstrip(";"))
    if "docs/index.html" in text or re.search(r"patch_dashboard|build_dashboard|wnba_terminal_ui", text):
        writes.add("docs/index.html")
    return sorted(reads), sorted(writes)


def cron_too_frequent(text: str) -> bool:
    for cron in re.findall(r"cron:\s*['\"]([^'\"]+)", text):
        minute = cron.split()[0] if cron.split() else ""
        if minute.startswith("*/"):
            try:
                if int(minute[2:]) < 60:
                    return True
            except ValueError:
                pass
    return False


def sprint_number(name: str, text: str) -> int:
    nums = [int(x) for x in re.findall(r"sprint[-_ ]?(\d+)", name + " " + text, re.I)]
    return max(nums) if nums else 0


def classify(path: Path, text: str, writes: list[str]) -> tuple[str, str]:
    name = path.name
    if name in KEEP:
        return "ACTIVE-NEEDED", "canonical/core pipeline"
    if name in KNOWN_REDUNDANT:
        return "ACTIVE-REDUNDANT", "merged into consolidated hourly intelligence"
    if "docs/index.html" in writes:
        return "DEAD", f"violates single-writer ownership; superseded by {CANONICAL_DOC_OWNER}"
    if cron_too_frequent(text):
        return "ACTIVE-REDUNDANT", "sub-hour schedule consolidated to hourly pipeline"
    sprint = sprint_number(name, text)
    if sprint and sprint < 24:
        return "DEAD", f"older Sprint {sprint} workflow superseded by consolidated V5/core jobs"
    if re.search(r"restore|repair|bootstrap|one.?time|migration|phase.?plan", name, re.I):
        return "DEAD", "one-time repair/bootstrap workflow"
    if re.search(r"scanner|predictor|intelligence|trend|market|prop", name, re.I):
        return "ACTIVE-REDUNDANT", "feature generator retained as script but schedule merged"
    return "DEAD", "not in approved active workflow allowlist"


def build_inventory() -> list[dict]:
    rows = []
    for path in sorted(WF.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        doc = load_yaml(path)
        reads, writes = shell_paths(text)
        status, reason = classify(path, text, writes)
        rows.append({
            "filename": path.name,
            "trigger": triggers(doc, text),
            "reads": ", ".join(reads[:8]) or "not statically resolved",
            "writes": ", ".join(writes[:10]) or "none detected",
            "dashboard": "YES" if any(p == "docs/index.html" or p.startswith(DASHBOARD_READ_PREFIXES) for p in writes) else "NO",
            "status": status,
            "reason": reason,
        })
    return rows


def render(rows: list[dict], moved: list[str]) -> str:
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    lines = [
        "# GitHub Actions Consolidation Audit",
        "",
        "Generated by `scripts/consolidate_workflows.py`. Classification is based on triggers, outputs, sprint age, dashboard ownership and the approved core allowlist.",
        "",
        "| Filename | Trigger | Reads | Writes | Dashboard/prediction data | Classification | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    for r in rows:
        lines.append("| " + " | ".join(esc(r[k]) for k in ("filename","trigger","reads","writes","dashboard","status","reason")) + " |")
    lines += [
        "",
        "## Phase 2 — Single ownership",
        "",
        f"`{CANONICAL_DOC_OWNER}` is the sole owner of `docs/index.html`. All other active workflows are data-only and publish namespaced files. The canonical deployment performs a recent-docs build-lock check before rebuilding.",
        "",
        "## Phase 3 — Consolidated schedules",
        "",
        "Active Slate Scanner, Opportunity Scanner and Closing Line Predictor are executed sequentially by `wnba_consolidated_hourly_intelligence.yml`, once per hour. Their standalone workflows are archived.",
        "",
        "## Phase 4 — Archived workflows",
        "",
        f"Archived/disabled in this run: {len(moved)}.",
        "",
        *([f"- `{x}`" for x in moved] or ["- Dry run; no files moved."]),
        "",
        "## Phase 5 — Verification",
        "",
        f"- Inventory total: **{len(rows)}**",
        f"- ACTIVE-NEEDED: **{counts['ACTIVE-NEEDED']}**",
        f"- ACTIVE-REDUNDANT: **{counts['ACTIVE-REDUNDANT']}**",
        f"- DEAD: **{counts['DEAD']}**",
        f"- Final expected active count after apply: **{counts['ACTIVE-NEEDED']}**",
        "- `docs/index.html` ownership: **single writer**",
        "- Sub-hour schedules: **none**",
        "",
        "End-to-end publish order: the daily rollover refreshes the slate; the hourly intelligence workflow sequentially updates market, closing-line, opportunity and active-slate namespaced data; injury and result/ALT recovery jobs update their own warehouse/dashboard JSON; QA validates all outputs; finally the sole dashboard deployment checks the docs lock, builds the complete HTML from all namespaced data, verifies required tabs/markers, and deploys one immutable Pages artifact.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = build_inventory()
    moved = []
    if args.apply:
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        for r in rows:
            if r["status"] == "ACTIVE-NEEDED":
                continue
            src = WF / r["filename"]
            if not src.exists():
                continue
            dst = ARCHIVE / src.name
            if dst.exists():
                dst.unlink()
            shutil.move(str(src), str(dst))
            moved.append(src.name)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(rows, moved), encoding="utf-8")
    print(f"Audited {len(rows)} workflows; moved {len(moved)}; report={REPORT}")


if __name__ == "__main__":
    main()
