"""Acceptance tests and bounded stale-output recovery for WNBA Mission Control."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

import wnba_mission_control as engine

MISSION_CONTROL = Path("data/dashboard/wnba_mission_control.json")
GAME_MODEL = Path("data/dashboard/wnba_game_market_model.json")
ALT_WAREHOUSE = Path("data/dashboard/wnba_alt_market_warehouse.json")
MATCHUP = Path("data/dashboard/wnba_matchup_intelligence.json")


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _run(command: list[str]) -> None:
    print("MISSION CONTROL RECOVERY:", " ".join(command))
    subprocess.run(command, check=True)


def _target() -> str:
    payload = _load(MISSION_CONTROL)
    target = str(payload.get("target_date") or "").strip()
    if target:
        return target
    result = subprocess.run(
        [sys.executable, "active_slate_date.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _is_stale(path: Path, target: str) -> bool:
    payload = _load(path)
    return not payload or str(payload.get("target_date") or "") != target


def refresh_stale_model_outputs() -> bool:
    """Refresh every active-slate model dependency used by the live dashboard.

    Manual dashboard runs can occur after the master slate advances but before
    Version 4 Status finishes the full model chain. This recovery keeps the
    canonical dashboard honest by rebuilding stale critical projections first,
    then the game model, ALT warehouse metadata, master payload, and Games views.
    """
    payload = _load(MISSION_CONTROL)
    target = _target()
    checks = {str(row.get("id")): row for row in payload.get("checks", []) if isinstance(row, dict)}
    stale_ids = {
        check_id
        for check_id in ("minutes", "unified", "top_plays", "explainability")
        if checks.get(check_id, {}).get("status") in {"RED", "YELLOW"}
        and any("Stale slate date" in str(issue) for issue in checks.get(check_id, {}).get("issues", []))
    }

    python = sys.executable
    changed = False

    if {"minutes", "unified"} & stale_ids:
        commands = [
            [python, "wnba_minutes_projection_v2.py", "--date", target],
            [python, "wnba_points_projection_v2.py", "--date", target],
            [python, "wnba_rebounds_assists_projection_v2.py", "--date", target],
            [python, "wnba_ancillary_projection_v2.py", "--date", target],
            [python, "wnba_unified_player_simulation_v2.py", "--date", target],
            [python, "qa_minutes_projection_v2.py"],
            [python, "qa_points_projection_v2.py"],
            [python, "qa_rebounds_assists_projection_v2.py"],
            [python, "qa_ancillary_projection_v2.py"],
            [python, "qa_unified_player_simulation_v2.py"],
            [python, "wnba_cross_market_top_plays.py", "--date", target],
            [python, "qa_cross_market_top_plays.py"],
            [python, "wnba_model_explainability.py", "--date", target],
            [python, "qa_model_explainability.py"],
        ]
        for command in commands:
            _run(command)
        changed = True

    game_payload = _load(GAME_MODEL)
    game_rows = game_payload.get("games", []) if isinstance(game_payload.get("games"), list) else []
    game_unavailable = not game_rows or not any(bool(row.get("model_available")) for row in game_rows if isinstance(row, dict))
    game_stale = _is_stale(GAME_MODEL, target) or _is_stale(MATCHUP, target)

    if game_stale or game_unavailable:
        for command in [
            [python, "wnba_matchup_intelligence.py", "--date", target],
            [python, "wnba_projection_ai.py", "--date", target],
            [python, "wnba_game_market_model.py", "--date", target],
            [python, "wnba_decision_engine_final.py", "--date", target],
            [python, "wnba_portfolio_optimizer_v2.py", "--date", target],
            [python, "wnba_risk_allocation.py", "--date", target],
        ]:
            _run(command)
        changed = True

    if _is_stale(ALT_WAREHOUSE, target):
        _run([python, "wnba_alt_market_warehouse.py", "--date", target])
        changed = True

    if changed:
        _run([python, "wnba_master_source_builder.py", "--date", target])
        _run([python, "patch_dashboard_v4_games_markets.py"])

    rebuilt = engine.build(target, retry_count=0)
    remaining_red = [row["component"] for row in rebuilt.get("checks", []) if row.get("status") == "RED"]
    if remaining_red:
        raise RuntimeError("Critical outputs remain blocked after recovery: " + ", ".join(remaining_red))
    print("MISSION CONTROL RECOVERY COMPLETE:", target, "changed=", changed)
    return changed


def test_count_helpers():
    assert engine.count_value([1, 2, 3]) == 3
    assert engine.count_value({"a": 1}) == 1
    assert engine.count_value(4) == 4


def test_alt_zero_is_detected():
    """Canonical ALT warehouse with raw source rows but zero valid markets is yellow."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "alt.json"
        path.write_text(
            json.dumps(
                {
                    "generated_at_utc": "2099-01-01T00:00:00+00:00",
                    "target_date": "2026-07-13",
                    "summary": {"raw_rows": 214, "markets": 0, "players": 0},
                }
            ),
            encoding="utf-8",
        )
        check = {
            "id": "alt_props",
            "name": "ALT Player Props",
            "path": str(path),
            "keys": ["summary.markets"],
            "minimum": 1,
            "critical": False,
            "retry": True,
        }
        row = engine.evaluate(check, "2026-07-13", 0)
        assert row["status"] == "YELLOW", row
        assert row["action"] == "RETRY_SOURCE", row
        assert any("0 valid markets" in issue for issue in row["issues"]), row


def test_critical_missing_blocks():
    check = {
        "id": "games",
        "name": "Games",
        "path": "definitely_missing_file.json",
        "keys": ["games"],
        "minimum": 1,
        "critical": True,
    }
    row = engine.evaluate(check, "2026-07-13", 0)
    assert row["status"] == "RED", row
    assert row["action"] == "BLOCK_PUBLISH", row


def test_retry_cap():
    """After two attempts an empty optional ALT source publishes degraded."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "alt.json"
        path.write_text(
            json.dumps(
                {
                    "target_date": "2026-07-13",
                    "summary": {"raw_rows": 100, "markets": 0, "players": 0},
                }
            ),
            encoding="utf-8",
        )
        check = {
            "id": "alt_props",
            "name": "ALT Player Props",
            "path": str(path),
            "keys": ["summary.markets"],
            "minimum": 1,
            "critical": False,
            "retry": True,
        }
        row = engine.evaluate(check, "2026-07-13", 2)
        assert row["status"] == "YELLOW", row
        assert row["action"] == "PUBLISH_DEGRADED", row


def main():
    refresh_stale_model_outputs()
    tests = [
        ("count helpers", test_count_helpers),
        ("ALT zero detection", test_alt_zero_is_detected),
        ("critical failure blocks", test_critical_missing_blocks),
        ("retry cap", test_retry_cap),
    ]
    results = []
    for name, fn in tests:
        try:
            fn()
            results.append({"test": name, "passed": True, "detail": ""})
        except Exception as exc:
            results.append({"test": name, "passed": False, "detail": str(exc)})
    failed = [row for row in results if not row["passed"]]
    report = {
        "status": "green" if not failed else "red",
        "summary": {"tests": len(results), "passed": len(results) - len(failed), "failed": len(failed)},
        "tests": results,
    }
    Path("data/dashboard").mkdir(parents=True, exist_ok=True)
    with Path("data/dashboard/wnba_mission_control_acceptance.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(report["summary"])
    if failed:
        for row in failed:
            print("FAILED:", row["test"], row["detail"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
