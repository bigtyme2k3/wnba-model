#!/usr/bin/env python3
"""Build the V5 dashboard tab freshness manifest from artifact metadata.

Freshness must not depend on checkout mtimes: GitHub Actions checkout rewrites
filesystem timestamps and can make old artifacts look current. This consumer
prefers artifact target/generation metadata and falls back to the last Git
commit time for unchanged files.
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

# Current/active candidates only. Retired legacy artifacts must not be used as a
# freshness fallback because their presence can mask a missing current producer.
TAB_CANDIDATES: dict[str, list[str]] = {
    "games": ["wnba_master.json", "wnba_current_slate.json", "wnba_daily_report.json", "wnba_games.json"],
    "game_props": ["wnba_game_props.json", "wnba_game_prop_intelligence.json"],
    "player_props": ["wnba_player_props.json", "wnba_player_prop_intelligence.json"],
    "alt_streaks": ["wnba_alt_streaks.json"],
    "alt_performance": ["wnba_alt_performance.json", "wnba_alt_pending_diagnostics.json"],
    "daily_edges": ["wnba_daily_edges.json", "wnba_daily_edge_engine.json"],
    "ensemble": ["wnba_ensemble_intelligence.json", "wnba_ensemble.json"],
    "simulation": ["wnba_monte_carlo_scenarios.json"],
    "best_bets": ["wnba_best_bets.json"],
    # No active V5 portfolio producer is currently declared. Keep the tab
    # visible as missing instead of treating a legacy file as current.
    "portfolio": [],
    "results": ["wnba_results_grading.json", "wnba_results.json", "wnba_live_results.json"],
    "performance": ["wnba_game_performance.json", "wnba_model_performance.json"],
    "explainability": ["wnba_explainability.json", "wnba_reasoning_layer.json"],
    "remaining_season": ["wnba_remaining_season_intelligence.json"],
    "market_intelligence": ["wnba_market_timeline_summary.json", "wnba_line_movement_summary.json"],
    "injuries": ["wnba_injury_intelligence.json"],
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


def inspect(path: Path, target: str, now: datetime) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "stale",
            "target_date": target,
            "artifact_target_date": None,
            "file": str(path.relative_to(ROOT)),
            "generated_at": None,
            "age_minutes": None,
            "timestamp_source": "invalid_json",
            "reason": f"invalid_json:{type(exc).__name__}",
        }

    actual_target = artifact_target(payload)
    stamp = artifact_time(payload)
    source = "artifact_metadata" if stamp else None

    if stamp is None and working_tree_changed(path):
        stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        source = "working_tree_mtime"
    if stamp is None:
        stamp = git_commit_time(path)
        source = "git_commit" if stamp else "unknown"

    age = None if stamp is None else round(max(0.0, (now - stamp).total_seconds() / 60.0), 1)
    target_ok = actual_target in (None, target)
    time_ok = age is not None and age <= MAX_AGE_MINUTES
    status = "fresh" if target_ok and time_ok else "stale"

    if not target_ok:
        reason = f"target_mismatch:{actual_target}!={target}"
    elif age is None:
        reason = "missing_generation_timestamp"
    elif not time_ok:
        reason = f"age_exceeds_{int(MAX_AGE_MINUTES)}m"
    else:
        reason = "current"

    return {
        "status": status,
        "target_date": target,
        "artifact_target_date": actual_target,
        "file": str(path.relative_to(ROOT)),
        "generated_at": stamp.isoformat() if stamp else None,
        "age_minutes": age,
        "timestamp_source": source,
        "reason": reason,
    }


def build(target: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    tabs: dict[str, dict[str, Any]] = {}

    for tab, candidates in TAB_CANDIDATES.items():
        inspected = [inspect(DASHBOARD / name, target, now) for name in candidates if (DASHBOARD / name).exists()]
        if not inspected:
            tabs[tab] = {
                "status": "missing",
                "target_date": target,
                "artifact_target_date": None,
                "file": None,
                "generated_at": None,
                "age_minutes": None,
                "timestamp_source": None,
                "reason": "no_active_artifact",
            }
            continue
        tabs[tab] = next((row for row in inspected if row["status"] == "fresh"), inspected[0])

    payload = {
        "schema_version": "v5-semantic-freshness-1",
        "target_date": target,
        "generated_at": now.isoformat(),
        "freshness_policy": {
            "max_age_minutes": MAX_AGE_MINUTES,
            "checkout_mtime_for_tracked_files": "forbidden",
            "target_date_mismatch": "stale",
            "legacy_fallbacks": "forbidden",
        },
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
