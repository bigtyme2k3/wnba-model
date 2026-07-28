"""QA for Sprint 22 Phase 2.1 player ingestion bridge."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

import normalize_sprint22_phase2_1_player_data as ingest


def run() -> dict:
    tests = 0
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp)
        pd.DataFrame([
            {"game_id":"1","season":2026,"game_date":"2026-05-01","team_name":"Aces","team_abbreviation":"LVA","athlete_id":"10","athlete_display_name":"A Player","athlete_position_abbreviation":"G","minutes":30,"points":20,"rebounds":5,"assists":4},
            {"game_id":"2","season":2026,"game_date":"2026-05-03","team_name":"Aces","team_abbreviation":"LVA","athlete_id":"10","athlete_display_name":"A Player","athlete_position_abbreviation":"G","minutes":31,"points":22,"rebounds":6,"assists":5},
            {"game_id":"2","season":2026,"game_date":"2026-05-03","team_name":"Aces","team_abbreviation":"LVA","athlete_id":"10","athlete_display_name":"A Player","athlete_position_abbreviation":"G","minutes":31,"points":22,"rebounds":6,"assists":5},
        ]).to_csv(raw / "wehoop_player_box_2026.csv", index=False)
        report = ingest.build(raw)
        assert report["status"] == "PASS"; tests += 1
        assert report["total_game_logs"] == 2; tests += 1
        logs = pd.read_csv(raw / "player_game_logs_2026.csv")
        assert len(logs) == 2; tests += 1
        assert {"source_player_id","player","team","game_id","game_date","points"}.issubset(logs.columns); tests += 1
        assert logs[["source_player_id","game_id","player"]].duplicated().sum() == 0; tests += 1
        profiles = pd.read_csv(raw / "player_profiles_2026.csv")
        assert len(profiles) == 1; tests += 1
        assert str(profiles.iloc[0]["source_player_id"]) == "10"; tests += 1
        catalog = json.loads((raw / "player_ingestion_catalog.json").read_text())
        assert catalog["unique_players"] == 1; tests += 1
    return {"status":"PASS","tests":tests}


if __name__ == "__main__":
    print(json.dumps(run()))
