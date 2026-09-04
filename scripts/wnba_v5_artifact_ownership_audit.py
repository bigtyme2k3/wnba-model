#!/usr/bin/env python3
"""Static WNBA V5 artifact-ownership and schedule contract audit.

The authoritative contract lives in config/v5_artifact_ownership.json. This
scanner inspects active workflows only (.github/workflows, never the archive),
records references and publish evidence, and reports any ownership or
maintenance-schedule contract violation.

The workflow that runs this script is responsible for turning a non-PASS report
into a blocking CI failure after publishing the diagnostic artifact.
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
CONTRACT_PATH = ROOT / "config" / "v5_artifact_ownership.json"
OUT_JSON = ROOT / "data" / "dashboard" / "wnba_v5_artifact_ownership_audit.json"
OUT_CSV = ROOT / "data" / "dashboard" / "wnba_v5_artifact_ownership_audit.csv"

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


def load_contract() -> dict:
    if not CONTRACT_PATH.exists():
        raise SystemExit(f"Missing ownership contract: {CONTRACT_PATH.relative_to(ROOT)}")
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if int(payload.get("schema_version") or 0) != 1:
        raise SystemExit("Unsupported V5 ownership contract schema")
    artifacts = payload.get("artifacts") or []
    if not artifacts:
        raise SystemExit("V5 ownership contract contains no protected artifacts")
    seen: set[str] = set()
    for item in artifacts:
        artifact = str(item.get("artifact") or "")
        writer = str(item.get("writer_workflow") or "")
        domain = str(item.get("domain") or "")
        if not artifact or not writer or not domain:
            raise SystemExit(f"Invalid ownership contract row: {item}")
        if artifact in seen:
            raise SystemExit(f"Duplicate protected artifact in ownership contract: {artifact}")
        seen.add(artifact)
    return payload


def shell_publish_line_indexes(lines: list[str]) -> set[int]:
    """Return line indexes belonging to git-add/atomic-push commands."""
    indexes: set[int] = set()
    active = False
    for idx, raw in enumerate(lines):
        text = raw.strip()
        lower = text.lower()
        if not active and any(hint in lower for hint in SHELL_PUBLISH_START):
            active = True
        if active:
            indexes.add(idx)
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
    contract = load_contract()
    protected = contract["artifacts"]
    rows: list[dict] = []
    by_artifact: dict[str, list[dict]] = defaultdict(list)
    scheduled_workflows: list[dict] = []

    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    workflow_paths = {str(path.relative_to(ROOT)) for path in files}

    for wf in files:
        text = wf.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        shell_lines = shell_publish_line_indexes(lines)
        scheduled = scheduled_entry(wf, lines, text)
        if scheduled:
            scheduled_workflows.append(scheduled)

        for contract_row in protected:
            domain = contract_row["domain"]
            artifact = contract_row["artifact"]
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

    summary: list[dict] = []
    violations: list[dict] = []

    for contract_row in protected:
        domain = contract_row["domain"]
        artifact = contract_row["artifact"]
        expected_writer = contract_row["writer_workflow"]
        refs = by_artifact.get(artifact, [])
        workflows = sorted({r["workflow"] for r in refs})
        publishers = sorted({r["workflow"] for r in refs if r["publish_context"]})
        unexpected_publishers = [wf for wf in publishers if wf != expected_writer]
        checks = {
            "writer_workflow_exists": expected_writer in workflow_paths,
            "writer_references_artifact": expected_writer in workflows,
            "no_unexpected_publishers": not unexpected_publishers,
            "no_multiple_observed_publishers": len(publishers) <= 1,
        }
        item = {
            "domain": domain,
            "artifact": artifact,
            "expected_writer": expected_writer,
            "workflow_references": workflows,
            "observed_publish_workflows": publishers,
            "unexpected_publish_workflows": unexpected_publishers,
            "reference_count": len(refs),
            "observed_publish_workflow_count": len(publishers),
            "checks": checks,
            "status": "PASS" if all(checks.values()) else "VIOLATION",
        }
        summary.append(item)
        if item["status"] != "PASS":
            violations.append({
                "type": "ARTIFACT_OWNERSHIP",
                "domain": domain,
                "artifact": artifact,
                "expected_writer": expected_writer,
                "failed_checks": [name for name, ok in checks.items() if not ok],
                "unexpected_publish_workflows": unexpected_publishers,
            })

    paid_scheduled = [item for item in scheduled_workflows if item["paid_api_risk"]]
    live_scheduled = [item for item in scheduled_workflows if item["live_pipeline_risk"]]

    maintenance = contract.get("maintenance_contract") or {}
    if str(contract.get("mode") or "").lower() == "maintenance":
        observed = {
            "scheduled_workflow_count": len(scheduled_workflows),
            "scheduled_paid_api_risk_count": len(paid_scheduled),
            "scheduled_live_pipeline_risk_count": len(live_scheduled),
        }
        for key, expected in maintenance.items():
            if key not in observed:
                continue
            if int(observed[key]) != int(expected):
                violations.append({
                    "type": "MAINTENANCE_SCHEDULE",
                    "metric": key,
                    "expected": int(expected),
                    "observed": int(observed[key]),
                })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not violations else "FAIL",
        "mode": "contract_enforced",
        "contract_mode": contract.get("mode"),
        "contract_schema_version": contract.get("schema_version"),
        "contract_path": str(CONTRACT_PATH.relative_to(ROOT)),
        "scope": ".github/workflows only; .github/workflows-archive excluded",
        "protected_artifact_count": len(protected),
        "active_workflow_count": len(files),
        "ownership_violation_count": sum(v["type"] == "ARTIFACT_OWNERSHIP" for v in violations),
        "schedule_violation_count": sum(v["type"] == "MAINTENANCE_SCHEDULE" for v in violations),
        "violation_count": len(violations),
        "violations": violations,
        "scheduled_workflow_count": len(scheduled_workflows),
        "scheduled_paid_api_risk_count": len(paid_scheduled),
        "scheduled_live_pipeline_risk_count": len(live_scheduled),
        "scheduled_workflows": scheduled_workflows,
        "artifacts": summary,
        "evidence": rows,
        "notes": [
            "The machine-readable ownership contract is authoritative.",
            "Every expected writer must exist and reference its protected artifact.",
            "Any observed publish path from a workflow other than the declared writer is blocking.",
            "Read-only references are allowed for consumers.",
            "Multi-line git-add and atomic-push artifact lists are parsed through their full continuation block.",
            "Some broad-directory publishers are not inferable statically; the declared writer plus explicit protected-path checks are the enforcement boundary.",
            "Maintenance mode requires the configured schedule counts, currently zero active crons.",
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
        "ownership_violation_count": payload["ownership_violation_count"],
        "schedule_violation_count": payload["schedule_violation_count"],
        "scheduled_workflow_count": payload["scheduled_workflow_count"],
        "scheduled_paid_api_risk_count": payload["scheduled_paid_api_risk_count"],
        "scheduled_live_pipeline_risk_count": payload["scheduled_live_pipeline_risk_count"],
        "output": str(OUT_JSON.relative_to(ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
