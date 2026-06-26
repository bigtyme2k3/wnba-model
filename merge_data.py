"""
merge_data.py
-------------
Merges Basketball-Reference stats with The Odds API lines into a
single model-ready master dataset. Also engineers key features:

  - Rest days per team
  - Back-to-back / 3-in-4 fatigue flags
  - Home/away travel direction (East→West, West→East)
  - Rolling team efficiency (last 5 and 10 games)
  - Actual spread result and total result (for model training labels)

Usage:
    python merge_data.py --year 2023
    python merge_data.py --year all

Output:
    data/processed/master_{year}.csv
    data/processed/master_all.csv
"""

import os
import argparse
import numpy as np
import pandas as pd
from glob import glob

RAW_DIR       = "data/raw"
PROCESSED_DIR = "data/processed"

# ── Team name normalization ───────────────────────────────────────────────────
# Basketball-Reference and The Odds API use slightly different names.
# Add more mappings here as needed.

TEAM_NAME_MAP = {
    "Las Vegas Aces":          "Las Vegas Aces",
    "New York Liberty":        "New York Liberty",
    "Connecticut Sun":         "Connecticut Sun",
    "Seattle Storm":           "Seattle Storm",
    "Minnesota Lynx":          "Minnesota Lynx",
    "Chicago Sky":             "Chicago Sky",
    "Los Angeles Sparks":      "Los Angeles Sparks",
    "Phoenix Mercury":         "Phoenix Mercury",
    "Atlanta Dream":           "Atlanta Dream",
    "Washington Mystics":      "Washington Mystics",
    "Dallas Wings":            "Dallas Wings",
    "Indiana Fever":           "Indiana Fever",
    # Expansion teams (2025+)
    "Golden State Valkyries":  "Golden State Valkyries",
    "Toronto Tempo":           "Toronto Tempo",
    "Portland Fire":           "Portland Fire",
    # Abbreviations from BRef game logs
    "LVA": "Las Vegas Aces",
    "NYL": "New York Liberty",
    "CON": "Connecticut Sun",
    "SEA": "Seattle Storm",
    "MIN": "Minnesota Lynx",
    "CHI": "Chicago Sky",
    "LAS": "Los Angeles Sparks",
    "PHO": "Phoenix Mercury",
    "ATL": "Atlanta Dream",
    "WAS": "Washington Mystics",
    "DAL": "Dallas Wings",
    "IND": "Indiana Fever",
}

