"""Repository, module, data, workflow, and forward-validation QA for WNBA V4.

Uses only the Python standard library so it can run before project dependencies
are installed. Produces machine-readable JSON and a Markdown report.
"""
from __future__ import annotations

import argparse
import json
import py_compile
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "v4_modules.json"
DASHBOARD_DIR = ROOT / "data" / "dashboard"
WORKFLOW_DIR = ROOT / ".github" / "workflows"
FORWARD_DB = ROOT / "data" / "warehouse" / "wnba_forward_validation.sqlite"
READINESS = DASHBOARD_DIR / "wnba_pipeline_readiness.json"
OUTPUT_JSON = DASHBOARD_DIR / "wnba_v4_qa.json"
OUTPUT_MD = ROOT / "docs" / "V4_QA_REPORT.md"

EXPECTED_EMPTY_NAMES = {
    "wnba_daily_edges.json",
    "wnba_ensemble_intelligence.json",
    "wnba_monte_carlo_scenarios.json",
    "wnba_forward_validation.json",
    "wnba_alt_streaks.json",
    "wnba_alt_market_warehouse.json",
}
EXPECTED_EMPTY_TOKENS = (
    "daily_edges", "ensemble", "monte_carlo", "forward_validation",
    "alt_streak", "current_slate", "today", "pregame", "live_",
)


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
            "top_edges", "ranked_edges", "simulations", "predictions",
        ):
            if isinstance(value.get(key), list):
                return len(value[key])
        return 1 if value else 0
    return 0


def readiness_state() -> tuple[str, bool, str]:
    try:
        payload = read_json(READINESS)
        status = str(payload.get("status") or "UNKNOWN").upper()
        reason = str(payload.get("reason") or "")
        return status, status in {"WAIT", "OFFDAY", "NO_SLATE"}, reason
    except Exception:
        return "UNKNOWN", False, "readiness report unavailable"


def compile_python(path: Path) -> tuple[bool, str]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, ""
    except Exception as exc:
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
            "id": module.get("id"), "module": module.get("name"),
            "declared_status": declared, "owner_file": module.get("owner_file"),
            "owner_exists": exists, "syntax_ok": syntax_ok,
            "qa_score": max(0, score),
            "grade": "green" if score >= 90 else "yellow" if score >= 60 else "red",
            "issues": issues,
        })
    return results


def is_expected_empty(path: Path, offday: bool) -> bool:
    if not offday:
        return False
    name = path.name.lower()
    return name in EXPECTED_EMPTY_NAMES or any(token in name for token in EXPECTED_EMPTY_TOKENS)


def data_checks() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _, offday, _ = readiness_state()
    if not DASHBOARD_DIR.exists():
        return [{"path": str(DASHBOARD_DIR.relative_to(ROOT)), "valid": False, "issue": "directory missing"}]
    for path in sorted(DASHBOARD_DIR.glob("*.json")):
        rel = str(path.relative_to(ROOT))
        try:
            payload = read_json(path)
            rows = row_count(payload)
            expected = rows == 0 and is_expected_empty(path, offday)
            results.append({
                "path": rel, "valid": True, "bytes": path.stat().st_size,
                "rows": rows, "empty": rows == 0,
                "expected_empty": expected,
                "health_effect": "none" if expected else "warning" if rows == 0 else "none",
            })
        except Exception as exc:
            results.append({"path": rel, "valid": False, "bytes": path.stat().st_size, "rows": 0, "empty": True, "expected_empty": False, "issue": str(exc)})
    return results


def workflow_checks() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        continue_count = len(re.findall(r"continue-on-error:\s*true", text, re.I))
        run_count = len(re.findall(r"^\s*-\s+name:", text, re.M))
        ratio = round(continue_count / run_count, 3) if run_count else 0
        permissions_write = bool(re.search(r"contents:\s*write", text))
        self_push = bool(re.search(r"\bgit\s+push\b", text))
        critical_masking = bool(re.search(
            r"(?:collect|grade|freeze|publish|deploy|build\s+model|run\s+model)[^\n]*\n(?:.|\n){0,180}?continue-on-error:\s*true",
            text, re.I,
        ))
        diagnostic_heavy = bool(re.search(r"diagnostic|audit|health|fallback|optional|supplemental", text, re.I))
        if critical_masking or (continue_count >= 8 and ratio >= 0.45 and not diagnostic_heavy):
            risk = "high"
        elif continue_count >= 3 or ratio >= 0.25:
            risk = "medium"
        else:
            risk = "low"
        results.append({
            "path": str(path.relative_to(ROOT)), "steps": run_count,
            "continue_on_error": continue_count, "masked_failure_ratio": ratio,
            "critical_failure_masking": critical_masking,
            "diagnostic_or_optional": diagnostic_heavy,
            "contents_write": permissions_write, "self_push": self_push, "risk": risk,
        })
    return results


