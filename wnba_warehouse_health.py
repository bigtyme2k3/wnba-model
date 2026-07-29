"""Audit WNBA warehouse, dashboard, and master datasets for freshness and integrity."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
GROUPS = {
    "dashboard": ROOT / "data" / "dashboard",
    "master": ROOT / "data" / "master",
    "warehouse": ROOT / "data" / "warehouse",
}
OUT_JSON = ROOT / "data" / "dashboard" / "wnba_warehouse_health.json"
OUT_MD = ROOT / "docs" / "WAREHOUSE_HEALTH_REPORT.md"


def parse_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        datetime.fromisoformat(text)
        return text
    except ValueError:
        return None


def nonempty_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    return 0


def inspect_file(group: str, path: Path, expected_date: str | None) -> dict[str, Any]:
    stat = path.stat()
    record: dict[str, Any] = {
        "group": group,
        "path": str(path.relative_to(ROOT)),
        "bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "status": "green",
        "findings": [],
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        record["status"] = "red"
        record["findings"].append(f"invalid_json: {exc}")
        return record

    record["top_level_type"] = type(payload).__name__
    record["top_level_count"] = nonempty_count(payload)
    if not payload:
        record["status"] = "yellow"
        record["findings"].append("empty_payload")

    if isinstance(payload, dict):
        target_date = parse_date(payload.get("target_date") or payload.get("date"))
        record["target_date"] = target_date
        if expected_date and target_date and target_date != expected_date:
            record["status"] = "yellow"
            record["findings"].append(f"target_date_mismatch:{target_date}!={expected_date}")
        if payload.get("schema_version") is not None:
            record["schema_version"] = payload.get("schema_version")
    return record


def audit() -> dict[str, Any]:
    expected_date = None
    master_path = GROUPS["master"] / "wnba_master.json"
    if master_path.exists():
        try:
            expected_date = parse_date(json.loads(master_path.read_text(encoding="utf-8")).get("target_date"))
        except Exception:
            pass

    files: list[dict[str, Any]] = []
    for group, directory in GROUPS.items():
        if not directory.exists():
            files.append({
                "group": group,
                "path": str(directory.relative_to(ROOT)),
                "status": "red",
                "findings": ["missing_directory"],
            })
            continue
        for path in sorted(directory.glob("*.json")):
            files.append(inspect_file(group, path, expected_date))

    duplicates: list[dict[str, Any]] = []
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in files:
        name = Path(row["path"]).name
        by_name.setdefault(name, []).append(row)
    for name, rows in sorted(by_name.items()):
        if len(rows) > 1:
            duplicates.append({"name": name, "paths": [r["path"] for r in rows]})

    red = sum(row.get("status") == "red" for row in files)
    yellow = sum(row.get("status") == "yellow" for row in files)
    status = "red" if red else "yellow" if yellow else "green"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_target_date": expected_date,
        "status": status,
        "summary": {
            "files": len(files),
            "green": sum(row.get("status") == "green" for row in files),
            "yellow": yellow,
            "red": red,
            "duplicate_names": len(duplicates),
        },
        "duplicates": duplicates,
        "files": files,
    }


def write_report(result: dict[str, Any]) -> None:
    lines = [
        "# WNBA Warehouse Health Report",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        f"Expected target date: `{result.get('expected_target_date')}`",
        f"Overall status: **{result['status'].upper()}**",
        "",
        "## Summary",
        "",
    ]
    for key, value in result["summary"].items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    lines += ["", "## Dataset Status", "", "| Status | Group | Path | Target date | Findings |", "|---|---|---|---|---|"]
    for row in result["files"]:
        findings = ", ".join(row.get("findings", [])) or "None"
        lines.append(f"| {row.get('status','unknown').upper()} | {row.get('group','')} | `{row.get('path','')}` | {row.get('target_date','')} | {findings} |")
    lines += ["", "## Duplicate Dataset Names", ""]
    if result["duplicates"]:
        for item in result["duplicates"]:
            lines.append(f"- `{item['name']}`: {', '.join(item['paths'])}")
    else:
        lines.append("- None detected.")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = audit()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_report(result)
    print(json.dumps(result["summary"], indent=2))
    if args.strict and result["status"] == "red":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