# Time zones per team arena (for travel fatigue calculations)
TEAM_TIMEZONES = {
    "Las Vegas Aces":         "US/Pacific",
    "Golden State Valkyries": "US/Pacific",
    "Seattle Storm":          "US/Pacific",
    "Los Angeles Sparks":     "US/Pacific",
    "Phoenix Mercury":        "US/Mountain",
    "Minnesota Lynx":         "US/Central",
    "Chicago Sky":            "US/Central",
    "Dallas Wings":           "US/Central",
    "Indiana Fever":          "US/Eastern",
    "New York Liberty":       "US/Eastern",
    "Connecticut Sun":        "US/Eastern",
    "Atlanta Dream":          "US/Eastern",
    "Washington Mystics":     "US/Eastern",
    "Toronto Tempo":          "US/Eastern",
    "Portland Fire":          "US/Pacific",
}


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_game_logs(year: int) -> pd.DataFrame:
    path = os.path.join(RAW_DIR, f"game_logs_{year}.csv")
    if not os.path.exists(path):
        print(f"  [WARN] Missing game log: {path}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    df["season"] = year

    # Standardize column names from BRef scrape
    rename = {
        "date":         "game_date",
        "visitor/neutral": "away_team",
        "home/neutral": "home_team",
        "pts":          "away_pts",
        "pts.1":        "home_pts",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Parse date
    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")

    # Compute actual spread (home - away) and total
    if "home_pts" in df.columns and "away_pts" in df.columns:
        df["home_pts"]    = pd.to_numeric(df["home_pts"], errors="coerce")
        df["away_pts"]    = pd.to_numeric(df["away_pts"], errors="coerce")
        df["actual_spread"] = df["home_pts"] - df["away_pts"]  # + means home won by X
        df["actual_total"]  = df["home_pts"] + df["away_pts"]

    return df


def load_odds(year: int) -> pd.DataFrame:
    path = os.path.join(RAW_DIR, f"odds_consensus.csv")
    if not os.path.exists(path):
        print(f"  [WARN] Missing odds file: {path}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    df["game_date"]  = df["start_time"].dt.date.astype(str)
    df["game_date"]  = pd.to_datetime(df["game_date"])

    if "season" in df.columns:
        df = df[df["season"] == year].copy()

    return df


def load_team_stats(year: int) -> pd.DataFrame:
    path = os.path.join(RAW_DIR, f"team_advanced_{year}.csv")
    if not os.path.exists(path):
        print(f"  [WARN] Missing team advanced stats: {path}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    df["season"] = year
    df.columns = [c.strip().lower().replace("/", "_").replace(" ", "_") for c in df.columns]

    # Key columns we want: team, ortg, drtg, pace, ts%
    keep = ["team", "season", "ortg", "drtg", "pace", "ts%", "w", "l"]
    existing = [c for c in keep if c in df.columns]
    df = df[existing].copy()

    # Compute net rating
    if "ortg" in df.columns and "drtg" in df.columns:
        df["net_rtg"] = pd.to_numeric(df["ortg"], errors="coerce") - \
                        pd.to_numeric(df["drtg"], errors="coerce")

    return df


# ── Feature Engineering ───────────────────────────────────────────────────────

def add_rest_days(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each game, compute how many days of rest each team had.
    Flags: back_to_back (0 rest days), three_in_four (1 rest day in 3-game stretch).
    """
    df = df.sort_values("game_date").reset_index(drop=True)

    for side in ["home_team", "away_team"]:
        rest_col  = f"{side.split('_')[0]}_rest_days"
        b2b_col   = f"{side.split('_')[0]}_back_to_back"
        t4_col    = f"{side.split('_')[0]}_three_in_four"

        df[rest_col] = None
        df[b2b_col]  = False
        df[t4_col]   = False

        teams = df[side].unique()
        for team in teams:
            mask      = df[side] == team
            team_games = df[mask].copy()

            # Days since last game
            team_games["prev_date"] = team_games["game_date"].shift(1)
            team_games[rest_col]    = (
                team_games["game_date"] - team_games["prev_date"]
            ).dt.days - 1  # -1 because 1 day apart = 0 rest days

            # Back-to-back flag
            team_games[b2b_col] = team_games[rest_col] == 0

            # 3-in-4 flag (3rd game within 4 calendar days)
            team_games["prev_date_2"] = team_games["game_date"].shift(2)
            team_games[t4_col] = (
                (team_games["game_date"] - team_games["prev_date_2"]).dt.days <= 3
            )

            df.loc[mask, rest_col] = team_games[rest_col].values
            df.loc[mask, b2b_col]  = team_games[b2b_col].values
            df.loc[mask, t4_col]   = team_games[t4_col].values

    return df


def add_travel_flag(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag East→West and West→East travel for away teams.
    Cross-country travel (2+ time zones) is the meaningful signal.
    """
    WEST_TEAMS = {"Las Vegas Aces", "Golden State Valkyries", "Seattle Storm",
                  "Los Angeles Sparks", "Phoenix Mercury", "Portland Fire"}
    EAST_TEAMS = {"New York Liberty", "Connecticut Sun", "Atlanta Dream",
                  "Washington Mystics", "Indiana Fever", "Toronto Tempo"}
    CENTRAL_TEAMS = {"Minnesota Lynx", "Chicago Sky", "Dallas Wings"}

    def direction(away, home):
        if away in EAST_TEAMS and home in WEST_TEAMS:
            return "east_to_west"
        elif away in WEST_TEAMS and home in EAST_TEAMS:
            return "west_to_east"
        elif (away in EAST_TEAMS or away in WEST_TEAMS) and home in CENTRAL_TEAMS:
            return "cross_central"
        return "same_region"

    df["travel_direction"] = df.apply(
        lambda r: direction(r.get("away_team", ""), r.get("home_team", "")), axis=1
    )
    df["long_travel"] = df["travel_direction"].isin(["east_to_west", "west_to_east"])
    return df


def add_rolling_efficiency(game_df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Compute rolling net rating proxy using actual score margins.
    Uses last N games for each team going into each matchup.
    """
    game_df = game_df.sort_values("game_date").reset_index(drop=True)

    # Build a per-team game-by-game margin table
    home_records = game_df[["game_date", "home_team", "actual_spread"]].copy()
    home_records.columns = ["game_date", "team", "margin"]

    away_records = game_df[["game_date", "away_team", "actual_spread"]].copy()
    away_records["actual_spread"] = -away_records["actual_spread"]  # Away perspective
    away_records.columns = ["game_date", "team", "margin"]

    all_records = pd.concat([home_records, away_records]).sort_values(["team", "game_date"])
    all_records = all_records[all_records["margin"].notna()]

    # Rolling average margin
    all_records[f"rolling_{window}g_margin"] = (
        all_records.groupby("team")["margin"]
        .transform(lambda x: x.shift(1).rolling(window, min_periods=2).mean())
    )

    # Merge back to game_df for home team
    home_merge = all_records[["game_date", "team", f"rolling_{window}g_margin"]].copy()
    home_merge.columns = ["game_date", "home_team", f"home_rolling_{window}g"]

    away_merge = all_records[["game_date", "team", f"rolling_{window}g_margin"]].copy()
    away_merge.columns = ["game_date", "away_team", f"away_rolling_{window}g"]

    game_df = game_df.merge(home_merge, on=["game_date", "home_team"], how="left")
    game_df = game_df.merge(away_merge, on=["game_date", "away_team"], how="left")

    # Predicted spread from rolling efficiency delta
    game_df[f"pred_spread_rolling_{window}g"] = (
        game_df[f"home_rolling_{window}g"] - game_df[f"away_rolling_{window}g"]
    )

    return game_df


def add_model_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create binary training labels for model evaluation:
    - home_covered: did the home team cover the spread?
    - went_over:    did the game go over the total?
    """
    spread_col = "avg_spread_home_line"
    total_col  = "avg_total_point"

    if "actual_spread" in df.columns and spread_col in df.columns:
        df["home_covered"] = df["actual_spread"] > -df[spread_col]

    if "actual_total" in df.columns and total_col in df.columns:
        df["went_over"] = df["actual_total"] > df[total_col]

    # Closing line value proxy: model prediction vs closing spread
    if "pred_spread_rolling_5g" in df.columns and spread_col in df.columns:
        df["clv_proxy"] = df["pred_spread_rolling_5g"] - (-df[spread_col])

    return df


# ── Main Merge ────────────────────────────────────────────────────────────────

def process_year(year: int) -> pd.DataFrame:
    print(f"\n── Processing season {year} ──")

    game_df  = load_game_logs(year)
    odds_df  = load_odds(year)
    stats_df = load_team_stats(year)

    if game_df.empty:
        print(f"  [SKIP] No game log data for {year}")
        return pd.DataFrame()

    # Add engineered features to game log
    game_df = add_rest_days(game_df)
    game_df = add_travel_flag(game_df)

    if "actual_spread" in game_df.columns:
        game_df = add_rolling_efficiency(game_df, window=5)
        game_df = add_rolling_efficiency(game_df, window=10)

    # Merge odds if available
    if not odds_df.empty:
        # Match on date + teams (fuzzy match by home/away)
        merge_keys = ["game_date", "home_team", "away_team"]
        available_keys = [k for k in merge_keys if k in odds_df.columns and k in game_df.columns]
        merged = game_df.merge(odds_df, on=available_keys, how="left")
        print(f"  Merged odds: {merged[merged['avg_spread_home_line'].notna()].shape[0]} games with lines")
    else:
        merged = game_df.copy()
        print("  [WARN] No odds data — skipping odds merge")

    # Merge season-level team stats (for context, not game-level prediction)
    if not stats_df.empty:
        for side, col in [("home_team", "home"), ("away_team", "away")]:
            side_stats = stats_df.copy()
            side_stats.columns = [
                f"{col}_{c}" if c not in ["team", "season"] else c
                for c in side_stats.columns
            ]
            if "team" in side_stats.columns:
                merged = merged.merge(
                    side_stats.rename(columns={"team": side}),
                    on=[side, "season"],
                    how="left"
                )

    # Add training labels
    merged = add_model_labels(merged)

    print(f"  Final shape: {merged.shape}")
    return merged


def main():
    global RAW_DIR, PROCESSED_DIR
    parser = argparse.ArgumentParser(description="Merge WNBA stats + odds into model-ready dataset")
    parser.add_argument("--year", type=str, default="all", help="Year to process (e.g. 2023) or 'all'")
    parser.add_argument("--raw", type=str, default=RAW_DIR, help="Raw data directory")
    parser.add_argument("--out", type=str, default=PROCESSED_DIR, help="Processed output directory")
    args = parser.parse_args()

    global RAW_DIR, PROCESSED_DIR
    RAW_DIR       = args.raw
    PROCESSED_DIR = args.out
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    if args.year == "all":
        raw_files = glob(os.path.join(RAW_DIR, "game_logs_*.csv"))
        years = sorted([int(f.split("_")[-1].replace(".csv", "")) for f in raw_files])
        print(f"Found seasons: {years}")
    else:
        years = [int(args.year)]

    all_dfs = []
    for year in years:
        df = process_year(year)
        if not df.empty:
            path = os.path.join(PROCESSED_DIR, f"master_{year}.csv")
            df.to_csv(path, index=False)
            print(f"  Saved → {path}")
            all_dfs.append(df)

    if len(all_dfs) > 1:
        master = pd.concat(all_dfs, ignore_index=True)
        master_path = os.path.join(PROCESSED_DIR, "master_all.csv")
        master.to_csv(master_path, index=False)
        print(f"\n✅ Master dataset saved → {master_path}")
        print(f"   Total rows: {len(master)} | Seasons: {master['season'].nunique()}")
        print(f"   Games with spread lines: {master['avg_spread_home_line'].notna().sum() if 'avg_spread_home_line' in master.columns else 'N/A'}")

    print("\n✅ Merge complete.")


if __name__ == "__main__":
    main()
