#!/usr/bin/env python3
"""Build the V5 dashboard tab freshness manifest from artifact metadata.

Freshness must not depend on checkout mtimes: GitHub Actions checkout rewrites
filesystem timestamps and can make old artifacts look current. Current-slate
views must prove their target date, and known failed/standby producer states
must never be reported as fresh.
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

# Current/active candidates only. Retired legacy artifacts must not be used as a
# freshness fallback because their presence can mask a missing current producer.
TAB_CONFIG: dict[str, dict[str, Any]] = {
    "games": {"candidates": ["wnba_master.json"], "require_target": True},
    "game_props": {"candidates": ["wnba_game_props.json", "wnba_game_prop_intelligence.json"], "require_target": True},
    "player_props": {"candidates": ["wnba_player_props.json", "wnba_player_prop_intelligence.json"], "require_target": True},
    "alt_streaks": {"candidates": ["wnba_alt_streaks.json"], "require_target": True},
    "alt_performance": {"candidates": ["wnba_alt_performance.json"], "require_target": True},
    "daily_edges": {"candidates": ["wnba_daily_edges.json"], "require_target": True},
    "ensemble": {"candidates": ["wnba_ensemble_intelligence.json"], "require_target": True},
    "simulation": {"candidates": ["wnba_monte_carlo_scenarios.json"], "require_target": True},
    "best_bets": {"candidates": ["wnba_best_bets.json"], "require_target": True},
    # No active V5 portfolio producer is currently declared. Keep the tab
    # visible as missing instead of treating a legacy file as current.
    "portfolio": {"candidates": [], "require_target": False},
    "results": {"candidates": ["wnba_results_grading.json"], "require_target": True},
    "performance": {"candidates": ["wnba_game_performance.json"], "require_target": False},
    "explainability": {"candidates": ["wnba_reasoning_layer.json"], "require_target": False},
    "remaining_season": {"candidates": ["wnba_remaining_season_intelligence.json"], "require_target": False},
    "market_intelligence": {"candidates": ["wnba_market_timeline_summary.json", "wnba_line_movement_summary.json"], "require_target": True},
    "injuries": {"candidates": ["wnba_injury_intelligence.json"], "require_target": True},
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
    "error",
    "failed",
    "failure",
    "fetch_failed",
    "invalid",
    "missing",
    "stale",
    "standby",
    "unavailable",
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
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return parse_time(proc.stdout.strip()) if proc.returncode == 0 else None


def working_tree_changed(path: Path) -> bool:
    rel = str(path.relative_to(ROOT))
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", rel],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return bool(proc.stdout.strip())


def inspect(path: Path, target: str, now: datetime, require_target: bool) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "stale",
            "target_date": target,
            "artifact_target_date": None,
            "artifact_status": None,
            "file": str(path.relative_to(ROOT)),
            "generated_at": None,
            "age_minutes": None,
            "timestamp_source": "invalid_json",
            "reason": f"invalid_json:{type(exc).__name__}",
        }

    actual_target = artifact_target(payload)
    producer_status, health_failure = artifact_health(payload)
    stamp = artifact_time(payload)
    source = "artifact_metadata" if stamp else None

    # A file generated in this workflow may not yet have a Git commit. Its local
    # mtime is acceptable only while it is visibly changed in the working tree.
    if stamp is None and working_tree_changed(path):
        stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        source = "working_tree_mtime"
    if stamp is None:
        stamp = git_commit_time(path)
        source = "git_commit" if stamp else "unknown"

    raw_age = None if stamp is None else (now - stamp).total_seconds() / 60.0
    age = None if raw_age is None else round(max(0.0, raw_age), 1)
    future_ok = raw_age is None or raw_age >= -MAX_FUTURE_SKEW_MINUTES
    target_ok = actual_target == target if require_target else actual_target in (None, target)
    time_ok = age is not None and age <= MAX_AGE_MINUTES and future_ok
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
        reason = f"age_exceeds_{int(MAX_AGE_MINUTES)}m"
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


def build(target: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    tabs: dict[str, dict[str, Any]] = {}

    for tab, config in TAB_CONFIG.items():
        candidates = list(config["candidates"])
        require_target = bool(config["require_target"])
        inspected = [
            inspect(DASHBOARD / name, target, now, require_target)
            for name in candidates
            if (DASHBOARD / name).exists()
        ]
        if not inspected:
            tabs[tab] = {
                "status": "missing",
                "target_date": target,
                "artifact_target_date": None,
                "artifact_status": None,
                "file": None,
                "generated_at": None,
                "age_minutes": None,
                "timestamp_source": None,
                "reason": "retired_no_active_producer" if tab == "portfolio" else "no_active_artifact",
            }
            continue
        tabs[tab] = next((row for row in inspected if row["status"] == "fresh"), inspected[0])

    payload = {
        "schema_version": "v5-semantic-freshness-2",
        "target_date": target,
        "generated_at": now.isoformat(),
        "freshness_policy": {
            "max_age_minutes": MAX_AGE_MINUTES,
            "max_future_skew_minutes": MAX_FUTURE_SKEW_MINUTES,
            "checkout_mtime_for_tracked_files": "forbidden",
            "current_slate_target_date": "required",
            "target_date_mismatch": "stale",
            "failed_or_standby_artifact": "stale",
            "legacy_fallbacks": "forbidden",
        },
        "retired_tabs": ["portfolio"],
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
