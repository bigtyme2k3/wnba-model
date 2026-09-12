#!/usr/bin/env python3
"""Offline regression test for the V5 projection-integrity boundary."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wnba_projection_contract import projection_ceiling, projection_field_violations, validate_projection

TARGET = "2099-01-17"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    assert validate_projection("PTS", 37.5) == (37.5, None)
    assert validate_projection("REB", 16.0) == (16.0, None)
    assert validate_projection("PTS", 55_600_000_000)[0] is None
    assert validate_projection("REB", -1)[0] is None
    assert validate_projection("AST", float("inf"))[0] is None
    assert projection_field_violations(
        {"model_projection": 17.0, "pred": 55_600_000_000}, "PTS"
    )[0]["field"] == "pred"

    edges = load_module("v5_integrity_edges", ROOT / "wnba_daily_edge_engine.py")
    ensemble = load_module("v5_integrity_ensemble", ROOT / "wnba_ensemble_intelligence_engine.py")
    monte_carlo = load_module("v5_integrity_monte_carlo", ROOT / "wnba_monte_carlo_scenario_engine.py")
    forward = load_module("v5_integrity_forward", ROOT / "wnba_forward_validation_engine.py")
    best_bets = load_module("v5_integrity_best_bets", ROOT / "wnba_best_bets.py")
    audit = load_module("v5_integrity_audit", ROOT / "scripts" / "wnba_v5_projection_integrity_audit.py")
    current_slate = load_module("v5_integrity_current_slate", ROOT / "wnba_current_slate.py")

    embedded = {
        "props": [{"projection": 55_600_000_000}],
        "best_bets": [{"projection": 55_600_000_000}],
        "portfolio": [{"projection": 55_600_000_000}],
        "summary": {"props": 1, "best_bets": 1, "portfolio": 1},
    }
    removed = current_slate.retire_legacy_betting_views(embedded)
    assert removed == {"props": 1, "best_bets": 1, "portfolio": 1}
    assert embedded["props"] == embedded["best_bets"] == embedded["portfolio"] == []
    assert all(embedded["summary"][key] == 0 for key in ("props", "best_bets", "portfolio"))

    with tempfile.TemporaryDirectory(prefix="wnba-v5-projection-integrity-") as tmp:
        base = Path(tmp)
        dash = base / "data/dashboard"
        ware = base / "data/warehouse"
        dash.mkdir(parents=True)
        ware.mkdir(parents=True)

        m02 = {
            "target_date": TARGET,
            "status": "READY",
            "empty_slate": False,
            "player_props": [
                {
                    "target_date": TARGET,
                    "player": "Healthy Player",
                    "team": "Test Home",
                    "game": "Test Away @ Test Home",
                    "stat": "PTS",
                    "line": 15.5,
                    "model_projection": 17.0,
                    "recommendation": "OVER",
                    "odds": -110,
                    "sportsbook": "fixturebook",
                },
                {
                    "target_date": TARGET,
                    "player": "Compounded Player",
                    "team": "Test Home",
                    "game": "Test Away @ Test Home",
                    "stat": "PTS",
                    "line": 12.5,
                    "model_projection": 55_600_000_000,
                    "recommendation": "OVER",
                    "odds": -110,
                    "sportsbook": "fixturebook",
                },
            ],
        }
        write_json(dash / "wnba_s19_m02_predictions.json", m02)

        edges.M02 = dash / "wnba_s19_m02_predictions.json"
        edges.ALT = dash / "wnba_alt_market_warehouse.json"
        edges.OUTS = [dash / "wnba_daily_edges.json", ware / "wnba_daily_edges.json"]
        edge_report = edges.build(TARGET)
        assert edge_report["status"] == "ok"
        assert edge_report["summary"]["candidates_scored"] == 1
        assert edge_report["summary"]["invalid_projection_rows_rejected"] == 1
        assert [row["player"] for row in edge_report["top_edges"]] == ["Healthy Player"]

        ensemble.EDGES = dash / "wnba_daily_edges.json"
        ensemble.OUTS = [dash / "wnba_ensemble_intelligence.json", ware / "wnba_ensemble_intelligence.json"]
        ensemble_report = ensemble.build(TARGET)
        assert ensemble_report["status"] == "ok"
        assert ensemble_report["summary"]["candidates_ranked"] == 1
        assert ensemble_report["ranked_edges"][0]["projection"] == 17.0

        monte_carlo.ENSEMBLE = dash / "wnba_ensemble_intelligence.json"
        monte_carlo.LOGS = ware / "wnba_player_game_logs.json"
        monte_carlo.OUTS = [dash / "wnba_monte_carlo_scenarios.json", ware / "wnba_monte_carlo_scenarios.json"]
        simulation_report = monte_carlo.build(TARGET, 1000)
        assert simulation_report["status"] == "ok"
        assert simulation_report["summary"]["candidates_simulated"] == 1
        simulated = simulation_report["all_simulations"][0]
        assert simulated["player"] == "Healthy Player"
        assert simulated["projection_validated"] is True
        assert 0 <= simulated["p90"] <= projection_ceiling("PTS")
        simulation_input = ensemble_report["ranked_edges"][0]
        assert monte_carlo.simulate_candidate(
            {**simulation_input, "projection": None},
            {("healthy player", "PTS"): [20.0] * 10},
            1000,
        ) is None
        assert monte_carlo.simulate_candidate({**simulation_input, "side": "PASS"}, {}, 1000) is None

        forward.DB = ware / "wnba_forward_validation.sqlite"
        forward.DASH = dash
        forward.WARE = ware
        forward.OUTS = [dash / "wnba_forward_validation.json", ware / "wnba_forward_validation.json"]
        forward.SOURCES = [
            ("daily_edge", dash / "wnba_daily_edges.json", "top_edges"),
            ("ensemble", dash / "wnba_ensemble_intelligence.json", "ranked_edges"),
            ("simulation", dash / "wnba_monte_carlo_scenarios.json", "all_simulations"),
        ]
        frozen = forward.freeze(TARGET)
        assert frozen["inserted"] == 3
        assert frozen["invalid_projection_rows_rejected"] == 0

        corrupted_edges = dict(edge_report)
        corrupted_edges["top_edges"] = [
            *edge_report["top_edges"],
            {**edge_report["top_edges"][0], "player": "Frozen Corrupt", "projection": 55_600_000_000},
        ]
        write_json(dash / "wnba_daily_edges.json", corrupted_edges)
        rejected_freeze = forward.freeze(TARGET)
        assert rejected_freeze["inserted"] == 0
        assert rejected_freeze["invalid_projection_rows_rejected"] == 1
        write_json(dash / "wnba_daily_edges.json", edge_report)
        forward_report = forward.report()
        assert forward_report["summary"]["frozen_predictions"] == 3
        assert forward_report["summary"]["quarantined_predictions"] == 0

        # The repository-wide gate must detect corruption even if a downstream
        # consumer would quarantine it locally.
        write_json(dash / "wnba_master.json", {"target_date": TARGET, "props": []})
        write_json(dash / "wnba_v5_buy_signals.json", {
            "injury_target_date": TARGET,
            "signals": [
                {
                    "date": TARGET, "player": "Healthy Player", "market": "PTS", "side": "OVER",
                    "line": 15.5, "projection": 17.0, "decision_state": "BUY_NOW", "expected_value": 0.08,
                },
                {
                    "date": TARGET, "player": "Compounded Player", "market": "PTS", "side": "OVER",
                    "line": 12.5, "projection": 55_600_000_000, "decision_state": "BUY_NOW", "expected_value": 99.0,
                },
            ],
        })
        best_bets.ROOT = dash
        best_bets.MASTER = dash / "wnba_master.json"
        best_bets.V5_BUY = dash / "wnba_v5_buy_signals.json"
        best_bets.OUT = dash / "wnba_best_bets.json"
        old_argv = sys.argv
        try:
            sys.argv = ["wnba_best_bets.py", "--date", TARGET]
            best_bets.main()
        finally:
            sys.argv = old_argv
        bets = json.loads(best_bets.OUT.read_text(encoding="utf-8"))
        assert bets["status"] == "invalid"
        assert bets["bet_count"] == 1
        assert bets["best_bets"][0]["player"] == "Healthy Player"
        assert bets["projection_integrity"]["invalid_rows_rejected"] == 1
        audit.ROOT = base
        failed = audit.inspect(TARGET)
        assert failed["status"] == "FAIL"
        assert any(
            item.get("artifact") == "data/dashboard/wnba_s19_m02_predictions.json"
            and str(item.get("reason", "")).startswith("above_PTS_ceiling")
            for item in failed["violations"]
        )

        m02["player_props"] = [m02["player_props"][0]]
        write_json(dash / "wnba_s19_m02_predictions.json", m02)
        passed = audit.inspect(TARGET)
        assert passed["status"] == "PASS", passed["violations"]
        assert passed["violation_count"] == 0

        # A stale canonical source must clear the derived chain rather than
        # silently retaining a prior target's rankings.
        m02["target_date"] = "2099-01-16"
        write_json(dash / "wnba_s19_m02_predictions.json", m02)
        stale = edges.build(TARGET)
        assert stale["status"] == "stale"
        assert stale["top_edges"] == []

        m02["target_date"] = TARGET
        m02["empty_slate"] = True
        write_json(dash / "wnba_s19_m02_predictions.json", m02)
        contradictory_empty = edges.build(TARGET)
        assert contradictory_empty["status"] == "invalid"
        assert contradictory_empty["top_edges"] == []

    print(json.dumps({
        "status": "PASS",
        "contract": "V5_PROJECTION_INTEGRITY",
        "corrupted_projection": 55_600_000_000,
        "daily_edges_published": 1,
        "ensemble_ranked": 1,
        "monte_carlo_simulated": 1,
        "forward_rows_frozen": 3,
        "corrupted_forward_row_rejected": True,
        "corrupted_best_bet_rejected": True,
        "audit_detected_corruption": True,
        "legacy_embedded_views_cleared": True,
        "stale_source_failed_closed": True,
        "contradictory_empty_slate_failed_closed": True,
        "production_paths_touched": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
