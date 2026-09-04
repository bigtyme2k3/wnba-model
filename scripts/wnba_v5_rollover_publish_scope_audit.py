#!/usr/bin/env python3
"""Enforce the explicit publish surface for WNBA Daily Slate Rollover."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/wnba_daily_slate_rollover.yml"
ALLOWLIST = ROOT / "config/v5_rollover_derived_outputs.txt"
OWNERSHIP = ROOT / "config/v5_artifact_ownership.json"
ROLLOVER = ".github/workflows/wnba_daily_slate_rollover.yml"
ALLOWED_ROOTS = ("data/dashboard/", "data/warehouse/", "data/market/", "data/forecast/")
BROAD_ROOTS = {"data/dashboard", "data/warehouse", "data/market", "data/forecast"}
CRITICAL = {
    "data/dashboard/wnba_tab_freshness.json",
    "data/dashboard/wnba_best_bets.json",
    "data/dashboard/wnba_daily_edges.json",
    "data/dashboard/wnba_ensemble_intelligence.json",
    "data/dashboard/wnba_remaining_season_intelligence.json",
}


def load_allowlist() -> list[str]:
    if not ALLOWLIST.exists():
        raise SystemExit(f"Missing rollover allowlist: {ALLOWLIST.relative_to(ROOT)}")
    rows = []
    for raw in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        rows.append(value)
    return rows


def main() -> None:
    rows = load_allowlist()
    if not rows:
        raise SystemExit("Rollover derived-output allowlist is empty")
    if len(rows) != len(set(rows)):
        raise SystemExit("Rollover derived-output allowlist contains duplicates")

    for path in rows:
        if path in BROAD_ROOTS or path.endswith("/"):
            raise SystemExit(f"Directory publish scope is forbidden: {path}")
        if any(token in path for token in ("*", "?", "[", "]")):
            raise SystemExit(f"Glob publish scope is forbidden: {path}")
        if not path.startswith(ALLOWED_ROOTS):
            raise SystemExit(f"Rollover allowlist path is outside derived roots: {path}")

    missing = sorted(CRITICAL - set(rows))
    if missing:
        raise SystemExit(f"Critical rollover outputs missing from allowlist: {missing}")

    contract = json.loads(OWNERSHIP.read_text(encoding="utf-8"))
    protected = {
        str(item.get("artifact")): str(item.get("writer_workflow"))
        for item in contract.get("artifacts", [])
        if isinstance(item, dict) and item.get("artifact")
    }
    foreign = sorted(path for path in rows if path in protected and protected[path] != ROLLOVER)
    if foreign:
        raise SystemExit(f"Rollover allowlist contains foreign-owned protected artifacts: {foreign}")

    workflow = WORKFLOW.read_text(encoding="utf-8")
    marker = "- name: Publish derived dashboard intelligence"
    if marker not in workflow:
        raise SystemExit("Rollover publish step missing")
    publish_block = workflow.split(marker, 1)[1].split("\n      - name:", 1)[0]
    if "config/v5_rollover_derived_outputs.txt" not in publish_block:
        raise SystemExit("Rollover publish step does not load the explicit allowlist")
    if '"${DERIVED_OUTPUTS[@]}"' not in publish_block:
        raise SystemExit("Rollover publish step does not pass explicit allowlisted files")
    for root in BROAD_ROOTS:
        if f"'{root}'" in publish_block or f'"{root}"' in publish_block:
            raise SystemExit(f"Broad directory argument remains in rollover publish step: {root}")

    verification_marker = "- name: Verify derived outputs and source immutability"
    verify_block = workflow.split(verification_marker, 1)[1].split("\n      - name:", 1)[0]
    if "UNEXPECTED" not in verify_block or "v5_rollover_derived_outputs.txt" not in verify_block:
        raise SystemExit("Rollover does not fail closed on changed files outside the allowlist")

    print({
        "status": "PASS",
        "contract": "V5_ROLLOVER_EXPLICIT_PUBLISH_SCOPE",
        "allowlisted_files": len(rows),
        "broad_directory_args": 0,
        "foreign_protected_artifacts": 0,
    })


if __name__ == "__main__":
    main()
