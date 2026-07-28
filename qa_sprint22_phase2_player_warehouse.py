"""QA for Sprint 22 Phase 2 player intelligence warehouse."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

import build_sprint22_phase2_player_warehouse as wh


def run():
    tests = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = root / "raw"
        out = root / "out"
        raw.mkdir()

        pd.DataFrame([
            {"Player": "A Player", "Team": "Aces", "PTS": 18.0, "Pos": "G"},
            {"Player": "B Player", "Team": "Liberty", "PTS": 15.0, "Pos": "F"},
        ]).to_csv(raw / "player_stats_2026.csv", index=False)
        pd.DataFrame([
            {"Player": "A Player", "Team": "Aces", "USG%": 24.0},
            {"Player": "B Player", "Team": "Liberty", "USG%": 20.0},
        ]).to_csv(raw / "player_advanced_2026.csv", index=False)

        logs = []
        for i in range(12):
            team = "Aces" if i < 6 else "Storm"
            logs.append({
                "Player": "A Player",
                "Team": team,
                "Opponent": "Liberty",
                "Date": f"2026-07-{i + 1:02d}",
                "MIN": 30 + i % 3,
                "PTS": 10 + i,
                "REB": 4 + i % 4,
                "AST": 3 + i % 2,
            })
        pd.DataFrame(logs).to_csv(raw / "player_game_logs_2026.csv", index=False)
        pd.DataFrame([
            {"Player": "A Player", "Team": "Storm", "Date": "2026-07-12", "Status": "probable"}
        ]).to_csv(raw / "injuries_2026.csv", index=False)

        catalog = wh.build(raw, out)
        assert catalog["status"] == "PASS"; tests += 1
        assert catalog["warehouse_version"] == "sprint22_phase2_v2"; tests += 1
        assert catalog["tables"]["player_profile"]["rows"] == 2; tests += 1
        assert catalog["tables"]["player_game_logs"]["rows"] == 12; tests += 1
        assert catalog["duplicate_game_keys"] == 0; tests += 1
        assert catalog["log_only_player_ids"] == []; tests += 1
        assert catalog["availability_only_player_ids"] == []; tests += 1
        assert catalog["profile_linked_game_log_rows"] == 12; tests += 1

        profile = pd.read_csv(out / "player_profile.csv")
        assert profile["player_id"].nunique() == 2; tests += 1
        a = profile.loc[profile["player"] == "A Player"].iloc[0]
        assert a["points"] == 18.0 and a["usg_pct"] == 24.0; tests += 1

        logs_df = pd.read_csv(out / "player_game_logs.csv")
        assert logs_df[["player_id", "game_id"]].duplicated().sum() == 0; tests += 1
        assert logs_df.loc[logs_df["player"] == "A Player", "player_id"].nunique() == 1; tests += 1
        assert wh.stable_player_id("A Player", "") == wh.stable_player_id("A Player", ""); tests += 1

        rolling = pd.read_csv(out / "player_rolling_metrics.csv")
        first = rolling.sort_values("game_date").iloc[0]
        assert pd.isna(first.get("points_avg_l3")); tests += 1
        fourth = rolling.sort_values("game_date").iloc[3]
        assert abs(fourth["points_avg_l3"] - 11.0) < 1e-9; tests += 1

        matchups = pd.read_csv(out / "player_matchups.csv")
        assert int(matchups.iloc[0]["games"]) == 12; tests += 1
        availability = pd.read_csv(out / "player_availability.csv")
        assert availability.iloc[0]["status"] == "probable"; tests += 1
        assert availability.iloc[0]["player_id"] == logs_df.iloc[0]["player_id"]; tests += 1

        stored = json.loads((out / "player_catalog.json").read_text())
        assert stored["rolling_is_pregame_lagged"] is True; tests += 1
        assert "Team is never part" in stored["identity_policy"]; tests += 1
        for name in stored["tables"]:
            assert (out / f"{name}.csv").exists(); tests += 1

    return {"status": "PASS", "tests": tests}


if __name__ == "__main__":
    print(json.dumps(run()))
