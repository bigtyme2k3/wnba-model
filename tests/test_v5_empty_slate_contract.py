#!/usr/bin/env python3
"""Offline contract test for the V5 confirmed-empty-slate path.

The test redirects every M02 output into a temporary directory and replaces
network/subprocess entry points with hard failures. It proves that a confirmed
zero-game slate can produce READY empty artifacts without an Odds API request,
player-points execution, or mutation of repository production data.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = "2099-01-15"


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


def forbidden(label: str):
    def fail(*_args, **_kwargs):
        raise AssertionError(f"Forbidden empty-slate side effect invoked: {label}")
    return fail


def main() -> int:
    source = load_module(
        "v5_empty_test_prop_source",
        ROOT / "scripts" / "wnba_s19_m02_prop_source.py",
    )
    predictions = load_module(
        "v5_empty_test_predictions",
        ROOT / "scripts" / "wnba_s19_m02_predictions.py",
    )

    with tempfile.TemporaryDirectory(prefix="wnba-v5-empty-") as tmp:
        base = Path(tmp)
        dash = base / "data" / "dashboard"
        raw = base / "data" / "raw"
        dash.mkdir(parents=True)
        raw.mkdir(parents=True)

        injury_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        game_time = injury_time + timedelta(minutes=1)

        master = {
            "target_date": TARGET,
            "today_games": [],
            "summary": {"today_games": 0},
        }
        phase2 = {
            "target_date": TARGET,
            "generated_at_utc": game_time.isoformat(),
            "schema_version": "sprint19-m01-injury-aware-games-v1",
            "status": "PASS",
            "games": [],
            "summary": {"games": 0},
        }
        injury = {
            "target_date": TARGET,
            "generated_at_utc": injury_time.isoformat(),
            "source_only": True,
            "adjustments": [],
        }

        write_json(dash / "wnba_master.json", master)
        write_json(dash / "wnba_sprint2_phase2.json", phase2)
        write_json(dash / "wnba_injury_intelligence.json", injury)
        write_json(dash / "wnba_v5_buy_signals.json", {"target_date": TARGET, "rows": []})
        write_json(dash / "wnba_v5_live_portfolio.json", {"target_date": TARGET, "rows": []})

        # Redirect the prop-source module completely into the temp fixture.
        source.RAW = raw
        source.DASH = dash
        source.GAMES = dash / "wnba_sprint2_phase2.json"
        source.CANONICAL_PROPS = dash / "wnba_player_props.json"
        source.AUDIT = dash / "wnba_s19_m02_prop_source_audit.json"
        source.fetch_live = forbidden("Odds API fetch")

        source_result = source.build(TARGET)
        assert source_result["status"] == "READY"
        assert source_result["empty_slate"] is True
        assert source_result["api_called"] is False
        assert source_result["rows"] == 0
        assert source_result["canonical_games"] == []
        assert (raw / f"props_raw_{TARGET}.csv").exists()
        assert (raw / "props_today.csv").exists()

        # Redirect M02 prediction outputs and prohibit player_points execution.
        predictions.DASH = dash
        predictions.RAW = raw
        predictions.MASTER = dash / "wnba_master.json"
        predictions.GAMES = dash / "wnba_sprint2_phase2.json"
        predictions.INJURY = dash / "wnba_injury_intelligence.json"
        predictions.BUY = dash / "wnba_v5_buy_signals.json"
        predictions.PORTFOLIO = dash / "wnba_v5_live_portfolio.json"
        predictions.PROP_PRED = raw / "player_points_today.csv"
        predictions.OUT = dash / "wnba_s19_m02_predictions.json"
        predictions.AUDIT = dash / "wnba_s19_m02_prediction_audit.json"
        predictions.subprocess.run = forbidden("player_points subprocess")

        prediction_result = predictions.build(TARGET)
        prediction_audit = json.loads(predictions.AUDIT.read_text(encoding="utf-8"))

        assert prediction_result["status"] == "READY"
        assert prediction_result["empty_slate"] is True
        assert prediction_result["games"] == []
        assert prediction_result["player_props"] == []
        assert prediction_result["best_bets"] == []
        assert prediction_result["portfolio"] == []
        assert prediction_result["summary"]["player_prop_predictions"] == 0
        assert prediction_audit["status"] == "READY"
        assert prediction_audit["empty_slate"] is True
        assert prediction_audit["player_prop_predictions"] == 0
        assert prediction_audit["actionable_out_props"] == 0
        assert prediction_audit["all_rendered_props_exact_current_slate"] is True

        print(json.dumps({
            "status": "PASS",
            "contract": "V5_EMPTY_SLATE",
            "target_date": TARGET,
            "api_called": source_result["api_called"],
            "games": len(prediction_result["games"]),
            "player_props": len(prediction_result["player_props"]),
            "best_bets": len(prediction_result["best_bets"]),
            "portfolio": len(prediction_result["portfolio"]),
            "production_paths_touched": False,
        }, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
