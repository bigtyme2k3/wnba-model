#!/usr/bin/env python3
"""Static inventory of production artifact ownership across active workflows.

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


def main() -> int:
    rows: list[dict] = []
    by_artifact: dict[str, list[dict]] = defaultdict(list)

    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    for wf in files:
        text = wf.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        shell_lines = shell_publish_line_indexes(lines)
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

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "REVIEW_REQUIRED" if conflicts else "PASS",
        "mode": "inventory_only",
        "scope": ".github/workflows only; .github/workflows-archive excluded",
        "protected_artifact_count": sum(len(v) for v in PROTECTED.values()),
        "active_workflow_count": len(files),
        "multiple_publisher_count": len(conflicts),
        "multiple_publishers": conflicts,
        "artifacts": summary,
        "evidence": rows,
        "notes": [
            "This audit is static and intentionally conservative.",
            "Read-only open/json.load references are not publisher evidence.",
            "Multi-line git-add and atomic-push artifact lists are parsed through their full continuation block.",
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
        "output": str(OUT_JSON.relative_to(ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
