#!/usr/bin/env python3
"""Enforce the explicit publish surface for WNBA Daily Slate Rollover."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/wnba_daily_slate_rollover.yml"
ALLOWLIST = ROOT / "config/v5_rollover_derived_outputs.txt"
OWNERSHIP = ROOT / "config/v5_artifact_ownership.json"
FRESHNESS = ROOT / "scripts/wnba_v5_tab_freshness.py"
PROJECTION_AUDIT = ROOT / "scripts/wnba_v5_projection_integrity_audit.py"
PROJECTION_CONTRACT = ROOT / "wnba_projection_contract.py"
M02_PREDICTIONS = ROOT / "scripts/wnba_s19_m02_predictions.py"
DAILY_EDGE = ROOT / "wnba_daily_edge_engine.py"
ENSEMBLE = ROOT / "wnba_ensemble_intelligence_engine.py"
MONTE_CARLO = ROOT / "wnba_monte_carlo_scenario_engine.py"
CURRENT_SLATE = ROOT / "wnba_current_slate.py"
ROLLOVER = ".github/workflows/wnba_daily_slate_rollover.yml"
ALLOWED_ROOTS = ("data/dashboard/", "data/warehouse/", "data/market/", "data/forecast/")
BROAD_ROOTS = {"data/dashboard", "data/warehouse", "data/market", "data/forecast"}
CRITICAL = {
    "data/dashboard/wnba_tab_freshness.json",
    "data/dashboard/wnba_best_bets.json",
    "data/dashboard/wnba_daily_edges.json",
    "data/dashboard/wnba_ensemble_intelligence.json",
    "data/dashboard/wnba_projection_integrity_audit.json",
    "data/dashboard/wnba_remaining_season_intelligence.json",
}
# These files are retired, alternate-purpose, or superseded fallbacks. They may
# remain in repository history, but cannot be used to prove a current tab fresh.
FORBIDDEN_FRESHNESS_FALLBACKS = {
    "wnba_current_slate.json",
    "wnba_daily_report.json",
    "wnba_games.json",
    "wnba_unified_simulation.json",
    "wnba_portfolio.json",
    "wnba_portfolio_intelligence.json",
    "wnba_alt_market_watch.json",
    "wnba_alt_pending_diagnostics.json",
    "wnba_daily_edge_engine.json",
    "wnba_ensemble.json",
    "wnba_results.json",
    "wnba_live_results.json",
    "wnba_model_performance.json",
    "wnba_explainability.json",
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

    # Every declared rollover stage must exist. run_if_present is only a runtime
    # convenience for optional execution, not permission to accumulate dead
    # legacy stage names that silently skip forever.
    stage_scripts = sorted(set(re.findall(r"run_if_present\s+([A-Za-z0-9_./-]+\.py)", workflow)))
    missing_stage_scripts = [script for script in stage_scripts if not (ROOT / script).is_file()]
    if missing_stage_scripts:
        raise SystemExit(f"Rollover references missing stage scripts: {missing_stage_scripts}")

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

    freshness_cmd = 'python scripts/wnba_v5_tab_freshness.py --date "$TARGET"'
    if freshness_cmd not in workflow:
        raise SystemExit("Rollover does not use the semantic V5 freshness builder")
    if not FRESHNESS.is_file():
        raise SystemExit("Semantic V5 freshness builder is missing")

    projection_cmd = 'python scripts/wnba_v5_projection_integrity_audit.py --date "$TARGET"'
    if projection_cmd not in workflow:
        raise SystemExit("Rollover does not enforce projection integrity before publish")
    if not PROJECTION_AUDIT.is_file() or not PROJECTION_CONTRACT.is_file():
        raise SystemExit("Projection integrity audit or shared contract is missing")
    if "data/dashboard/wnba_projection_integrity_audit.json" not in verify_block:
        raise SystemExit("Rollover does not verify the persisted projection-integrity result")
    projection_source = PROJECTION_AUDIT.read_text(encoding="utf-8")
    for required in ("projection_field_violations", "violation_count", "failure_action", "return 0 if"):
        if required not in projection_source:
            raise SystemExit(f"Projection integrity audit missing required gate behavior: {required}")

    chain_sources = (M02_PREDICTIONS, DAILY_EDGE, ENSEMBLE, MONTE_CARLO, CURRENT_SLATE)
    if not all(path.is_file() for path in chain_sources):
        raise SystemExit("Projection-integrity chain is missing a required producer or consumer")
    m02_source = M02_PREDICTIONS.read_text(encoding="utf-8")
    daily_source = DAILY_EDGE.read_text(encoding="utf-8")
    ensemble_source = ENSEMBLE.read_text(encoding="utf-8")
    monte_source = MONTE_CARLO.read_text(encoding="utf-8")
    current_slate_source = CURRENT_SLATE.read_text(encoding="utf-8")
    if m02_source.count("validate_projection(") < 2:
        raise SystemExit("M02 issuance does not validate projection bounds")
    if (
        "wnba_s19_m02_predictions.json" not in daily_source
        or not re.search(r"['\"]legacy_master_props_used['\"]\s*:\s*False", daily_source)
    ):
        raise SystemExit("Daily edges are not pinned to canonical M02 projections")
    if "wnba_master.json" in daily_source:
        raise SystemExit("Daily edges reintroduced the retired embedded master-props path")
    if "validate_projection" not in ensemble_source:
        raise SystemExit("Ensemble does not revalidate projection bounds")
    if (
        "validate_projection" not in monte_source
        or not re.search(r"['\"]daily_edges_fallback_used['\"]\s*:\s*False", monte_source)
        or "wnba_daily_edges.json" in monte_source
    ):
        raise SystemExit("Monte Carlo does not enforce its canonical validated ensemble source")
    if current_slate_source.count("retire_legacy_betting_views(") < 3:
        raise SystemExit("Current-slate refresh no longer clears retired embedded betting views")

    freshness_source = FRESHNESS.read_text(encoding="utf-8")
    stale_refs = sorted(
        name for name in FORBIDDEN_FRESHNESS_FALLBACKS
        if name in freshness_source or name in workflow
    )
    if stale_refs:
        raise SystemExit(f"Forbidden artifacts remain in freshness resolution: {stale_refs}")
    for required in (
        "artifact_metadata",
        "git_commit",
        "target_mismatch",
        "missing_required_target_date",
        "BAD_ARTIFACT_STATUSES",
        "failed_or_standby_artifact",
        "fetch_failed",
        "retired_no_active_producer",
    ):
        if required not in freshness_source:
            raise SystemExit(f"Semantic freshness guard missing required evidence path: {required}")

    print({
        "status": "PASS",
        "contract": "V5_ROLLOVER_EXPLICIT_PUBLISH_SCOPE",
        "allowlisted_files": len(rows),
        "declared_stage_scripts": len(stage_scripts),
        "missing_stage_scripts": 0,
        "semantic_freshness": True,
        "projection_integrity_gate": True,
        "projection_chain_fail_closed": True,
        "forbidden_freshness_fallbacks": 0,
        "current_slate_target_required": True,
        "producer_failure_states_rejected": True,
        "broad_directory_args": 0,
        "foreign_protected_artifacts": 0,
    })


if __name__ == "__main__":
    main()
