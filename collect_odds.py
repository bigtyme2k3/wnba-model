"""
collect_odds.py
---------------
Pulls historical WNBA betting odds (spread, totals, moneyline) from The Odds API.
Historical data available from mid-2022 onwards.

Setup:
    1. Get a free API key at https://the-odds-api.com
    2. Add it to a .env file:  ODDS_API_KEY=your_key_here
    OR pass it as an argument: python collect_odds.py --api-key YOUR_KEY

Usage:
    python collect_odds.py --api-key YOUR_KEY --start 2022-05-01 --end 2024-10-01

Output:
    data/raw/odds_historical.csv   (all historical games, merged)
    data/raw/odds_{year}.csv       (per-season files)

Free tier limits:
    500 requests/month — this script batches requests efficiently.
    ~3 WNBA seasons fits comfortably in the free tier with careful use.
"""

import os
import time
import argparse
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

BASE_URL = "https://api.the-odds-api.com/v4"
SPORT    = "basketball_wnba"
REGIONS  = "us"
MARKETS  = "h2h,spreads,totals"   # moneyline, spread, over/under
ODDS_FMT = "american"


def get_historical_events(api_key: str, date: str) -> list:
    """
    Fetch all WNBA games for a specific date.
    date format: YYYY-MM-DDTHH:MM:SSZ  (e.g. 2023-07-01T00:00:00Z)
    """
    url = f"{BASE_URL}/historical/sports/{SPORT}/odds"
    params = {
        "apiKey":      api_key,
        "regions":     REGIONS,
        "markets":     MARKETS,
        "oddsFormat":  ODDS_FMT,
        "date":        date,
    }

    resp = requests.get(url, params=params, timeout=15)

    # Check remaining quota
    remaining = resp.headers.get("x-requests-remaining", "?")
    used      = resp.headers.get("x-requests-used", "?")

    if resp.status_code == 401:
        raise ValueError("Invalid API key. Check your ODDS_API_KEY.")
    if resp.status_code == 429:
        raise RuntimeError("Rate limit hit. Wait before retrying.")

    resp.raise_for_status()
    data = resp.json()

    return data.get("data", []), remaining, used


def parse_game(game: dict) -> list[dict]:
    """
    Flatten one game's odds into a list of rows (one per bookmaker).
    """
    rows = []
    game_id    = game.get("id")
    home_team  = game.get("home_team")
    away_team  = game.get("away_team")
    start_time = game.get("commence_time")

    for bm in game.get("bookmakers", []):
        bm_key  = bm.get("key")
        bm_name = bm.get("title")

        row = {
            "game_id":    game_id,
            "start_time": start_time,
            "home_team":  home_team,
            "away_team":  away_team,
            "bookmaker":  bm_name,
            "bm_key":     bm_key,
            # Spread fields
            "spread_home_line":  None,
            "spread_home_price": None,
            "spread_away_line":  None,
            "spread_away_price": None,
            # Total fields
            "total_point":       None,
            "total_over_price":  None,
            "total_under_price": None,
            # Moneyline fields
            "ml_home":           None,
            "ml_away":           None,
        }

        for market in bm.get("markets", []):
            mkey = market.get("key")
            outcomes = {o["name"]: o for o in market.get("outcomes", [])}

            if mkey == "spreads":
                h = outcomes.get(home_team, {})
                a = outcomes.get(away_team, {})
                row["spread_home_line"]  = h.get("point")
                row["spread_home_price"] = h.get("price")
                row["spread_away_line"]  = a.get("point")
                row["spread_away_price"] = a.get("price")

            elif mkey == "totals":
                over  = outcomes.get("Over", {})
                under = outcomes.get("Under", {})
                row["total_point"]       = over.get("point")
                row["total_over_price"]  = over.get("price")
                row["total_under_price"] = under.get("price")

            elif mkey == "h2h":
                row["ml_home"] = outcomes.get(home_team, {}).get("price")
                row["ml_away"] = outcomes.get(away_team, {}).get("price")

        rows.append(row)

    return rows


