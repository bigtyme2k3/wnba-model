"""Train shadow props models without replacing the current production bundle."""
from __future__ import annotations
import json, pickle
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error

DATA = Path("data/processed/sprint23/player_props_training.csv")
OUT = Path("models/sprint23")
TARGETS = ["pts", "reb", "ast", "threes", "pra"]
FEATURES = [
    "roll5_minutes", "roll5_pts", "roll5_reb", "roll5_ast", "roll5_threes", "roll5_pra",
    "minutes", "rest_days", "is_home", "season_game_num", "month", "usage", "ts_pct",
    "points_trend_l5", "minutes_trend_l5", "points_volatility_l10", "availability_risk",
    "matchup_points_avg", "matchup_rebounds_avg", "matchup_assists_avg",
]


def train() -> dict:
    df = pd.read_csv(DATA, parse_dates=["game_date"], low_memory=False).sort_values("game_date")
    df = df[df["feature_ready"].astype(str).str.lower().isin(["true", "1"])].copy()
    available = [c for c in FEATURES if c in df.columns]
    bundles, metrics = {}, {}
    for target in TARGETS:
        if target not in df.columns:
            continue
        sub = df[df[target].notna()].copy()
        if len(sub) < 100:
            continue
        split = max(int(len(sub) * 0.8), 1)
        train_df, test_df = sub.iloc[:split], sub.iloc[split:]
        X_train = train_df[available].apply(pd.to_numeric, errors="coerce").fillna(0)
        X_test = test_df[available].apply(pd.to_numeric, errors="coerce").fillna(0)
        model = Pipeline([("sc", StandardScaler()), ("model", Ridge(alpha=5.0))])
        model.fit(X_train, train_df[target])
        pred = model.predict(X_test)
        mae = float(mean_absolute_error(test_df[target], pred)) if len(test_df) else None
        baseline = float(mean_absolute_error(test_df[target], np.repeat(train_df[target].mean(), len(test_df)))) if len(test_df) else None
        bundles[target] = {"model": model, "features": available, "train_rows": int(len(train_df))}
        metrics[target] = {"test_rows": int(len(test_df)), "mae": mae, "mean_baseline_mae": baseline,
                           "beats_mean_baseline": bool(mae < baseline) if mae is not None else False}
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "props_models_shadow.pkl").open("wb") as fh:
        pickle.dump({"models": bundles, "version": "sprint23_phase2_shadow_v1"}, fh)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if len(bundles) >= 4 else "WARN",
        "models_trained": sorted(bundles), "features": available, "metrics": metrics,
        "promotion_status": "SHADOW_ONLY",
        "production_bundle_unchanged": True,
    }
    (OUT / "props_shadow_evaluation.json").write_text(json.dumps(report, indent=2))
    print("Sprint 23 Phase 2 shadow models:", report)
    return report

if __name__ == "__main__":
    train()
