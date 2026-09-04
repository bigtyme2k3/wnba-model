#!/usr/bin/env python3
"""Offline active-slate simulation for the V5 M02 chain.

Uses one synthetic game and a persisted canonical three-book prop fixture. All
outputs are redirected to a temporary directory. Live Odds API access is a hard
failure, while player_points.py is replaced by a deterministic local fixture so
we can prove the active-slate M02 contract without spending credits or touching
production data.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = "2099-01-16"
GAME = "Test Away @ Test Home"
PLAYER = "Test Player"


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
        raise AssertionError(f"Forbidden active-slate side effect invoked: {label}")
    return fail


def main() -> int:
    source = load_module(
        "v5_active_test_prop_source",
        ROOT / "scripts" / "wnba_s19_m02_prop_source.py",
    )
    predictions = load_module(
        "v5_active_test_predictions",
        ROOT / "scripts" / "wnba_s19_m02_predictions.py",
    )

    with tempfile.TemporaryDirectory(prefix="wnba-v5-active-") as tmp:
        base = Path(tmp)
        dash = base / "data" / "dashboard"
        raw = base / "data" / "raw"
        dash.mkdir(parents=True)
        raw.mkdir(parents=True)

        injury_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        game_time = injury_time + timedelta(minutes=1)

        write_json(dash / "wnba_master.json", {
            "target_date": TARGET,
            "today_games": [{
                "game": GAME,
                "away_team": "Test Away",
                "home_team": "Test Home",
            }],
            "summary": {"today_games": 1},
        })
        write_json(dash / "wnba_sprint2_phase2.json", {
            "target_date": TARGET,
            "generated_at_utc": game_time.isoformat(),
            "schema_version": "sprint19-m01-injury-aware-games-v1",
            "status": "PASS",
            "games": [{
                "game": GAME,
                "away_team": "Test Away",
                "home_team": "Test Home",
                "injury_context": {
                    "fresh": True,
                    "target_date": TARGET,
                },
            }],
            "summary": {"games": 1},
        })
        write_json(dash / "wnba_injury_intelligence.json", {
            "target_date": TARGET,
            "generated_at_utc": injury_time.isoformat(),
            "source_only": True,
            "injury_source_verified": True,
            "adjustments": [],
        })
        write_json(dash / "wnba_player_props.json", {
            "target_date": TARGET,
            "generated_at_utc": injury_time.isoformat(),
            "row_count": 1,
            "rows": [{
                "target_date": TARGET,
                "event_id": "fixture-event",
                "player": PLAYER,
                "team": "Test Home",
                "game": GAME,
                "away_team": "Test Away",
                "home_team": "Test Home",
                "stat": "points",
                "line": 15.5,
                "commence_time": f"{TARGET}T23:00:00Z",
                "books": [
                    {"book": "fanduel", "side": "OVER", "price": -110},
                    {"book": "draftkings", "side": "UNDER", "price": -105},
                    {"book": "fanatics", "side": "OVER", "price": -108}
                ],
            }],
        })
        write_json(dash / "wnba_v5_buy_signals.json", {"target_date": TARGET, "rows": []})
        write_json(dash / "wnba_v5_live_portfolio.json", {"target_date": TARGET, "rows": []})

        source.RAW = raw
        source.DASH = dash
        source.GAMES = dash / "wnba_sprint2_phase2.json"
        source.CANONICAL_PROPS = dash / "wnba_player_props.json"
        source.AUDIT = dash / "wnba_s19_m02_prop_source_audit.json"
        source.fetch_live = forbidden("Odds API fetch")

        source_result = source.build(TARGET)
        assert source_result["status"] == "READY"
        assert source_result["empty_slate"] is False
        assert source_result["api_called"] is False
        assert source_result["source"] == "data/dashboard/wnba_player_props.json"
        assert source_result["rows"] == 1
        assert source_result["canonical_games"] == [GAME]
        assert source_result["prop_games"] == [GAME]
        assert set(source_result["sportsbooks"]) == {"draftkings", "fanduel", "fanatics"}

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

        def fake_player_points(command, check=False, **_kwargs):
            assert command[:2] == ["python", "player_points.py"], command
            assert "--date" in command and TARGET in command, command
            with predictions.PROP_PRED.open("w", newline="", encoding="utf-8") as fobj:
                writer = csv.DictWriter(fobj, fieldnames=[
                    "player", "team", "opp_team", "stat", "line", "pred",
                    "signal", "is_active", "conf", "best_over_book",
                    "over_price", "best_under_book", "under_price",
                ])
                writer.writeheader()
                writer.writerow({
                    "player": PLAYER,
                    "team": "Test Home",
                    "opp_team": GAME,
                    "stat": "PTS",
                    "line": 15.5,
                    "pred": 17.0,
                    "signal": "OVER",
                    "is_active": "true",
                    "conf": "HIGH",
                    "best_over_book": "fanduel",
                    "over_price": -110,
                    "best_under_book": "draftkings",
                    "under_price": -105,
                })
            class Result:
                returncode = 0
            return Result()

        predictions.subprocess.run = fake_player_points
        prediction_result = predictions.build(TARGET)
        prediction_audit = json.loads(predictions.AUDIT.read_text(encoding="utf-8"))

        assert prediction_result["status"] == "READY"
        assert prediction_result["empty_slate"] is False
        assert len(prediction_result["games"]) == 1
        assert len(prediction_result["player_props"]) == 1
        assert prediction_result["player_props"][0]["player"] == PLAYER
        assert prediction_result["player_props"][0]["game"] == GAME
        assert prediction_result["player_props"][0]["model_projection"] == 17.0
        assert prediction_result["player_props"][0]["final_action"] == "WATCH"
        assert prediction_result["best_bets"] == []
        assert prediction_result["portfolio"] == []
        assert prediction_audit["status"] == "READY"
        assert prediction_audit["empty_slate"] is False
        assert prediction_audit["player_prop_predictions"] == 1
        assert prediction_audit["player_props_with_model_projection"] == 1
        assert prediction_audit["off_slate_prop_rows_rejected"] == 0
        assert prediction_audit["all_rendered_props_exact_current_slate"] is True
        assert prediction_audit["phase2_best_bets_fallback_enabled"] is False
        assert prediction_audit["phase2_portfolio_fallback_enabled"] is False

        print(json.dumps({
            "status": "PASS",
            "contract": "V5_ACTIVE_SLATE_OFFLINE",
            "target_date": TARGET,
            "games": len(prediction_result["games"]),
            "source_rows": source_result["rows"],
            "player_prop_predictions": prediction_audit["player_prop_predictions"],
            "api_called": source_result["api_called"],
            "final_action": prediction_result["player_props"][0]["final_action"],
            "production_paths_touched": False,
        }, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
