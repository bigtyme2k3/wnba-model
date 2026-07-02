"""
feature_fixes.py
----------------
Quality floor, blowout dampening, and anchored rolling
to prevent elite teams being undervalued after one bad game.
"""
import numpy as np
import pandas as pd

BLOWOUT_CAP     = 20.0
ANCHOR_WEIGHT   = 0.30
ELITE_THRESHOLD = 5.0

def blowout_dampened_margin(margin: float) -> float:
    return float(np.clip(margin, -BLOWOUT_CAP, BLOWOUT_CAP))

def anchored_rolling(raw_rolling: float, net_rtg: float,
                     games_played: int, anchor_weight: float = ANCHOR_WEIGHT) -> float:
    season_progress = min(games_played / 30.0, 1.0)
    dynamic_weight  = anchor_weight * (1.0 - season_progress * 0.5)
    return float((1 - dynamic_weight) * raw_rolling + dynamic_weight * net_rtg)

def quality_floor(rolling: float, net_rtg: float) -> float:
    if net_rtg >= ELITE_THRESHOLD:
        return max(rolling, net_rtg - 15.0)
    elif net_rtg <= -ELITE_THRESHOLD:
        return min(rolling, net_rtg + 15.0)
    return rolling

def compute_improved_rolling(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    df = df.sort_values(["season", "game_date"]).reset_index(drop=True)

    home_rec = df[["game_date","season","home_team","actual_spread","home_net_rtg","season_game_num"]].copy()
    home_rec.columns = ["game_date","season","team","margin","net_rtg","game_num"]
    away_rec = df[["game_date","season","away_team","actual_spread","away_net_rtg","season_game_num"]].copy()
    away_rec["actual_spread"] = -away_rec["actual_spread"]
    away_rec.columns = ["game_date","season","team","margin","net_rtg","game_num"]

    all_rec = pd.concat([home_rec, away_rec]).sort_values(["team","season","game_date"])
    all_rec = all_rec[all_rec["margin"].notna()].copy()
    all_rec["margin_capped"] = all_rec["margin"].apply(blowout_dampened_margin)
    all_rec[f"raw_rolling_{window}g"] = (
        all_rec.groupby(["team","season"])["margin_capped"]
        .transform(lambda x: x.shift(1).rolling(window, min_periods=2).mean())
    )

    def apply_fixes(row):
        raw = row[f"raw_rolling_{window}g"]
        if pd.isna(raw): return row["net_rtg"] * 0.5
        floored  = quality_floor(raw, row["net_rtg"])
        anchored = anchored_rolling(floored, row["net_rtg"], int(row["game_num"]))
        return anchored

    all_rec[f"improved_rolling_{window}g"] = all_rec.apply(apply_fixes, axis=1)

    home_m = all_rec[["game_date","season","team",f"improved_rolling_{window}g"]].copy()
    home_m.columns = ["game_date","season","home_team",f"home_improved_{window}g"]
    away_m = all_rec[["game_date","season","team",f"improved_rolling_{window}g"]].copy()
    away_m.columns = ["game_date","season","away_team",f"away_improved_{window}g"]

    df = df.merge(home_m, on=["game_date","season","home_team"], how="left")
    df = df.merge(away_m, on=["game_date","season","away_team"], how="left")
    df[f"improved_diff_{window}g"] = (
        df.get(f"home_improved_{window}g", pd.Series(0, index=df.index)).fillna(0) -
        df.get(f"away_improved_{window}g", pd.Series(0, index=df.index)).fillna(0)
    )
    return df
