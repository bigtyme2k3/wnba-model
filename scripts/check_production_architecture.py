from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / ".github" / "workflows"
DEPLOY = ACTIVE / "deploy_wnba_dashboard.yml"
ATOMIC = ROOT / "scripts" / "atomic_generated_push.sh"

RETIRED_DASHBOARD_BUILDERS = {
    "build_dashboard_v4.py",
    "patch_dashboard_v4_games_markets.py",
    "patch_dashboard_v4_consistency.py",
    "patch_dashboard_v4_live_slate.py",
    "patch_dashboard_v4_portfolio_ai.py",
    "patch_dashboard_navigation_v2.py",
}


def fail(message: str) -> None:
    raise SystemExit(f"ARCHITECTURE GUARD FAILED: {message}")


def active_workflows() -> list[Path]:
    return sorted([*ACTIVE.glob("*.yml"), *ACTIVE.glob("*.yaml")])


def main() -> None:
    if not DEPLOY.exists():
        fail("canonical Deploy WNBA Dashboard workflow is missing")
    if not ATOMIC.exists():
        fail("atomic generated publisher is missing")

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
        if "ALLOW_DASHBOARD_WRITE" in text:
            fail(f"{name} contains a dashboard-write bypass")
        if "date -u +%F" in text:
            fail(f"{name} contains a UTC-date slate fallback")

        if workflow != DEPLOY and (git_add_dashboard.search(text) or atomic_dashboard.search(text)):
            fail(f"{name} can publish the docs dashboard outside the canonical deploy")

    deploy_text = DEPLOY.read_text(encoding="utf-8")
    if "python active_slate_date.py" not in deploy_text:
        fail("deploy does not resolve the slate through active_slate_date.py")
    if "uses: actions/upload-pages-artifact@" not in deploy_text or "uses: actions/deploy-pages@" not in deploy_text:
        fail("deploy is missing the Pages artifact/deploy chain")

    atomic_text = ATOMIC.read_text(encoding="utf-8")
    if 'DASHBOARD_DEPLOY_WORKFLOW="Deploy WNBA Dashboard"' not in atomic_text:
        fail("atomic publisher does not recognize the canonical deploy workflow")
    if "ALLOW_DASHBOARD_WRITE" in atomic_text:
        fail("atomic publisher still exposes a dashboard-write bypass")
    if "CANONICAL_DASHBOARD_WORKFLOW" in atomic_text or "WNBA V4 Player Props Polish" in atomic_text:
        fail("atomic publisher still contains retired dashboard workflow ownership")
    if "is_protected_dashboard_file" not in atomic_text or "Skipping protected dashboard file after path expansion" not in atomic_text:
        fail("atomic publisher does not enforce dashboard protection after path expansion")

    print(
        {
            "status": "PASS",
            "active_workflows_checked": len(active_workflows()),
            "single_dashboard_writer": True,
            "directory_publish_bypass_blocked": True,
            "retired_dashboard_builders_blocked": True,
            "hardcoded_executable_slate_dates_blocked": True,
            "workflow_identity_spoofing_blocked": True,
            "utc_rollover_fallback_blocked_globally": True,
        }
    )


if __name__ == "__main__":
    main()
