#!/usr/bin/env python3
"""Offline regression for the canonical standard-prop sportsbook allowlist."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = "2099-01-16"


def load_module():
    path = ROOT / "wnba_player_props_ingestion.py"
    spec = importlib.util.spec_from_file_location("standard_prop_book_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ingestion = load_module()
    with tempfile.TemporaryDirectory(prefix="wnba-standard-books-") as tmp:
        base = Path(tmp)
        dash = base / "data" / "dashboard"
        raw = base / "data" / "raw"
        dash.mkdir(parents=True)
        raw.mkdir(parents=True)

        (dash / "wnba_master.json").write_text(json.dumps({
            "target_date": TARGET,
            "today_games": [{
                "game": "Test Away @ Test Home",
                "away_team": "Test Away",
                "home_team": "Test Home",
            }],
            "players": [{"player": "Test Player", "team": "Test Home"}],
        }), encoding="utf-8")
        cache = [{
            "id": "fixture-event",
            "commence_time": f"{TARGET}T23:00:00Z",
            "away_team": "Test Away",
            "home_team": "Test Home",
            "bookmakers": [
                {"key": "draftkings", "title": "DraftKings", "markets": [{
                    "key": "player_points",
                    "outcomes": [
                        {"description": "Test Player", "name": "Over", "point": 15.5, "price": -110},
                        {"description": "Test Player", "name": "Under", "point": 15.5, "price": -110},
                    ],
                }]},
                {"key": "fanduel", "title": "FanDuel", "markets": [{
                    "key": "player_points",
                    "outcomes": [
                        {"description": "Test Player", "name": "Over", "point": 15.5, "price": -105},
                        {"description": "Test Player", "name": "Under", "point": 15.5, "price": -115},
                    ],
                }]},
                {"key": "williamhill_us", "title": "Caesars", "markets": [{
                    "key": "player_points",
                    "outcomes": [
                        {"description": "Test Player", "name": "Over", "point": 15.5, "price": 140},
                        {"description": "Test Player", "name": "Under", "point": 15.5, "price": 130},
                    ],
                }]},
            ],
        }]
        cache_path = raw / f"wnba_player_props_{TARGET}.json"
        cache_path.write_text(json.dumps(cache), encoding="utf-8")

        ingestion.DASH = dash
        ingestion.RAW = raw
        old_argv = sys.argv
        try:
            sys.argv = [str(ROOT / "wnba_player_props_ingestion.py"), "--date", TARGET, "--from-raw-cache"]
            ingestion.main()
        finally:
            sys.argv = old_argv

        output = json.loads((dash / "wnba_player_props.json").read_text(encoding="utf-8"))
        assert output["api_called"] is False
        assert output["sportsbooks_observed"] == ["draftkings", "fanduel"]
        assert output["unsupported_bookmakers_rejected"] == ["williamhill_us"]
        assert output["row_count"] == 1
        row = output["rows"][0]
        assert {quote["book"] for quote in row["books"]} == {"DraftKings", "FanDuel"}
        assert row["best_over_book"] == "FanDuel"
        assert row["best_over_price"] == -105
        assert row["best_under_book"] == "DraftKings"
        assert row["best_under_price"] == -110

        repaired_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        assert {book["key"] for book in repaired_cache[0]["bookmakers"]} == {"draftkings", "fanduel"}

    print(json.dumps({"status": "PASS", "contract": "STANDARD_PROP_BOOK_ALLOWLIST"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
