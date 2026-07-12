"""Repository, module, data, and workflow QA for WNBA V4.

Uses only the Python standard library so it can run before project dependencies
are installed. Produces machine-readable JSON and a Markdown report.
"""
from __future__ import annotations

import argparse
import json
import os
import py_compile
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "v4_modules.json"
DASHBOARD_DIR = ROOT / "data" / "dashboard"
WORKFLOW_DIR = ROOT / ".github" / "workflows"
OUTPUT_JSON = DASHBOARD_DIR / "wnba_v4_qa.json"
OUTPUT_MD = ROOT / "docs" / "V4_QA_REPORT.md"


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def row_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in (
            "rows", "games", "props", "top_decisions", "qualified_bets",
            "recommended_card", "players", "records", "items", "data",
        ):
            if isinstance(value.get(key), list):
                return len(value[key])
        return 1 if value else 0
    return 0


def compile_python(path: Path) -> tuple[bool, str]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, ""
    except Exception as exc:  # pragma: no cover - diagnostic path
        return False, str(exc)


def module_checks() -> list[dict[str, Any]]:
    config = read_json(CONFIG)
    results: list[dict[str, Any]] = []
    for module in config.get("modules", []):
        owner = ROOT / module.get("owner_file", "")
        exists = owner.is_file()
        syntax_ok = None
        syntax_error = ""
        if exists and owner.suffix == ".py":
            syntax_ok, syntax_error = compile_python(owner)
        declared = module.get("status", "planned")
        score = 100
        issues: list[str] = []
        if not exists:
            score -= 70
            issues.append("owner file missing")
        if syntax_ok is False:
            score -= 60
            issues.append(f"syntax error: {syntax_error}")
        if declared in {"active", "validated"} and not exists:
            score = 0
        results.append({
            "id": module.get("id"),
            "module": module.get("name"),
            "declared_status": declared,
            "owner_file": module.get("owner_file"),
            "owner_exists": exists,
            "syntax_ok": syntax_ok,
            "qa_score": max(0, score),
            "grade": "green" if score >= 90 else "yellow" if score >= 60 else "red",
            "issues": issues,
        })
    return results


def data_checks() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not DASHBOARD_DIR.exists():
        return [{"path": str(DASHBOARD_DIR.relative_to(ROOT)), "valid": False, "issue": "directory missing"}]
    for path in sorted(DASHBOARD_DIR.glob("*.json")):
        rel = str(path.relative_to(ROOT))
        try:
            payload = read_json(path)
            results.append({
                "path": rel,
                "valid": True,
                "bytes": path.stat().st_size,
                "rows": row_count(payload),
                "empty": row_count(payload) == 0,
            })
        except Exception as exc:
            results.append({"path": rel, "valid": False, "bytes": path.stat().st_size, "rows": 0, "empty": True, "issue": str(exc)})
    return results


def workflow_checks() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        continue_count = len(re.findall(r"continue-on-error:\s*true", text, re.I))
        run_count = len(re.findall(r"^\s*-\s+name:", text, re.M))
        permissions_write = bool(re.search(r"contents:\s*write", text))
        self_push = bool(re.search(r"\bgit\s+push\b", text))
        results.append({
            "path": str(path.relative_to(ROOT)),
            "steps": run_count,
            "continue_on_error": continue_count,
            "masked_failure_ratio": round(continue_count / run_count, 3) if run_count else 0,
            "contents_write": permissions_write,
            "self_push": self_push,
            "risk": "high" if continue_count >= 8 else "medium" if continue_count >= 3 else "low",
        })
    return results


def build_report() -> dict[str, Any]:
    modules = module_checks()
    data = data_checks()
    workflows = workflow_checks()
    red = [item for item in modules if item["grade"] == "red"]
    invalid_json = [item for item in data if not item.get("valid")]
    empty_json = [item for item in data if item.get("valid") and item.get("empty")]
    risky_workflows = [item for item in workflows if item["risk"] == "high"]
    scores = [item["qa_score"] for item in modules]
    overall = round(sum(scores) / len(scores), 1) if scores else 0
    status = "red" if red or invalid_json else "yellow" if empty_json or risky_workflows else "green"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "overall_score": overall,
        "summary": {
            "modules": len(modules),
            "green_modules": sum(item["grade"] == "green" for item in modules),
            "yellow_modules": sum(item["grade"] == "yellow" for item in modules),
            "red_modules": len(red),
            "dashboard_json_files": len(data),
            "invalid_json_files": len(invalid_json),
            "empty_json_files": len(empty_json),
            "workflows": len(workflows),
            "high_risk_workflows": len(risky_workflows),
        },
        "modules": modules,
        "data": data,
        "workflows": workflows,
        "release_blockers": [
            *[f"{item['id']} {item['module']}: {', '.join(item['issues'])}" for item in red],
            *[f"Invalid JSON: {item['path']}" for item in invalid_json],
        ],
    }


def write_markdown(report: dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        "# WNBA V4 QA Report", "",
        f"Generated: `{report['generated_at_utc']}`", "",
        f"**Overall:** {report['status'].upper()} — {report['overall_score']}/100", "",
        "## Summary", "",
        f"- Modules: {summary['green_modules']} green, {summary['yellow_modules']} yellow, {summary['red_modules']} red",
        f"- Dashboard JSON: {summary['dashboard_json_files']} checked, {summary['invalid_json_files']} invalid, {summary['empty_json_files']} empty",
        f"- Workflows: {summary['workflows']} checked, {summary['high_risk_workflows']} high risk",
        "", "## Module QA", "",
        "| ID | Module | Declared | QA | Score | Owner |", "|---|---|---:|---:|---:|---|",
    ]
    for item in report["modules"]:
        lines.append(f"| {item['id']} | {item['module']} | {item['declared_status']} | {item['grade']} | {item['qa_score']} | `{item['owner_file']}` |")
    lines.extend(["", "## Release blockers", ""])
    blockers = report["release_blockers"]
    lines.extend([f"- {blocker}" for blocker in blockers] or ["- None detected by the static QA pass."])
    lines.extend(["", "## Workflow risk", "", "| Workflow | Steps | Continue-on-error | Ratio | Risk | Self-push |", "|---|---:|---:|---:|---:|---:|"])
    for item in report["workflows"]:
        lines.append(f"| `{item['path']}` | {item['steps']} | {item['continue_on_error']} | {item['masked_failure_ratio']} | {item['risk']} | {item['self_push']} |")
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Exit non-zero for red status")
    args = parser.parse_args()
    if not CONFIG.exists():
        raise SystemExit("Missing config/v4_modules.json")
    report = build_report()
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_markdown(report)
    print(json.dumps(report["summary"], indent=2))
    print(f"V4 QA status: {report['status']} ({report['overall_score']}/100)")
    if args.strict and report["status"] == "red":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
