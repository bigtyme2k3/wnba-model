"""QA for Sprint 22 Phase 2.2 historical player backfill catalog."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

import build_sprint22_phase2_2_historical_player_backfill as backfill


def run() -> dict:
    tests = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = root / "raw"
        out = root / "out"
        raw.mkdir()
        out.mkdir()

        for season in range(2020, 2025):
            rows = []
            for game_number in range(1, 4):
                rows.extend([
                    {"source_player_id": "1", "player": "A Player", "game_id": f"{season}-{game_number}", "game_date": f"{season}-06-{game_number:02d}", "points": 10 + game_number},
                    {"source_player_id": "2", "player": "B Player", "game_id": f"{season}-{game_number}", "game_date": f"{season}-06-{game_number:02d}", "points": 8 + game_number},
                ])
            pd.DataFrame(rows).to_csv(raw / f"player_game_logs_{season}.csv", index=False)

        warehouse = {
            "tables": {
                "player_profile": {"rows": 10},
                "player_game_logs": {"rows": 30},
                "player_rolling_metrics": {"rows": 30},
                "player_availability": {"rows": 0},
                "player_matchups": {"rows": 4},
            }
        }
        (out / "player_catalog.json").write_text(json.dumps(warehouse), encoding="utf-8")
        report = backfill.inspect(raw, out, minimum_seasons=5)
        assert report["status"] == "PASS"; tests += 1
        assert report["season_count"] == 5; tests += 1
        assert report["total_game_logs"] == 30; tests += 1
        assert report["unique_players"] == 2; tests += 1
        assert report["duplicate_player_game_keys"] == 0; tests += 1
        assert report["season_min"] == 2020 and report["season_max"] == 2024; tests += 1
        stored = json.loads((out / "historical_backfill_catalog.json").read_text())
        assert stored["warehouse_tables"]["player_rolling_metrics"] == 30; tests += 1

    return {"status": "PASS", "tests": tests}


if __name__ == "__main__":
    print(json.dumps(run()))
