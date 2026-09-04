#!/usr/bin/env python3
"""Blocking static contract for V5 core production entry points.

During maintenance mode, the reusable production stages may be invoked only by
workflow_call or explicit workflow_dispatch. The V5 daily orchestrator is the
single top-level production entry point and itself remains manual-only with
live_mode defaulting to false.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STAGES = [
    ".github/workflows/wnba_daily_canonical_build.yml",
    ".github/workflows/wnba_v5_injury_dashboard.yml",
    ".github/workflows/wnba-new-day-prediction-sync.yml",
    ".github/workflows/wnba_daily_slate_rollover.yml",
]
ORCHESTRATOR = ".github/workflows/wnba-v5-daily-orchestrator.yml"


def trigger_header(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if "\non:\n" not in text:
        raise AssertionError(f"Missing on: block: {path.relative_to(ROOT)}")
    if "\npermissions:" not in text:
        raise AssertionError(f"Missing permissions boundary: {path.relative_to(ROOT)}")
    return text.split("\npermissions:", 1)[0]


def main() -> int:
    checks = []
    for rel in STAGES:
        path = ROOT / rel
        header = trigger_header(path)
        stage_checks = {
            "workflow_call": "\n  workflow_call:" in header,
            "workflow_dispatch": "\n  workflow_dispatch:" in header,
            "no_push": "\n  push:" not in header,
            "no_schedule": "\n  schedule:" not in header,
        }
        checks.append({"workflow": rel, "role": "stage", "checks": stage_checks})

    orch_path = ROOT / ORCHESTRATOR
    orch_header = trigger_header(orch_path)
    orch_text = orch_path.read_text(encoding="utf-8")
    orch_checks = {
        "workflow_dispatch": "\n  workflow_dispatch:" in orch_header,
        "no_push": "\n  push:" not in orch_header,
        "no_schedule": "\n  schedule:" not in orch_header,
        "no_workflow_call": "\n  workflow_call:" not in orch_header,
        "live_mode_input": "live_mode:" in orch_header,
        "live_mode_default_false": "default: false" in orch_header,
    }
    checks.append({"workflow": ORCHESTRATOR, "role": "orchestrator", "checks": orch_checks})

    failures = []
    for item in checks:
        for name, ok in item["checks"].items():
            if not ok:
                failures.append({"workflow": item["workflow"], "check": name})

    payload = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "maintenance",
        "core_stage_count": len(STAGES),
        "top_level_entrypoint": ORCHESTRATOR,
        "failures": failures,
        "workflows": checks,
    }
    print(json.dumps(payload, indent=2))
    if failures:
        raise SystemExit("V5 core entrypoint contract violation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
