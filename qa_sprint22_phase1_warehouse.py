"""QA for Sprint 22 Phase 1 warehouse expansion."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

import build_sprint22_phase1_warehouse as wh


def run():
    tests = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = root / "raw"
        out = root / "warehouse"
        raw.mkdir()

        pd.DataFrame([
            {"Team": "Aces", "ORtg": 110.2, "DRtg": 101.0},
            {"Team": "Liberty", "ORtg": 108.0, "DRtg": 103.0},
        ]).to_csv(raw / "team_advanced_2026.csv", index=False)
        pd.DataFrame([
            {"Team": "Aces", "PTS": 84.2},
            {"Team": "Liberty", "PTS": 82.1},
        ]).to_csv(raw / "team_stats_2026.csv", index=False)

        pd.DataFrame([
            {"Player": "Player A", "Team": "Aces", "PTS": 18.2},
            {"Player": "Player B", "Team": "Liberty", "PTS": 16.1},
        ]).to_csv(raw / "player_stats_2026.csv", index=False)
        pd.DataFrame([
            {"Player": "Player A", "Team": "Aces", "USG%": 24.0},
            {"Player": "Player B", "Team": "Liberty", "USG%": 21.0},
        ]).to_csv(raw / "player_advanced_2026.csv", index=False)

        pd.DataFrame([
            {"Date": "2026-07-01", "Home Team": "Aces", "Away Team": "Liberty"}
        ]).to_csv(raw / "schedule_2026.csv", index=False)
        pd.DataFrame([
            {"Date": "2026-07-01", "Home Team": "Aces", "Away Team": "Liberty", "PTS": 80, "PTS.1": 76}
        ]).to_csv(raw / "game_logs_2026.csv", index=False)

        odds = pd.DataFrame([
            {
                "start_time": "2026-07-01T23:00:00Z",
                "home_team": "Aces",
                "away_team": "Liberty",
                "sportsbook": "fanduel",
                "market": "spread",
                "selection": "Aces",
                "point": -4.5,
            }
        ])
        odds.to_csv(raw / "odds_2026.csv", index=False)
        odds.to_csv(raw / "odds_historical.csv", index=False)

        catalog = wh.build(raw, out)
        assert catalog["status"] == "PASS"; tests += 1
        assert catalog["layers"]["team_season"]["rows"] == 2; tests += 1
        assert catalog["layers"]["player_season"]["rows"] == 2; tests += 1
        assert catalog["layers"]["game_context"]["rows"] == 1; tests += 1
        assert catalog["layers"]["market_snapshot"]["rows"] == 1; tests += 1
        assert catalog["layers"]["team_season"]["duplicates_removed"] == 2; tests += 1
        assert catalog["layers"]["player_season"]["duplicates_removed"] == 2; tests += 1
        assert catalog["layers"]["game_context"]["duplicates_removed"] == 1; tests += 1
        assert catalog["layers"]["market_snapshot"]["duplicates_removed"] == 1; tests += 1

        team = pd.read_csv(out / "team_season.csv")
        aces = team.loc[team["team"] == "Aces"].iloc[0]
        assert aces["ortg"] == 110.2 and aces["pts"] == 84.2; tests += 1
        assert "team_advanced_2026.csv" in aces["source_file"] and "team_stats_2026.csv" in aces["source_file"]; tests += 1

        player = pd.read_csv(out / "player_season.csv")
        player_a = player.loc[player["player"] == "Player A"].iloc[0]
        assert player_a["pts"] == 18.2 and player_a["usg_pct"] == 24.0; tests += 1

        for name in wh.LAYERS:
            assert (out / f"{name}.csv").exists(); tests += 1
        stored = json.loads((out / "warehouse_catalog.json").read_text())
        assert stored["warehouse_version"] == "sprint22_phase1_v2"; tests += 1
        assert stored["total_input_rows"] == 12 and stored["total_rows"] == 6; tests += 1
        assert all(layer["grain_unique"] for layer in stored["layers"].values()); tests += 1

    return {"status": "PASS", "tests": tests}


if __name__ == "__main__":
    print(json.dumps(run()))
