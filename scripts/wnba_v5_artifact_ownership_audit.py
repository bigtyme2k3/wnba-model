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
    "current_slate": [
        "data/dashboard/wnba_master.json",
    ],
    "standard_props": [
        "data/dashboard/wnba_player_props.json",
    ],
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
    "forward_ledger": [
        "data/history/wnba_v5_forward_predictions.jsonl",
    ],
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
    "dashboard_freshness": [
        "data/dashboard/wnba_tab_freshness.json",
    ],
}

# These are strong shell-level signals that an artifact path appearing on a
# nearby continuation line belongs to a publish command.
WINDOW_PUBLISH_HINTS = (
    "git add",
    "atomic_generated_push.sh",
    "cp ",
    "mv ",
    "install ",
)

# Direct write APIs may contain the artifact path on the same line. Generic
# ``open(...)`` is deliberately excluded because verification code commonly
# uses json.load(open(...)) and must remain a read-only reference.
DIRECT_WRITE_PATTERNS = (
    re.compile(r"\.write_text\s*\("),
    re.compile(r"json\.dump\s*\("),
    re.compile(r"\.to_csv\s*\("),
    re.compile(r"open\s*\([^\n]*,\s*['\"](?:w|a|x)[^'\"]*['\"]"),
    re.compile(r"\.open\s*\([^\n]*['\"](?:w|a|x)[^'\"]*['\"]"),
    re.compile(r"(?:^|\s)(?:tee)(?:\s+-a)?\s+"),
    re.compile(r">{1,2}\s*[^\s]+"),
)


def line_is_publish_context(lines: list[str], idx: int) -> bool:
    """Return True only when the artifact reference is tied to a write/publish.

    Multi-line shell commands put paths on continuation lines, so look backward
    for a small number of lines for git-add/atomic-push style commands. Direct
    Python write APIs are evaluated on the artifact line itself to avoid
    classifying json.load(open(...)) verification as a publisher.
    """
    line = lines[idx].lower()
    if any(pattern.search(line) for pattern in DIRECT_WRITE_PATTERNS):
        return True

    lo = max(0, idx - 8)
    backward = "\n".join(lines[lo : idx + 1]).lower()
    return any(hint in backward for hint in WINDOW_PUBLISH_HINTS)


def main() -> int:
    rows: list[dict] = []
    by_artifact: dict[str, list[dict]] = defaultdict(list)

    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    for wf in files:
        text = wf.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
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
                        "publish_context": line_is_publish_context(lines, i),
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
