"""QA for Sprint 23 Phase 2 props integration and shadow training."""
import json
from pathlib import Path
import pandas as pd

DATA = Path("data/processed/sprint23/player_props_training.csv")
CATALOG = Path("data/processed/sprint23/props_integration_catalog.json")
EVAL = Path("models/sprint23/props_shadow_evaluation.json")


def has_any(df: pd.DataFrame, names: list[str]) -> bool:
    """Accept either the Phase 1 warehouse name or the props compatibility alias."""
    return any(name in df.columns for name in names)


def run():
    df = pd.read_csv(DATA, low_memory=False)
    catalog = json.loads(CATALOG.read_text())
    report = json.loads(EVAL.read_text())
    pregame_groups = [
        ["roll5_pts", "points_avg_l5"],
        ["roll5_reb", "rebounds_avg_l5"],
        ["roll5_ast", "assists_avg_l5"],
        ["rest_days"],
    ]
    tests = {
        "dataset_status_pass": catalog["status"] == "PASS",
        "rows_present": len(df) > 0,
        "verified_seasons_only": set(df["season"].astype(int)).issubset(set(catalog["verified_seasons"])),
        "unique_player_game_keys": not df.duplicated(["player_id", "game_id"]).any(),
        "targets_present": all(c in df.columns for c in ["pts", "reb", "ast", "threes", "pra"]),
        "pregame_features_present": all(has_any(df, names) for names in pregame_groups),
        "feature_ready_rows": int(df["feature_ready"].astype(str).str.lower().isin(["true", "1"]).sum()) > 0,
        "shadow_models_created": len(report["models_trained"]) >= 4,
        "production_unchanged": report["production_bundle_unchanged"] is True and report["promotion_status"] == "SHADOW_ONLY",
    }
    failed = [name for name, passed in tests.items() if not passed]
    result = {"status": "PASS" if not failed else "FAIL", "tests": tests, "failed": failed}
    print(json.dumps(result, indent=2))
    if failed:
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    run()
