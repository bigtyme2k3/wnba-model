#!/usr/bin/env python3
"""Block implausible projections from active WNBA V5 decision artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wnba_projection_contract import (  # noqa: E402
    PROJECTION_FIELDS,
    canonical_stat,
    projection_evidence,
    projection_field_violations,
)

OUT = ROOT / "data/dashboard/wnba_projection_integrity_audit.json"
ARTIFACTS = (
    ("data/dashboard/wnba_master.json", "props", True),
    ("data/dashboard/wnba_s19_m02_predictions.json", "player_props", True),
    ("data/dashboard/wnba_daily_edges.json", "top_edges", True),
    ("data/warehouse/wnba_daily_edges.json", "top_edges", True),
    ("data/dashboard/wnba_ensemble_intelligence.json", "ranked_edges", True),
    ("data/warehouse/wnba_ensemble_intelligence.json", "ranked_edges", True),
    ("data/dashboard/wnba_monte_carlo_scenarios.json", "all_simulations", True),
    ("data/warehouse/wnba_monte_carlo_scenarios.json", "all_simulations", True),
    ("data/dashboard/wnba_best_bets.json", "best_bets", False),
    ("data/dashboard/wnba_forward_validation.json", "recent_predictions", True),
    ("data/warehouse/wnba_forward_validation.json", "recent_predictions", True),
)


def load(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def projection_row(row: dict[str, Any], field: str) -> tuple[dict[str, Any] | None, str | None]:
    if field != "recent_predictions":
        return row, None
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except Exception:
        return None, "invalid_payload_json"
    return (payload, None) if isinstance(payload, dict) else (None, "invalid_payload_shape")


def inspect(target: str = "") -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    rows_checked = 0
    projection_fields_checked = 0

    for relative_path, field, projection_required in ARTIFACTS:
        path = ROOT / relative_path
        data = load(path)
        if data is None:
            violations.append({"artifact": relative_path, "reason": "missing_or_invalid_json"})
            artifacts.append({"artifact": relative_path, "field": field, "status": "FAIL", "rows": 0})
            continue

        artifact_target = str(data.get("target_date") or "")[:10]
        artifact_violations = 0
        if target and field != "recent_predictions" and artifact_target != target:
            violations.append({
                "artifact": relative_path,
                "reason": "target_date_mismatch",
                "expected": target,
                "actual": artifact_target or None,
            })
            artifact_violations += 1

        raw_rows = data.get(field, [])
        if not isinstance(raw_rows, list):
            violations.append({"artifact": relative_path, "reason": f"{field}_not_a_list"})
            artifact_violations += 1
            raw_rows = []

        for index, raw_row in enumerate(raw_rows):
            rows_checked += 1
            if not isinstance(raw_row, dict):
                violations.append({"artifact": relative_path, "field": field, "index": index, "reason": "row_not_an_object"})
                artifact_violations += 1
                continue
            row, payload_error = projection_row(raw_row, field)
            if row is None:
                violations.append({"artifact": relative_path, "field": field, "index": index, "reason": payload_error})
                artifact_violations += 1
                continue

            evidence = projection_evidence(row)
            if evidence is None:
                if projection_required:
                    violations.append({
                        "artifact": relative_path,
                        "field": field,
                        "index": index,
                        "player": row.get("player"),
                        "reason": "missing_projection",
                    })
                    artifact_violations += 1
                continue

            stat = canonical_stat(row.get("market") or row.get("stat") or row.get("prop_type"))
            if not stat:
                violations.append({
                    "artifact": relative_path,
                    "field": field,
                    "index": index,
                    "player": row.get("player"),
                    "reason": "missing_stat_for_projection",
                })
                artifact_violations += 1
                continue

            populated = sum(
                row.get(name) not in (None, "")
                for name in PROJECTION_FIELDS
            )
            projection_fields_checked += populated
            for item in projection_field_violations(row, stat):
                violations.append({
                    "artifact": relative_path,
                    "field": field,
                    "index": index,
                    "player": row.get("player"),
                    "stat": stat,
                    **item,
                })
                artifact_violations += 1

        artifacts.append({
            "artifact": relative_path,
            "field": field,
            "target_date": artifact_target or None,
            "status": "PASS" if artifact_violations == 0 else "FAIL",
            "rows": len(raw_rows),
            "violation_count": artifact_violations,
        })

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target or None,
        "status": "PASS" if not violations else "FAIL",
        "contract": {
            "module": "wnba_projection_contract.py",
            "policy": "Every published single-player counting-stat projection must be finite, non-negative, and below its generous stat ceiling.",
            "failure_action": "quarantine and block publish; never clamp or simulate an implausible high value",
        },
        "artifact_count": len(ARTIFACTS),
        "rows_checked": rows_checked,
        "projection_fields_checked": projection_fields_checked,
        "violation_count": len(violations),
        "violations": violations[:100],
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    report = inspect(args.date)
    if not args.no_write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "artifacts": report["artifact_count"],
        "rows_checked": report["rows_checked"],
        "projection_fields_checked": report["projection_fields_checked"],
        "violations": report["violation_count"],
    }, indent=2))
    if report["violations"]:
        print(json.dumps(report["violations"][:20], indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