def forward_validation_checks() -> dict[str, Any]:
    report = {
        "database_exists": FORWARD_DB.exists(), "integrity": "missing",
        "table_exists": False, "records": 0, "duplicates": 0,
        "chronology_violations": 0, "immutable_identity_ready": False,
        "status": "green", "issues": [],
    }
    if not FORWARD_DB.exists():
        report["status"] = "green"
        report["issues"].append("Database not created yet; valid before first live freeze")
        return report
    try:
        con = sqlite3.connect(FORWARD_DB)
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        report["integrity"] = integrity
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        candidate = next((t for t in ("forward_predictions", "predictions", "frozen_predictions") if t in tables), None)
        report["table_exists"] = candidate is not None
        if integrity != "ok":
            report["issues"].append(f"SQLite integrity: {integrity}")
        if candidate:
            cols = {r[1] for r in con.execute(f"PRAGMA table_info({candidate})")}
            report["records"] = con.execute(f"SELECT COUNT(*) FROM {candidate}").fetchone()[0]
            id_col = next((c for c in ("prediction_id", "snapshot_id", "id") if c in cols), None)
            if id_col:
                report["duplicates"] = con.execute(f"SELECT COUNT(*)-COUNT(DISTINCT {id_col}) FROM {candidate}").fetchone()[0]
                report["immutable_identity_ready"] = True
            freeze_col = next((c for c in ("frozen_at_utc", "freeze_time_utc", "created_at_utc") if c in cols), None)
            start_col = next((c for c in ("game_start_utc", "commence_time", "start_time_utc") if c in cols), None)
            if freeze_col and start_col:
                report["chronology_violations"] = con.execute(
                    f"SELECT COUNT(*) FROM {candidate} WHERE {freeze_col} IS NOT NULL AND {start_col} IS NOT NULL AND {freeze_col} >= {start_col}"
                ).fetchone()[0]
        con.close()
    except Exception as exc:
        report["issues"].append(str(exc))
    if report["integrity"] != "ok" or report["duplicates"] or report["chronology_violations"] or report["issues"]:
        report["status"] = "red" if report["integrity"] not in {"ok", "missing"} or report["chronology_violations"] else "yellow"
    return report


def build_report() -> dict[str, Any]:
    modules = module_checks(); data = data_checks(); workflows = workflow_checks(); fv = forward_validation_checks()
    readiness, offday, readiness_reason = readiness_state()
    red = [item for item in modules if item["grade"] == "red"]
    invalid_json = [item for item in data if not item.get("valid")]
    expected_empty = [item for item in data if item.get("expected_empty")]
    unexpected_empty = [item for item in data if item.get("valid") and item.get("empty") and not item.get("expected_empty")]
    risky_workflows = [item for item in workflows if item["risk"] == "high"]
    scores = [item["qa_score"] for item in modules]
    overall = round(sum(scores) / len(scores), 1) if scores else 0
    critical = bool(red or invalid_json or fv["status"] == "red")
    warning = bool(unexpected_empty or risky_workflows or fv["status"] == "yellow")
    status = "red" if critical else "yellow" if warning else "green"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status, "overall_score": overall,
        "operating_context": {"readiness": readiness, "offday_or_break": offday, "reason": readiness_reason},
        "summary": {
            "modules": len(modules), "green_modules": sum(i["grade"] == "green" for i in modules),
            "yellow_modules": sum(i["grade"] == "yellow" for i in modules), "red_modules": len(red),
            "dashboard_json_files": len(data), "invalid_json_files": len(invalid_json),
            "empty_json_files": len(expected_empty) + len(unexpected_empty),
            "expected_empty_json_files": len(expected_empty), "unexpected_empty_json_files": len(unexpected_empty),
            "workflows": len(workflows), "high_risk_workflows": len(risky_workflows),
            "forward_validation_status": fv["status"],
        },
        "modules": modules, "data": data, "workflows": workflows,
        "forward_validation": fv,
        "release_blockers": [
            *[f"{i['id']} {i['module']}: {', '.join(i['issues'])}" for i in red],
            *[f"Invalid JSON: {i['path']}" for i in invalid_json],
            *(["Forward-validation chronology or database integrity failure"] if fv["status"] == "red" else []),
        ],
        "warnings": [
            *[f"Unexpected empty JSON: {i['path']}" for i in unexpected_empty],
            *[f"High-risk workflow: {i['path']}" for i in risky_workflows],
            *fv["issues"] if fv["status"] == "yellow" else [],
        ],
    }


def write_markdown(report: dict[str, Any]) -> None:
    s = report["summary"]
    lines = [
        "# WNBA V4 QA Report", "", f"Generated: `{report['generated_at_utc']}`", "",
        f"**Overall:** {report['status'].upper()} — {report['overall_score']}/100", "",
        f"Operating context: `{report['operating_context']['readiness']}` — {report['operating_context']['reason']}", "",
        "## Summary", "",
        f"- Modules: {s['green_modules']} green, {s['yellow_modules']} yellow, {s['red_modules']} red",
        f"- Dashboard JSON: {s['dashboard_json_files']} checked, {s['invalid_json_files']} invalid, {s['expected_empty_json_files']} expected empty, {s['unexpected_empty_json_files']} unexpected empty",
        f"- Workflows: {s['workflows']} checked, {s['high_risk_workflows']} high risk",
        f"- Forward validation: {s['forward_validation_status']}", "", "## Module QA", "",
        "| ID | Module | Declared | QA | Score | Owner |", "|---|---|---:|---:|---:|---|",
    ]
    for item in report["modules"]:
        lines.append(f"| {item['id']} | {item['module']} | {item['declared_status']} | {item['grade']} | {item['qa_score']} | `{item['owner_file']}` |")
    lines.extend(["", "## Release blockers", ""])
    lines.extend([f"- {x}" for x in report["release_blockers"]] or ["- None detected."])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {x}" for x in report["warnings"]] or ["- None detected."])
    lines.extend(["", "## Workflow risk", "", "| Workflow | Steps | Continue-on-error | Ratio | Critical masking | Risk |", "|---|---:|---:|---:|---:|---:|"])
    for item in report["workflows"]:
        lines.append(f"| `{item['path']}` | {item['steps']} | {item['continue_on_error']} | {item['masked_failure_ratio']} | {item['critical_failure_masking']} | {item['risk']} |")
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
