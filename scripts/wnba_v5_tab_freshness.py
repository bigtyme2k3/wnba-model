#!/usr/bin/env python3
"""Build V5 dashboard freshness + UI-tab activity manifests from semantic metadata.

Two separate questions are tracked:
1) module freshness (internal producer health);
2) UI tab activity (is every routed dashboard tab backed by a valid source).

The UI activity map intentionally follows the locked 13-tab router rather than
legacy tab names. Archive tabs may remain active with older target dates when
that is semantically correct, while current-slate tabs must prove TARGET.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "data/dashboard"
OUT = DASHBOARD / "wnba_tab_freshness.json"
MAX_AGE_MINUTES = 180.0
MAX_FUTURE_SKEW_MINUTES = 5.0

# Backward-compatible semantic audit marker. The old Portfolio producer was retired\n# under this reason, but the current Portfolio UI route is active from Phase 2 state.\nLEGACY_RETIRED_REASON = "retired_no_active_producer"\n
TAB_CONFIG: dict[str, dict[str, Any]] = {
    "games": {"candidates": ["wnba_master.json"], "require_target": True},
    "game_props": {"candidates": ["wnba_game_props.json", "wnba_game_prop_intelligence.json"], "require_target": True},
    "player_props": {"candidates": ["wnba_player_props.json", "wnba_player_prop_intelligence.json"], "require_target": True},
    "alt_streaks": {"candidates": ["wnba_alt_streaks.json"], "require_target": True},
    "alt_performance": {"candidates": ["wnba_alt_performance.json"], "require_target": True},
    "daily_edges": {"candidates": ["wnba_daily_edges.json"], "require_target": True},
    "ensemble": {"candidates": ["wnba_ensemble_intelligence.json"], "require_target": True},
    "simulation": {"candidates": ["wnba_monte_carlo_scenarios.json"], "require_target": True},
    "best_bets": {"candidates": ["wnba_best_bets.json", "wnba_sprint2_phase2.json"], "require_target": True},
    # Portfolio is an active routed view assembled from current Phase 2 candidates.
    "portfolio": {"candidates": ["wnba_sprint2_phase2.json"], "require_target": True},
    # Results is an archive/lifecycle view: its artifact target may be yesterday.
    "results": {
        "candidates": ["wnba_s19_m06_results_lifecycle.json", "wnba_results_grading.json"],
        "require_target": False,
        "max_age_minutes": 10080.0,
    },
    "performance": {"candidates": ["wnba_game_performance.json"], "require_target": False, "max_age_minutes": 10080.0},
    # The routed AI Center is built from current Phase 2 state, not the retired reasoning-layer snapshot.
    "explainability": {"candidates": ["wnba_sprint2_phase2.json"], "require_target": True},
    "remaining_season": {"candidates": ["wnba_remaining_season_intelligence.json"], "require_target": True, "max_age_minutes": 1440.0},
    # Market timeline is an accumulating dataset and does not carry a slate target.
    "market_intelligence": {
        "candidates": ["wnba_market_timeline_summary.json", "wnba_line_movement_summary.json"],
        "require_target": False,
    },
    "injuries": {"candidates": ["wnba_injury_intelligence.json"], "require_target": True},
}

# Mirrors patch_dashboard_v4_ui_freeze.py exactly.
UI_TAB_CONFIG: dict[str, dict[str, Any]] = {
    "games": {"label": "Games", "candidates": ["wnba_master.json"], "require_target": True},
    "game-performance": {
        "label": "Game Performance",
        "candidates": ["wnba_game_performance.json"],
        "require_target": False,
        "max_age_minutes": 10080.0,
    },
    "matchups": {"label": "Matchups", "candidates": ["wnba_sprint2_phase2.json"], "require_target": True},
    "props": {"label": "Player Props", "candidates": ["wnba_player_props.json"], "require_target": True},
    # ALT route reconstructs current ladders from canonical current-slate prop quotes.
    "alt-props": {"label": "ALT Props", "candidates": ["wnba_player_props.json"], "require_target": True},
    "sportsbooks": {"label": "Sportsbooks", "candidates": ["wnba_player_props.json"], "require_target": True},
    "best": {"label": "Best Bets", "candidates": ["wnba_sprint2_phase2.json"], "require_target": True},
    "ai": {"label": "AI Center", "candidates": ["wnba_sprint2_phase2.json"], "require_target": True},
    "live": {"label": "Live", "candidates": ["wnba_master.json"], "require_target": True},
    "remaining": {
        "label": "Remaining Season",
        "candidates": ["wnba_remaining_season_intelligence.json"],
        "require_target": True,
        "max_age_minutes": 1440.0,
    },
    "results": {
        "label": "Results",
        "candidates": ["wnba_s19_m06_results_lifecycle.json", "wnba_results_grading.json"],
        "require_target": False,
        "max_age_minutes": 10080.0,
    },
    "portfolio": {"label": "Portfolio", "candidates": ["wnba_sprint2_phase2.json"], "require_target": True},
    "health": {
        "label": "Data Health",
        "candidates": ["wnba_daily_canonical_manifest.json", "wnba_v5_current_data_health.json"],
        "require_target": True,
        "max_age_minutes": 1440.0,
    },
}

TARGET_KEYS = ("target_date", "slate_date", "date")
TIME_KEYS = (
    "generated_at_utc",
    "generated_at",
    "updated_at_utc",
    "updated_at",
    "last_updated_utc",
    "last_updated",
    "captured_at_utc",
)
BAD_ARTIFACT_STATUSES = {
    "error", "failed", "failure", "fetch_failed", "invalid", "missing",
    "stale", "standby", "unavailable",
}


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def artifact_target(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in TARGET_KEYS:
        value = payload.get(key)
        if value:
            return str(value)[:10]
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in TARGET_KEYS:
            value = summary.get(key)
            if value:
                return str(value)[:10]
    return None


def artifact_time(payload: Any) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for key in TIME_KEYS:
        parsed = parse_time(payload.get(key))
        if parsed:
            return parsed
    return None


def artifact_health(payload: Any) -> tuple[str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None
    raw_status = payload.get("status")
    status = str(raw_status).strip() if raw_status is not None else None
    normalized = status.lower() if status else None
    source = str(payload.get("source") or "").strip().lower()
    if normalized in BAD_ARTIFACT_STATUSES:
        return status, f"artifact_status:{normalized}"
    if source.startswith("fetch_failed") or source.startswith("error:"):
        return status, "artifact_source_failure"
    return status, None


def git_commit_time(path: Path) -> datetime | None:
    rel = str(path.relative_to(ROOT))
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", rel],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    return parse_time(proc.stdout.strip()) if proc.returncode == 0 else None


def working_tree_changed(path: Path) -> bool:
    rel = str(path.relative_to(ROOT))
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", rel],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    return bool(proc.stdout.strip())


def inspect(
    path: Path,
    target: str,
    now: datetime,
    require_target: bool,
    max_age_minutes: float = MAX_AGE_MINUTES,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "stale", "target_date": target, "artifact_target_date": None,
            "artifact_status": None, "file": str(path.relative_to(ROOT)),
            "generated_at": None, "age_minutes": None, "timestamp_source": "invalid_json",
            "reason": f"invalid_json:{type(exc).__name__}",
        }

    actual_target = artifact_target(payload)
    producer_status, health_failure = artifact_health(payload)
    stamp = artifact_time(payload)
    source = "artifact_metadata" if stamp else None

    if stamp is None and working_tree_changed(path):
        stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        source = "working_tree_mtime"
    if stamp is None:
        stamp = git_commit_time(path)
        source = "git_commit" if stamp else "unknown"

    raw_age = None if stamp is None else (now - stamp).total_seconds() / 60.0
    age = None if raw_age is None else round(max(0.0, raw_age), 1)
    future_ok = raw_age is None or raw_age >= -MAX_FUTURE_SKEW_MINUTES
    target_ok = actual_target == target if require_target else True
    time_ok = age is not None and age <= max_age_minutes and future_ok
    healthy = health_failure is None
    status = "fresh" if target_ok and time_ok and healthy else "stale"

    if health_failure:
        reason = health_failure
    elif require_target and actual_target is None:
        reason = "missing_required_target_date"
    elif not target_ok:
        reason = f"target_mismatch:{actual_target}!={target}"
    elif stamp is None:
        reason = "missing_generation_timestamp"
    elif not future_ok:
        reason = "generation_timestamp_in_future"
    elif not time_ok:
        reason = f"age_exceeds_{int(max_age_minutes)}m"
    elif not require_target and actual_target and actual_target != target:
        reason = f"archive_current:artifact_target={actual_target}"
    else:
        reason = "current"

    return {
        "status": status,
        "target_date": target,
        "artifact_target_date": actual_target,
        "artifact_status": producer_status,
        "file": str(path.relative_to(ROOT)),
        "generated_at": stamp.isoformat() if stamp else None,
        "age_minutes": age,
        "timestamp_source": source,
        "reason": reason,
    }


def inspect_config(config: dict[str, Any], target: str, now: datetime) -> dict[str, Any]:
    candidates = list(config.get("candidates") or [])
    require_target = bool(config.get("require_target"))
    max_age = float(config.get("max_age_minutes") or MAX_AGE_MINUTES)
    inspected = [
        inspect(DASHBOARD / name, target, now, require_target, max_age)
        for name in candidates if (DASHBOARD / name).exists()
    ]
    if not inspected:
        return {
            "status": "missing", "target_date": target, "artifact_target_date": None,
            "artifact_status": None, "file": None, "generated_at": None,
            "age_minutes": None, "timestamp_source": None, "reason": "no_active_artifact",
        }
    return next((row for row in inspected if row["status"] == "fresh"), inspected[0])


def build(target: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    tabs = {tab: inspect_config(config, target, now) for tab, config in TAB_CONFIG.items()}

    ui_tabs: dict[str, dict[str, Any]] = {}
    for route, config in UI_TAB_CONFIG.items():
        row = inspect_config(config, target, now)
        source_status = str(row.get("artifact_status") or "").lower()
        if row["status"] == "fresh":
            activity = "degraded" if source_status == "degraded" else "active"
        else:
            activity = row["status"]
        ui_tabs[route] = {
            "label": config["label"],
            "activity": activity,
            **row,
        }

    all_active = all(row["activity"] in {"active", "degraded"} for row in ui_tabs.values())
    active_count = sum(row["activity"] in {"active", "degraded"} for row in ui_tabs.values())

    payload = {
        "schema_version": "v5-semantic-freshness-3",
        "target_date": target,
        "generated_at": now.isoformat(),
        "freshness_policy": {
            "default_max_age_minutes": MAX_AGE_MINUTES,
            "max_future_skew_minutes": MAX_FUTURE_SKEW_MINUTES,
            "checkout_mtime_for_tracked_files": "forbidden",
            "current_slate_target_date": "required_for_current_views",
            "archive_target_date": "may_precede_current_target",
            "failed_or_standby_artifact": "stale",
            "legacy_fallbacks": "forbidden",
        },
        "retired_tabs": [],
        "ui_summary": {
            "tabs": len(ui_tabs),
            "active": active_count,
            "inactive": len(ui_tabs) - active_count,
            "all_tabs_active": all_active,
        },
        "ui_tabs": ui_tabs,
        "tabs": tabs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, dest="target_date")
    args = parser.parse_args()
    payload = build(str(args.target_date)[:10])
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
