#!/usr/bin/env python3
"""Static inventory of production artifact ownership and workflow schedules.

This is intentionally read-only. It scans only .github/workflows (never the
archive) and records workflows that reference protected canonical artifacts,
with stronger evidence when the reference appears in an actual publish/write
context. Read-only verification must not be classified as ownership.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
OUT_JSON = ROOT / "data" / "dashboard" / "wnba_v5_artifact_ownership_audit.json"
OUT_CSV = ROOT / "data" / "dashboard" / "wnba_v5_artifact_ownership_audit.csv"

PROTECTED = {
    "current_slate": ["data/dashboard/wnba_master.json"],
    "standard_props": ["data/dashboard/wnba_player_props.json"],
    "injury_context": [
        "data/dashboard/wnba_injury_intelligence.json",
        "data/warehouse/wnba_injury_intelligence.json",
    ],
    "game_predictions": [
        "data/dashboard/wnba_sprint2_predictions.json",
        "data/dashboard/wnba_sprint2_phase2.json",
    ],
    "m02_predictions": [
        "data/dashboard/wnba_s19_m02_predictions.json",
        "data/dashboard/wnba_s19_m02_prediction_audit.json",
    ],
    "forward_ledger": ["data/history/wnba_v5_forward_predictions.jsonl"],
    "closing_lines": [
        "data/dashboard/wnba_v5_explicit_clv.json",
        "data/history/wnba_v5_closing_lines.jsonl",
    ],
    "results": [
        "data/dashboard/wnba_results_grading.json",
        "data/history/wnba_model_history.jsonl",
    ],
    "alt_market": [
        "data/dashboard/wnba_alt_market_warehouse.json",
        "data/warehouse/wnba_alt_market_warehouse.json",
    ],
    "dashboard_freshness": ["data/dashboard/wnba_tab_freshness.json"],
}

# Shell commands that publish a list of artifacts. A command may continue for
# dozens of lines, so fixed look-back windows are not reliable.
SHELL_PUBLISH_START = (
    "git add",
    "atomic_generated_push.sh",
)

DIRECT_WRITE_PATTERNS = (
    re.compile(r"\.write_text\s*\("),
    re.compile(r"json\.dump\s*\("),
    re.compile(r"\.to_csv\s*\("),
    re.compile(r"open\s*\([^\n]*,\s*['\"](?:w|a|x)[^'\"]*['\"]"),
    re.compile(r"\.open\s*\([^\n]*['\"](?:w|a|x)[^'\"]*['\"]"),
    re.compile(r"(?:^|\s)tee(?:\s+-a)?\s+"),
    re.compile(r">{1,2}\s*[^\s]+"),
    re.compile(r"(?:^|\s)(?:cp|mv|install)\s+"),
)

CRON_RE = re.compile(r"^\s*(?:-\s*)?cron:\s*['\"]?([^'\"#]+?)['\"]?\s*(?:#.*)?$")
NAME_RE = re.compile(r"^\s*name:\s*['\"]?(.+?)['\"]?\s*$")


def shell_publish_line_indexes(lines: list[str]) -> set[int]:
    """Return all line indexes belonging to git-add/atomic-push commands."""
    indexes: set[int] = set()
    active = False
    for idx, raw in enumerate(lines):
        text = raw.strip()
        lower = text.lower()
        if not active and any(hint in lower for hint in SHELL_PUBLISH_START):
            active = True
        if active:
            indexes.add(idx)
            # YAML block-shell continuation commands use a trailing backslash.
            # The first non-continuation line terminates the artifact list.
            if not text.endswith("\\"):
                active = False
    return indexes


def line_is_publish_context(lines: list[str], idx: int, shell_publish_lines: set[int]) -> bool:
    if idx in shell_publish_lines:
        return True
    line = lines[idx].lower()
    return any(pattern.search(line) for pattern in DIRECT_WRITE_PATTERNS)


def workflow_name(lines: list[str], fallback: str) -> str:
    for raw in lines[:20]:
        match = NAME_RE.match(raw)
        if match:
            return match.group(1).strip()
    return fallback


def scheduled_entry(wf: Path, lines: list[str], text: str) -> dict | None:
    crons: list[str] = []
    for raw in lines:
        if raw.lstrip().startswith("#"):
            continue
        match = CRON_RE.match(raw)
        if match:
            cron = match.group(1).strip()
            if cron and cron not in crons:
                crons.append(cron)
    if not crons:
        return None

    lower = text.lower()
    paid_markers = (
        "odds_api_key",
        "scrape_odds_props_consensus.py",
        "the odds api",
        "paid request",
    )
    live_markers = (
        "live inference",
        "closing capture",
        "current slate",
        "injury",
        "results refresh",
        "market refresh",
        "rollover",
    )
    return {
        "workflow": str(wf.relative_to(ROOT)),
        "name": workflow_name(lines, wf.stem),
        "crons": crons,
        "cron_count": len(crons),
        "paid_api_risk": any(marker in lower for marker in paid_markers),
        "live_pipeline_risk": any(marker in lower for marker in live_markers),
    }


def main() -> int:
    rows: list[dict] = []
    by_artifact: dict[str, list[dict]] = defaultdict(list)
    scheduled_workflows: list[dict] = []

    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    for wf in files:
        text = wf.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        shell_lines = shell_publish_line_indexes(lines)
        scheduled = scheduled_entry(wf, lines, text)
        if scheduled:
            scheduled_workflows.append(scheduled)

        for domain, artifacts in PROTECTED.items():
            for artifact in artifacts:
                for i, line in enumerate(lines):
                    if artifact not in line:
                        continue
                    evidence = {
                        "domain": domain,
                        "artifact": artifact,
                        "workflow": str(wf.relative_to(ROOT)),
                        "line": i + 1,
                        "publish_context": line_is_publish_context(lines, i, shell_lines),
                        "snippet": line.strip()[:240],
                    }
                    rows.append(evidence)
                    by_artifact[artifact].append(evidence)

    summary = []
    conflicts = []
    for domain, artifacts in PROTECTED.items():
        for artifact in artifacts:
            refs = by_artifact.get(artifact, [])
            workflows = sorted({r["workflow"] for r in refs})
            publishers = sorted({r["workflow"] for r in refs if r["publish_context"]})
            item = {
                "domain": domain,
                "artifact": artifact,
                "workflow_references": workflows,
                "publish_workflows": publishers,
                "reference_count": len(refs),
                "publish_workflow_count": len(publishers),
                "status": "MULTIPLE_PUBLISHERS" if len(publishers) > 1 else "SINGLE_OR_NO_PUBLISHER",
            }
            summary.append(item)
            if len(publishers) > 1:
                conflicts.append(item)

    paid_scheduled = [item for item in scheduled_workflows if item["paid_api_risk"]]
    live_scheduled = [item for item in scheduled_workflows if item["live_pipeline_risk"]]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "REVIEW_REQUIRED" if conflicts else "PASS",
        "mode": "inventory_only",
        "scope": ".github/workflows only; .github/workflows-archive excluded",
        "protected_artifact_count": sum(len(v) for v in PROTECTED.values()),
        "active_workflow_count": len(files),
        "multiple_publisher_count": len(conflicts),
        "multiple_publishers": conflicts,
        "scheduled_workflow_count": len(scheduled_workflows),
        "scheduled_paid_api_risk_count": len(paid_scheduled),
        "scheduled_live_pipeline_risk_count": len(live_scheduled),
        "scheduled_workflows": scheduled_workflows,
        "artifacts": summary,
        "evidence": rows,
        "notes": [
            "This audit is static and intentionally conservative.",
            "Read-only open/json.load references are not publisher evidence.",
            "Multi-line git-add and atomic-push artifact lists are parsed through their full continuation block.",
            "Cron inventory includes only uncommented cron entries in active workflow files.",
            "paid_api_risk/live_pipeline_risk are keyword-based triage hints, not blocking findings.",
            "A MULTIPLE_PUBLISHERS result is a consolidation target, not proof of runtime corruption.",
            "Do not convert this inventory into a blocking gate until authoritative writers are finalized.",
        ],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["domain", "artifact", "workflow", "line", "publish_context", "snippet"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({
        "status": payload["status"],
        "active_workflows": payload["active_workflow_count"],
        "protected_artifacts": payload["protected_artifact_count"],
        "multiple_publisher_count": payload["multiple_publisher_count"],
        "scheduled_workflow_count": payload["scheduled_workflow_count"],
        "scheduled_paid_api_risk_count": payload["scheduled_paid_api_risk_count"],
        "scheduled_live_pipeline_risk_count": payload["scheduled_live_pipeline_risk_count"],
        "output": str(OUT_JSON.relative_to(ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
