"""QA for Sprint 23 Phase 1 player features."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path("data/features/sprint23/player")


def run() -> dict:
    features = pd.read_csv(ROOT / "player_game_features.csv", low_memory=False)
    latest = pd.read_csv(ROOT / "player_latest_features.csv", low_memory=False)
    catalog = json.loads((ROOT / "player_feature_catalog.json").read_text())

    required = {"player_id", "game_id", "game_date", "season", "games_before", "days_rest", "feature_ready"}
    missing = sorted(required - set(features.columns))
    duplicates = int(features.duplicated(["player_id", "game_id"]).sum())
    bad_seasons = sorted(set(pd.to_numeric(features["season"], errors="coerce").dropna().astype(int)) - set(catalog["verified_seasons"]))
    latest_duplicates = int(latest.duplicated("player_id").sum())
    leakage_columns = [c for c in features.columns if c.startswith("actual_") or c.startswith("target_")]

    tests = {
        "catalog_pass": catalog["status"] == "PASS",
        "rows_present": len(features) > 0,
        "latest_rows_present": len(latest) > 0,
        "required_columns": not missing,
        "unique_player_game_keys": duplicates == 0,
        "latest_one_row_per_player": latest_duplicates == 0,
        "verified_seasons_only": not bad_seasons,
        "pregame_lagged_declared": catalog.get("pregame_lagged") is True,
        "no_target_columns": not leakage_columns,
        "rolling_features_present": all(c in features for c in ["points_avg_l3", "points_avg_l5", "points_avg_l10"]),
        "rest_features_present": all(c in features for c in ["days_rest", "back_to_back", "long_rest"]),
    }
    failed = [name for name, passed in tests.items() if not passed]
    report = {
        "status": "PASS" if not failed else "FAIL",
        "tests": tests,
        "failed": failed,
        "diagnostics": {
            "rows": int(len(features)), "latest_players": int(len(latest)), "missing": missing,
            "duplicates": duplicates, "bad_seasons": bad_seasons, "leakage_columns": leakage_columns,
        },
    }
    print(json.dumps(report, indent=2))
    if failed:
        raise SystemExit(1)
    return report


if __name__ == "__main__":
    run()
