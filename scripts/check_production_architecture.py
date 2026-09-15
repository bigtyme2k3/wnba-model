from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / ".github" / "workflows"
DEPLOY = ACTIVE / "deploy_wnba_dashboard.yml"
ALT_MARKET_OWNER = ACTIVE / "wnba_alt_pregame_snapshot.yml"
ALT_LATE_MARKET_ENTRY = ACTIVE / "wnba-alt-late-market-refresh.yml"
ATOMIC = ROOT / "scripts" / "atomic_generated_push.sh"
ALT_RECOVERY = ROOT / "wnba_alt_game_log_recovery.py"
UPCOMING_RESOLVER = ROOT / "scripts" / "wnba_dashboard_slate_context.py"
M02_RENDERER = ROOT / "patch_dashboard_s19_m02.py"

RETIRED_DASHBOARD_BUILDERS = {
    "build_dashboard_v4.py",
    "patch_dashboard_v4_games_markets.py",
    "patch_dashboard_v4_consistency.py",
    "patch_dashboard_v4_live_slate.py",
    "patch_dashboard_v4_portfolio_ai.py",
    "patch_dashboard_navigation_v2.py",
}
REUSABLE_WRITER_OVERRIDES = {
    "wnba_v5_injury_dashboard.yml": ".github/workflows/wnba_v5_injury_dashboard.yml",
    "wnba-new-day-prediction-sync.yml": ".github/workflows/wnba-new-day-prediction-sync.yml",
    "wnba_daily_slate_rollover.yml": ".github/workflows/wnba_daily_slate_rollover.yml",
}


def fail(message: str) -> None:
    raise SystemExit(f"ARCHITECTURE GUARD FAILED: {message}")


def active_workflows() -> list[Path]:
    return sorted([*ACTIVE.glob("*.yml"), *ACTIVE.glob("*.yaml")])


def workflow_step(text: str, name: str) -> str:
    match = re.search(
        rf"^      - name: {re.escape(name)}\n(.*?)(?=^      - (?:name:|uses:)|\Z)",
        text,
        flags=re.M | re.S,
    )
    return match.group(1) if match else ""


