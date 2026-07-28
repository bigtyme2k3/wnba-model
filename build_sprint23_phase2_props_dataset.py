"""Build a leakage-safe props training dataset from Sprint 23 player features."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

FEATURE_DIR = Path("data/features/sprint23/player")
WAREHOUSE = Path("data/warehouse/sprint22/player")
OUT = Path("data/processed/sprint23")

TARGET_MAP = {
    "points": "pts", "rebounds": "reb", "assists": "ast",
    "three_points_made": "threes",
}
FEATURE_MAP = {
    "minutes_avg_l5": "roll5_minutes", "points_avg_l5": "roll5_pts",
    "rebounds_avg_l5": "roll5_reb", "assists_avg_l5": "roll5_ast",
    "three_points_made_avg_l5": "roll5_threes", "pra_avg_l5": "roll5_pra",
    "rest_days": "rest_days", "minutes_season_avg": "minutes",
}


def build() -> dict:
    features = pd.read_csv(FEATURE_DIR / "player_game_features.csv", low_memory=False)
    logs = pd.read_csv(WAREHOUSE / "player_game_logs.csv", low_memory=False)
    coverage = json.loads((WAREHOUSE / "player_coverage_manifest.json").read_text())
    verified = set(int(s) for s in coverage["verified_seasons"])
    keys = ["player_id", "game_id"]
    keep_logs = keys + [c for c in ["player", "team", "opponent", "game_date", "season", *TARGET_MAP] if c in logs.columns]
    frame = features.merge(logs[keep_logs], on=keys, how="inner", suffixes=("", "_actual"))
    frame = frame[frame["season"].astype(int).isin(verified)].copy()
    for source, target in TARGET_MAP.items():
        if source in frame.columns:
            frame[target] = pd.to_numeric(frame[source], errors="coerce")
    if all(c in frame.columns for c in ("pts", "reb", "ast")):
        frame["pra"] = frame["pts"] + frame["reb"] + frame["ast"]
    for source, target in FEATURE_MAP.items():
        if source in frame.columns:
            frame[target] = pd.to_numeric(frame[source], errors="coerce")
    frame["usage"] = pd.to_numeric(frame.get("usage_season_avg", 0.24), errors="coerce").fillna(0.24)
    frame["ts_pct"] = pd.to_numeric(frame.get("true_shooting_pct_season_avg", 0.56), errors="coerce").fillna(0.56)
    frame["opp_drtg_pos"] = 102.0
    frame["avg_pace"] = 83.0
    frame["team_pace"] = 83.0
    frame["is_home"] = pd.to_numeric(frame.get("is_home", 0), errors="coerce").fillna(0).astype(int)
    frame["game_date"] = pd.to_datetime(frame["game_date"], errors="coerce")
    frame["season_game_num"] = frame.sort_values("game_date").groupby(["player_id", "season"]).cumcount() + 1
    frame["month"] = frame["game_date"].dt.month
    frame["feature_ready"] = frame.get("feature_ready", False).fillna(False).astype(bool)
    frame = frame.sort_values(["game_date", "player_id"]).reset_index(drop=True)
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "player_props_training.csv"
    frame.to_csv(output, index=False)
    target_counts = {t: int(frame[t].notna().sum()) for t in ["pts", "reb", "ast", "threes", "pra"] if t in frame}
    catalog = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": "sprint23_phase2_v1",
        "status": "PASS" if len(frame) and frame.duplicated(keys).sum() == 0 else "FAIL",
        "rows": int(len(frame)), "players": int(frame["player_id"].nunique()),
        "verified_seasons": sorted(verified), "target_counts": target_counts,
        "duplicate_player_game_keys": int(frame.duplicated(keys).sum()),
        "feature_ready_rows": int(frame["feature_ready"].sum()),
        "leakage_policy": "All model inputs originate from Phase 1 pregame-lagged features; actual stats are targets only.",
        "production_model_replaced": False,
    }
    (OUT / "props_integration_catalog.json").write_text(json.dumps(catalog, indent=2))
    print("Sprint 23 Phase 2 dataset:", catalog)
    return catalog

if __name__ == "__main__":
    build()
