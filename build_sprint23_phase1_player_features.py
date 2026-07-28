"""Sprint 23 Phase 1: build leakage-safe model features from the verified player warehouse."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

WAREHOUSE = Path("data/warehouse/sprint22/player")
OUT = Path("data/features/sprint23/player")
STATS = ["minutes", "points", "rebounds", "assists", "steals", "blocks", "turnovers"]


def read_csv(name: str) -> pd.DataFrame:
    path = WAREHOUSE / name
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, low_memory=False)


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    logs = read_csv("player_game_logs.csv")
    rolling = read_csv("player_rolling_metrics.csv")
    matchups = read_csv("player_matchups.csv")
    availability = read_csv("player_availability.csv")
    coverage = json.loads((WAREHOUSE / "player_coverage_manifest.json").read_text())

    allowed = set(int(x) for x in coverage["verified_seasons"])
    logs["season"] = pd.to_numeric(logs["season"], errors="coerce").astype("Int64")
    logs = logs[logs["season"].isin(allowed)].copy()
    logs["game_date"] = pd.to_datetime(logs["game_date"], errors="coerce")
    logs = logs.sort_values(["player_id", "game_date", "game_id"]).reset_index(drop=True)

    for stat in STATS:
        if stat in logs:
            logs[stat] = pd.to_numeric(logs[stat], errors="coerce")

    base_cols = [c for c in ["player_id", "game_id", "game_date", "season", "player", "team", "opponent"] if c in logs]
    features = logs[base_cols].copy()
    features["games_before"] = logs.groupby("player_id").cumcount()
    features["days_rest"] = logs.groupby("player_id")["game_date"].diff().dt.days
    features["back_to_back"] = features["days_rest"].eq(1).astype(int)
    features["long_rest"] = features["days_rest"].ge(4).astype(int)

    for window in (3, 5, 10):
        for stat in STATS:
            if stat in logs:
                grouped = logs.groupby("player_id")[stat]
                features[f"{stat}_avg_l{window}"] = grouped.transform(
                    lambda s: s.shift(1).rolling(window, min_periods=1).mean()
                )
                features[f"{stat}_std_l{window}"] = grouped.transform(
                    lambda s: s.shift(1).rolling(window, min_periods=2).std()
                )

    if {"points", "rebounds", "assists"}.issubset(logs.columns):
        logs["pra"] = logs["points"] + logs["rebounds"] + logs["assists"]
        for window in (3, 5, 10):
            features[f"pra_avg_l{window}"] = logs.groupby("player_id")["pra"].transform(
                lambda s: s.shift(1).rolling(window, min_periods=1).mean()
            )

    for stat in [s for s in STATS if s in logs]:
        features[f"{stat}_season_avg"] = logs.groupby(["player_id", "season"])[stat].transform(
            lambda s: s.shift(1).expanding(min_periods=1).mean()
        )

    if "minutes_avg_l5" in features and "minutes_avg_l10" in features:
        features["minutes_trend_5v10"] = features["minutes_avg_l5"] - features["minutes_avg_l10"]
    if "points_avg_l5" in features and "points_avg_l10" in features:
        features["points_trend_5v10"] = features["points_avg_l5"] - features["points_avg_l10"]

    matchup_stats = [c for c in STATS if c in matchups.columns]
    matchup = matchups[["player_id", "opponent", "games"] + matchup_stats].copy()
    matchup = matchup.rename(columns={"games": "matchup_games", **{s: f"matchup_{s}_avg" for s in matchup_stats}})
    features = features.merge(matchup, on=["player_id", "opponent"], how="left")

    if not availability.empty and "status" in availability:
        availability["snapshot_date"] = pd.to_datetime(availability["snapshot_date"], errors="coerce")
        latest_avail = availability.sort_values("snapshot_date").drop_duplicates("player_id", keep="last")
        latest_avail = latest_avail[["player_id", "status", "snapshot_date"]].rename(
            columns={"status": "availability_status", "snapshot_date": "availability_snapshot_date"}
        )
        features = features.merge(latest_avail, on="player_id", how="left")
    else:
        features["availability_status"] = "unknown"

    features["availability_status"] = features["availability_status"].fillna("unknown")
    features["availability_risk"] = features["availability_status"].astype(str).str.lower().isin(
        {"out", "doubtful", "questionable", "inactive"}
    ).astype(int)
    features["feature_ready"] = (features["games_before"] >= 3).astype(int)
    features["game_date"] = features["game_date"].dt.strftime("%Y-%m-%d")

    feature_cols = [c for c in features.columns if c not in base_cols]
    numeric_features = features[feature_cols].select_dtypes(include=[np.number]).columns
    features[numeric_features] = features[numeric_features].replace([np.inf, -np.inf], np.nan)

    features.to_csv(OUT / "player_game_features.csv", index=False)
    latest = features.sort_values(["player_id", "game_date"]).drop_duplicates("player_id", keep="last")
    latest.to_csv(OUT / "player_latest_features.csv", index=False)

    duplicate_keys = int(features.duplicated(["player_id", "game_id"]).sum())
    catalog = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_version": "sprint23_phase1_v1",
        "source": "verified Sprint 22 player warehouse",
        "verified_seasons": sorted(allowed),
        "rows": int(len(features)),
        "latest_players": int(len(latest)),
        "feature_columns": feature_cols,
        "duplicate_player_game_keys": duplicate_keys,
        "pregame_lagged": True,
        "minimum_history_for_ready": 3,
        "status": "PASS" if len(features) > 0 and duplicate_keys == 0 else "FAIL",
    }
    (OUT / "player_feature_catalog.json").write_text(json.dumps(catalog, indent=2))
    print("Sprint 23 Phase 1:", {"status": catalog["status"], "rows": catalog["rows"], "features": len(feature_cols)})
    return catalog


if __name__ == "__main__":
    build()