def main() -> None:
    if not DEPLOY.exists():
        fail("canonical Deploy WNBA Dashboard workflow is missing")
    if not ATOMIC.exists():
        fail("atomic generated publisher is missing")
    if not ALT_MARKET_OWNER.exists():
        fail("canonical ALT market owner workflow is missing")
    if not ALT_LATE_MARKET_ENTRY.exists():
        fail("controlled ALT late-market entry workflow is missing")
    if not ALT_RECOVERY.exists():
        fail("ALT historical recovery planner is missing")
    if not UPCOMING_RESOLVER.exists():
        fail("prepared-upcoming dashboard resolver is missing")
    if not M02_RENDERER.exists():
        fail("Sprint 19 M02 dashboard renderer is missing")

    # Block hardcoded dates only where they are being used as execution state.
    # Documentation/comments may legitimately mention historical dates.
    hardcoded_slate_date = re.compile(
        r"(?:--date\s+|TARGET\s*=|target_date[^\n:=]*[:=]\s*['\"]?)20\d{2}-\d{2}-\d{2}",
        re.I,
    )
    # Non-deploy workflows may read docs, but they may not stage/publish either
    # docs/index.html directly or the parent docs directory through a multiline
    # command. The atomic publisher independently enforces this after expansion.
    git_add_dashboard = re.compile(
        r"git\s+add(?:(?!\n\s*-\s+name:).){0,1600}?(?:^|[\s'\"])(?:docs(?:/index\.html)?)(?=[\s'\"\\]|$)",
        re.S | re.M,
    )
    atomic_dashboard = re.compile(
        r"atomic_generated_push\.sh(?:(?!\n\s*-\s+name:).){0,1600}?(?:^|[\s'\"])(?:docs(?:/index\.html)?)(?=[\s'\"\\]|$)",
        re.S | re.M,
    )

    for workflow in active_workflows():
        text = workflow.read_text(encoding="utf-8")
        name = workflow.name

        retired = sorted(item for item in RETIRED_DASHBOARD_BUILDERS if item in text)
        if retired:
            fail(f"{name} references retired dashboard builders: {retired}")

        if hardcoded_slate_date.search(text):
            fail(f"{name} hardcodes an executable slate date")

        if "GITHUB_WORKFLOW=" in text:
            fail(f"{name} spoofs GITHUB_WORKFLOW")
        override_marker = "V5_WRITER_WORKFLOW_PATH:"
        if override_marker in text:
            expected = REUSABLE_WRITER_OVERRIDES.get(name)
            if not expected or f"{override_marker} {expected}" not in text:
                fail(f"{name} contains an unauthorized reusable-writer identity override")
        if "ALLOW_DASHBOARD_WRITE" in text:
            fail(f"{name} contains a dashboard-write bypass")
        if "date -u +%F" in text:
            fail(f"{name} contains a UTC-date slate fallback")

        if workflow != DEPLOY and (git_add_dashboard.search(text) or atomic_dashboard.search(text)):
            fail(f"{name} can publish the docs dashboard outside the canonical deploy")

    deploy_text = DEPLOY.read_text(encoding="utf-8")
    if "python active_slate_date.py" not in deploy_text:
        fail("deploy does not resolve the slate through active_slate_date.py")
    break_contract = {
        "SLATE_MODE=$(python active_slate_date.py --field mode)": "slate-mode resolution",
        "NEXT_SLATE_DATE=$(python active_slate_date.py --field next_slate_date)": "next-slate resolution",
        "MAINTENANCE_BREAK": "maintenance break gate",
        "patch_dashboard_break_state.py": "fail-closed break dashboard",
        "BREAK_MODE_DEPLOY_SAFE": "break deployment verification",
        "if: env.MAINTENANCE_BREAK != 'true'": "live-only current-market steps",
    }
    missing_break_contract = [label for marker, label in break_contract.items() if marker not in deploy_text]
    if missing_break_contract:
        fail(f"deploy is missing break-aware contracts: {missing_break_contract}")
    upcoming_contract = {
        "scripts/wnba_dashboard_slate_context.py --field target_date": "prepared-upcoming target resolution",
        "PREPARED_UPCOMING": "prepared-upcoming deployment gate",
        "DASHBOARD_MODE": "dashboard mode evidence",
        "ALT_CURRENT_SOURCE": "current ALT source gate",
        "UPCOMING_STANDARD_PROPS_ONLY": "standard-props-only upcoming state",
        "actionable_injury_unverified_props": "unverified injury actionability assertion",
    }
    missing_upcoming_contract = [label for marker, label in upcoming_contract.items() if marker not in deploy_text]
    if missing_upcoming_contract:
        fail(f"deploy is missing prepared-upcoming contracts: {missing_upcoming_contract}")

    alt_owner_text = ALT_MARKET_OWNER.read_text(encoding="utf-8")
    alt_owner_header = alt_owner_text.split("\npermissions:", 1)[0]
    alt_owner_contract = {
        "scripts/wnba_dashboard_slate_context.py --field target_date": "prepared-upcoming target resolution",
        "ALT_TARGET_MODE": "active/upcoming target-mode gate",
        "SOURCE_STACK_READY": "prepared source-stack gate",
        "ODDS_API_MIN_REMAINING: '1500'": "paid API credit reserve",
        "actions: write": "dashboard dispatch permission",
        "gh workflow run deploy_wnba_dashboard.yml --ref main": "canonical dashboard deployment dispatch",
    }
    missing_alt_owner_contract = [
        label for marker, label in alt_owner_contract.items() if marker not in alt_owner_text
    ]
    if missing_alt_owner_contract:
        fail(f"ALT market owner is missing contracts: {missing_alt_owner_contract}")
    if "\n  push:" in alt_owner_header or "\n  schedule:" in alt_owner_header:
        fail("ALT market owner must remain manual/reusable during maintenance mode")

    alt_entry_text = ALT_LATE_MARKET_ENTRY.read_text(encoding="utf-8")
    for marker, label in {
        "data/alt_late_refresh_request.txt": "controlled request marker",
        "uses: ./.github/workflows/wnba_alt_pregame_snapshot.yml": "canonical ALT owner delegation",
        "actions: write": "reusable workflow dispatch permission",
    }.items():
        if marker not in alt_entry_text:
            fail(f"ALT late-market entry is missing {label}")
    for name in (
        "Install ALT pipeline dependencies",
        "Score current ALT props",
        "Verify Sprint 19 M02-M06 dashboard routing and current slate artifact",
        "Persist Sprint 19 M06 prediction history",
    ):
        block = workflow_step(deploy_text, name)
        if not block or "if: env.MAINTENANCE_BREAK != 'true'" not in block:
            fail(f"deploy live-only step is not break-gated: {name}")
    build_block = workflow_step(deploy_text, "Build complete dashboard artifact")
    if not build_block or "patch_dashboard_break_state.py" not in build_block or "wnba_terminal_ui.py" not in build_block:
        fail("deploy build step is missing its maintenance/live branches")
    if build_block.index("patch_dashboard_break_state.py") > build_block.index("wnba_terminal_ui.py"):
        fail("deploy can enter the live dashboard build before installing break state")
    verify_break = workflow_step(deploy_text, "Verify maintenance break artifact")
    if "if: env.MAINTENANCE_BREAK == 'true'" not in verify_break or "BREAK_MODE_DEPLOY_SAFE" not in verify_break:
        fail("deploy does not independently verify the maintenance artifact")
    if "uses: actions/upload-pages-artifact@" not in deploy_text or "uses: actions/deploy-pages@" not in deploy_text:
        fail("deploy is missing the Pages artifact/deploy chain")

    resolver_text = UPCOMING_RESOLVER.read_text(encoding="utf-8")
    for marker in (
        "next_slate_source_stack_ready",
        "projection_integrity:not_clean",
        "sportsbooks:unsupported_book_observed",
        "injury_unverified:actionable_rows_present",
        "paid_api_called=False",
    ):
        if marker not in resolver_text:
            fail(f"prepared-upcoming resolver is missing {marker}")

    renderer_text = M02_RENDERER.read_text(encoding="utf-8")
    if "r.eligible_for_bet===true" not in renderer_text:
        fail("M02 renderer does not use final bet eligibility for actionable counts")
    if "if(r.eligible)counts.ACTIONABLE++" in renderer_text:
        fail("M02 renderer still labels research candidates as actionable")
    if "Official injury report unverified" not in renderer_text:
        fail("M02 renderer does not disclose unverified injury state")

    recovery_text = ALT_RECOVERY.read_text(encoding="utf-8")
    recovery_contract = {
        "resolve_slate_context": "schedule-state resolution",
        "automatic_break_pause": "automatic break pause",
        '"paused_schedule_break"': "machine-readable paused status",
        '"external_feed_calls_allowed": not automatic_break_pause': "external-feed fail-closed evidence",
        "--allow-break-recovery": "explicit operator override",
    }
    missing_recovery_contract = [
        label for marker, label in recovery_contract.items() if marker not in recovery_text
    ]
    if missing_recovery_contract:
        fail(f"ALT recovery is missing break-aware contracts: {missing_recovery_contract}")

    atomic_text = ATOMIC.read_text(encoding="utf-8")
    if 'DASHBOARD_DEPLOY_WORKFLOW="Deploy WNBA Dashboard"' not in atomic_text:
        fail("atomic publisher does not recognize the canonical deploy workflow")
    if "ALLOW_DASHBOARD_WRITE" in atomic_text:
        fail("atomic publisher still exposes a dashboard-write bypass")
    if "CANONICAL_DASHBOARD_WORKFLOW" in atomic_text or "WNBA V4 Player Props Polish" in atomic_text:
        fail("atomic publisher still contains retired dashboard workflow ownership")
    if "is_protected_dashboard_file" not in atomic_text or "Skipping protected dashboard file after path expansion" not in atomic_text:
        fail("atomic publisher does not enforce dashboard protection after path expansion")
    if "V5_WRITER_WORKFLOW_PATH" not in atomic_text or "Unknown V5 writer workflow override" not in atomic_text:
        fail("atomic publisher does not validate reusable-writer identity overrides against the ownership contract")
    for workflow_name, workflow_path in REUSABLE_WRITER_OVERRIDES.items():
        workflow_text = (ACTIVE / workflow_name).read_text(encoding="utf-8")
        if f"V5_WRITER_WORKFLOW_PATH: {workflow_path}" not in workflow_text:
            fail(f"{workflow_name} does not bind its reusable-writer identity")

    print(
        {
            "status": "PASS",
            "active_workflows_checked": len(active_workflows()),
            "single_dashboard_writer": True,
            "directory_publish_bypass_blocked": True,
            "retired_dashboard_builders_blocked": True,
            "hardcoded_executable_slate_dates_blocked": True,
            "workflow_identity_spoofing_blocked": True,
            "reusable_writer_identity_bound": True,
            "utc_rollover_fallback_blocked_globally": True,
            "break_aware_deployment_required": True,
            "stale_current_markets_blocked_during_break": True,
            "automatic_external_recovery_paused_during_break": True,
        }
    )


if __name__ == "__main__":
    main()