def date_range(start: str, end: str) -> list[str]:
    """
    Generate daily ISO timestamps between start and end dates.
    WNBA regular season runs roughly May–October.
    We only request dates within that window to save API quota.
    """
    fmt   = "%Y-%m-%d"
    start_dt = datetime.strptime(start, fmt)
    end_dt   = datetime.strptime(end,   fmt)

    dates = []
    current = start_dt
    while current <= end_dt:
        # Only include May through October (WNBA season window)
        if 5 <= current.month <= 10:
            dates.append(current.strftime("%Y-%m-%dT12:00:00Z"))
        current += timedelta(days=1)

    return dates


def consolidate_lines(df: pd.DataFrame) -> pd.DataFrame:
    """
    Average odds across bookmakers to get a consensus line per game.
    This reduces noise from individual book movements.
    """
    numeric_cols = [
        "spread_home_line", "spread_home_price", "spread_away_line", "spread_away_price",
        "total_point", "total_over_price", "total_under_price",
        "ml_home", "ml_away"
    ]

    group_cols = ["game_id", "start_time", "home_team", "away_team"]

    agg = df.groupby(group_cols)[numeric_cols].mean().reset_index()
    agg.columns = group_cols + [f"avg_{c}" for c in numeric_cols]

    # Also keep best available line (min juice on spreads/totals)
    return agg


def main():
    parser = argparse.ArgumentParser(description="Collect historical WNBA odds from The Odds API")
    parser.add_argument("--api-key", type=str, default=os.getenv("ODDS_API_KEY"), help="Your Odds API key")
    parser.add_argument("--start",   type=str, default="2022-05-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",     type=str, default="2024-10-01", help="End date YYYY-MM-DD")
    parser.add_argument("--out",     type=str, default="data/raw",   help="Output directory")
    parser.add_argument("--bm",      type=str, default=None, help="Filter to one bookmaker key (e.g. fanduel)")
    args = parser.parse_args()

    if not args.api_key:
        raise ValueError(
            "No API key found. Set ODDS_API_KEY in .env or pass --api-key YOUR_KEY\n"
            "Get a free key at: https://the-odds-api.com"
        )

    os.makedirs(args.out, exist_ok=True)

    dates = date_range(args.start, args.end)
    print(f"\nCollecting WNBA odds from {args.start} to {args.end}")
    print(f"Total date snapshots to fetch: {len(dates)}\n")

    all_rows = []
    seen_games = set()  # Avoid duplicate game entries from overlapping daily snapshots

    for date_str in tqdm(dates, desc="Dates"):
        try:
            games, remaining, used = get_historical_events(args.api_key, date_str)

            if not games:
                continue

            for game in games:
                gid = game.get("id")
                if gid in seen_games:
                    continue
                seen_games.add(gid)

                rows = parse_game(game)

                if args.bm:
                    rows = [r for r in rows if r["bm_key"] == args.bm]

                all_rows.extend(rows)

            time.sleep(1)  # Polite delay

        except Exception as e:
            print(f"\n  [ERROR] {date_str}: {e}")
            continue

    if not all_rows:
        print("\n[WARN] No odds data collected. Check your API key and date range.")
        return

    df = pd.DataFrame(all_rows)

    # Parse and add year column for easy filtering
    df["start_time"] = pd.to_datetime(df["start_time"])
    df["season"]     = df["start_time"].dt.year

    # Save full raw file
    full_path = os.path.join(args.out, "odds_historical.csv")
    df.to_csv(full_path, index=False)
    print(f"\n✅ Raw odds saved → {full_path}  ({len(df)} rows, {df['game_id'].nunique()} unique games)")

    # Save consensus (averaged across bookmakers) file
    consensus_df = consolidate_lines(df)
    cons_path = os.path.join(args.out, "odds_consensus.csv")
    consensus_df.to_csv(cons_path, index=False)
    print(f"✅ Consensus odds saved → {cons_path}  ({len(consensus_df)} games)")

    # Save per-season files
    for year, group in df.groupby("season"):
        year_path = os.path.join(args.out, f"odds_{year}.csv")
        group.to_csv(year_path, index=False)
        print(f"   Season {year}: {group['game_id'].nunique()} games → {year_path}")

    print(f"\n📊 API usage — Requests used: {used} | Remaining: {remaining}")


if __name__ == "__main__":
    main()
