#!/usr/bin/env python3
"""Surgically remove legacy push entry points from the V5 core production chain.

The four core stages remain reusable through workflow_call and operator-controlled
through workflow_dispatch. This script edits only the trigger blocks; every
other workflow line is preserved byte-for-byte.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPLACEMENTS = {
    ".github/workflows/wnba_daily_canonical_build.yml": (
        """# Maintenance mode: scheduled execution remains paused during the FIBA break.\n# This workflow owns the canonical slate, standard props, team ratings, and\n# base Sprint 2 predictions only. Injury-aware Phase 2 is a downstream consumer.\non:\n  workflow_call:\n    inputs:\n      target_date:\n        description: Optional Eastern slate date (YYYY-MM-DD)\n        required: false\n        type: string\n    secrets:\n      ODDS_API_KEY:\n        required: false\n  workflow_dispatch:\n    inputs:\n      target_date:\n        description: Optional Eastern slate date (YYYY-MM-DD)\n        required: false\n        type: string\n  push:\n    paths:\n      - 'data/daily_canonical_build_request.txt'\n      - 'scripts/build_daily_canonical_slate.py'\n      - 'wnba_player_props_ingestion.py'\n      - 'wnba_sprint2_prediction_engine.py'\n""",
        """# Maintenance mode: scheduled execution remains paused during the FIBA break.\n# This workflow owns the canonical slate, standard props, team ratings, and\n# base Sprint 2 predictions only. Production execution is explicit: reusable\n# workflow_call from the V5 orchestrator or operator workflow_dispatch only.\non:\n  workflow_call:\n    inputs:\n      target_date:\n        description: Optional Eastern slate date (YYYY-MM-DD)\n        required: false\n        type: string\n    secrets:\n      ODDS_API_KEY:\n        required: false\n  workflow_dispatch:\n    inputs:\n      target_date:\n        description: Optional Eastern slate date (YYYY-MM-DD)\n        required: false\n        type: string\n""",
    ),
    ".github/workflows/wnba_v5_injury_dashboard.yml": (
        """# Maintenance mode: scheduled polling is paused during the FIBA break.\n# This workflow owns injury context only; downstream prediction workflows\n# consume the published context and own their own artifacts.\non:\n  workflow_call:\n    inputs:\n      date:\n        description: 'Target slate date (YYYY-MM-DD); blank uses active slate'\n        required: false\n        type: string\n        default: ''\n  workflow_dispatch:\n    inputs:\n      date:\n        description: 'Target slate date (YYYY-MM-DD); blank uses active slate'\n        required: false\n        default: ''\n  push:\n    branches: [main]\n    paths:\n      - 'scrape_official_wnba_injuries.py'\n      - 'scrape_injuries.py'\n      - 'wnba_injury_intelligence.py'\n      - 'wnba_injury_rotation_guard.py'\n      - 'scripts/wnba_new_day_injury_refresh.py'\n      - 'active_slate_date.py'\n      - 'scripts/check_production_architecture.py'\n      - '.github/workflows/wnba_v5_injury_dashboard.yml'\n""",
        """# Maintenance mode: scheduled polling is paused during the FIBA break.\n# This workflow owns injury context only; downstream prediction workflows\n# consume the published context and own their own artifacts. Production\n# execution is workflow_call from the V5 orchestrator or manual dispatch only.\non:\n  workflow_call:\n    inputs:\n      date:\n        description: 'Target slate date (YYYY-MM-DD); blank uses active slate'\n        required: false\n        type: string\n        default: ''\n  workflow_dispatch:\n    inputs:\n      date:\n        description: 'Target slate date (YYYY-MM-DD); blank uses active slate'\n        required: false\n        default: ''\n""",
    ),
    ".github/workflows/wnba-new-day-prediction-sync.yml": (
        """# Maintenance mode: scheduled retries remain paused during the FIBA break.\n# Production execution is allowed only through workflow_call or manual dispatch;\n# code/data pushes may validate the workflow definition but never run the writer.\non:\n  workflow_call:\n    inputs:\n      date:\n        description: Optional Eastern target date (YYYY-MM-DD)\n        required: false\n        type: string\n        default: ''\n      deploy_dashboard:\n        description: Dispatch the dashboard after this stage\n        required: false\n        type: boolean\n        default: true\n    secrets:\n      ODDS_API_KEY:\n        required: false\n  workflow_dispatch:\n    inputs:\n      date:\n        description: Optional Eastern target date (YYYY-MM-DD)\n        required: false\n        default: ''\n      deploy_dashboard:\n        description: Dispatch dashboard after prediction publish\n        required: false\n        type: boolean\n        default: true\n  push:\n    branches: [main]\n    paths:\n      - 'data/new_day_prediction_sync_request.txt'\n      - 'scripts/wnba_sprint2_phase2.py'\n      - 'scripts/wnba_s19_m02_prop_source.py'\n      - 'scripts/wnba_s19_m02_predictions.py'\n      - 'wnba_game_predictions_ledger.py'\n""",
        """# Maintenance mode: scheduled retries remain paused during the FIBA break.\n# Production execution is allowed only through workflow_call from the V5\n# orchestrator or explicit operator workflow_dispatch. No push event can start\n# this writer.\non:\n  workflow_call:\n    inputs:\n      date:\n        description: Optional Eastern target date (YYYY-MM-DD)\n        required: false\n        type: string\n        default: ''\n      deploy_dashboard:\n        description: Dispatch the dashboard after this stage\n        required: false\n        type: boolean\n        default: true\n    secrets:\n      ODDS_API_KEY:\n        required: false\n  workflow_dispatch:\n    inputs:\n      date:\n        description: Optional Eastern target date (YYYY-MM-DD)\n        required: false\n        default: ''\n      deploy_dashboard:\n        description: Dispatch dashboard after prediction publish\n        required: false\n        type: boolean\n        default: true\n""",
    ),
    ".github/workflows/wnba_daily_slate_rollover.yml": (
        """# Maintenance mode: scheduled rollover remains paused during the WNBA/FIBA\n# break. Canonical slate, injury, prediction, ALT, grading, and forward-evidence\n# artifacts are owned by their dedicated workflows. This workflow consumes\n# those sources and refreshes only derived dashboard intelligence.\non:\n  workflow_call:\n    inputs:\n      target_date:\n        description: Optional authoritative slate date (YYYY-MM-DD)\n        required: false\n        type: string\n        default: ''\n  workflow_dispatch:\n    inputs:\n      target_date:\n        description: Optional authoritative slate date (YYYY-MM-DD)\n        required: false\n        type: string\n        default: ''\n  push:\n    paths:\n      - 'data/dashboard_refresh_request.txt'\n""",
        """# Maintenance mode: scheduled rollover remains paused during the WNBA/FIBA\n# break. Canonical slate, injury, prediction, ALT, grading, and forward-evidence\n# artifacts are owned by their dedicated workflows. This workflow consumes\n# those sources and refreshes only derived dashboard intelligence. Production\n# execution is workflow_call from the V5 orchestrator or manual dispatch only.\non:\n  workflow_call:\n    inputs:\n      target_date:\n        description: Optional authoritative slate date (YYYY-MM-DD)\n        required: false\n        type: string\n        default: ''\n  workflow_dispatch:\n    inputs:\n      target_date:\n        description: Optional authoritative slate date (YYYY-MM-DD)\n        required: false\n        type: string\n        default: ''\n""",
    ),
}


def main() -> int:
    changed = []
    for rel, (old, new) in REPLACEMENTS.items():
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        if old in text:
            updated = text.replace(old, new, 1)
            # The prediction workflow no longer needs a push-event runtime guard.
            if rel.endswith("wnba-new-day-prediction-sync.yml"):
                updated = updated.replace("  sync:\n    if: ${{ github.event_name != 'push' }}\n", "  sync:\n", 1)
            path.write_text(updated, encoding="utf-8")
            changed.append(rel)
            continue
        if new in text:
            continue
        raise SystemExit(f"Refusing unsafe edit; expected trigger block not found in {rel}")

    print({"status": "PASS", "changed": changed, "count": len(changed)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
