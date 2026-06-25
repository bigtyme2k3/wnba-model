"""
collect_stats.py
----------------
Scrapes WNBA team + player stats from Basketball-Reference.
Covers: team totals, advanced team stats, player per-game stats, player advanced stats.

Usage:
    python collect_stats.py --start 2020 --end 2024

Output:
    data/raw/team_stats_{year}.csv
    data/raw/team_advanced_{year}.csv
    data/raw/player_stats_{year}.csv
    data/raw/player_advanced_{year}.csv
    data/raw/game_logs_{year}.csv
"""

import os
import time
import argparse
import requests
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://www.basketball-reference.com/wnba"
HEADERS = {"User-Agent": "Mozilla/5.0 (research project; contact: you@email.com)"}

# Be polite — Basketball-Reference rate limits aggressive scrapers
REQUEST_DELAY = 4  # seconds between requests


def get_soup(url: str) -> BeautifulSoup:
    """Fetch a page and return a BeautifulSoup object."""
    time.sleep(REQUEST_DELAY)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def parse_table(soup: BeautifulSoup, table_id: str) -> pd.DataFrame:
    """Parse a specific HTML table by its ID into a DataFrame."""
    table = soup.find("table", {"id": table_id})
    if table is None:
        print(f"  [WARN] Table '{table_id}' not found.")
        return pd.DataFrame()

    # Remove header rows nested inside tbody (Basketball-Reference quirk)
    for row in table.find_all("tr", class_="thead"):
        row.decompose()

    df = pd.read_html(str(table))[0]

    # Drop rows where the first column is the column name (repeated headers)
    first_col = df.columns[0]
    df = df[df[first_col] != first_col].reset_index(drop=True)

    return df


# ── Team Stats ────────────────────────────────────────────────────────────────

def collect_team_stats(year: int, out_dir: str):
    url = f"{BASE_URL}/years/{year}.html"
    print(f"  Fetching team stats: {url}")
    soup = get_soup(url)

    tables = {
        "team_stats":    "per_game-team",
        "team_advanced": "advanced-team",
    }

    for name, table_id in tables.items():
        df = parse_table(soup, table_id)
        if not df.empty:
            df["season"] = year
            path = os.path.join(out_dir, f"{name}_{year}.csv")
            df.to_csv(path, index=False)
            print(f"    Saved {len(df)} rows → {path}")


# ── Player Stats ──────────────────────────────────────────────────────────────

def collect_player_stats(year: int, out_dir: str):
    url = f"{BASE_URL}/years/{year}_per_game.html"
    print(f"  Fetching player per-game stats: {url}")
    soup = get_soup(url)

    df = parse_table(soup, "per_game_stats")
    if not df.empty:
        df["season"] = year
        path = os.path.join(out_dir, f"player_stats_{year}.csv")
        df.to_csv(path, index=False)
        print(f"    Saved {len(df)} rows → {path}")

    # Advanced player stats (same page, different table)
    url_adv = f"{BASE_URL}/years/{year}_advanced.html"
    print(f"  Fetching player advanced stats: {url_adv}")
    soup_adv = get_soup(url_adv)

    df_adv = parse_table(soup_adv, "advanced_stats")
    if not df_adv.empty:
        df_adv["season"] = year
        path_adv = os.path.join(out_dir, f"player_advanced_{year}.csv")
        df_adv.to_csv(path_adv, index=False)
        print(f"    Saved {len(df_adv)} rows → {path_adv}")


# ── Game Logs ─────────────────────────────────────────────────────────────────

def collect_game_logs(year: int, out_dir: str):
    """
    Scrapes the full schedule + results page for a given season.
    This gives us actual game outcomes for model validation.
    """
    url = f"{BASE_URL}/years/{year}_games.html"
    print(f"  Fetching game logs: {url}")
    soup = get_soup(url)

    df = parse_table(soup, "schedule")
    if not df.empty:
        df["season"] = year

        # Clean up column names
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Drop rows with no result yet (future games)
        if "pts" in df.columns:
            df = df[df["pts"].notna() & (df["pts"] != "")]

        path = os.path.join(out_dir, f"game_logs_{year}.csv")
        df.to_csv(path, index=False)
        print(f"    Saved {len(df)} rows → {path}")


# ── Schedule with Opponent + Rest Days ────────────────────────────────────────

def collect_schedule(year: int, out_dir: str):
    """
    Pulls the full schedule so we can calculate rest days and travel flags.
    Includes future games (used for live prediction pipeline later).
    """
    url = f"{BASE_URL}/years/{year}_games.html"
    print(f"  Fetching full schedule: {url}")
    soup = get_soup(url)

    df = parse_table(soup, "schedule")
    if not df.empty:
        df["season"] = year
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        path = os.path.join(out_dir, f"schedule_{year}.csv")
        df.to_csv(path, index=False)
        print(f"    Saved {len(df)} rows → {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Collect WNBA stats from Basketball-Reference")
    parser.add_argument("--start", type=int, default=2020, help="First season year (e.g. 2020)")
    parser.add_argument("--end",   type=int, default=2024, help="Last season year (e.g. 2024)")
    parser.add_argument("--out",   type=str, default="data/raw", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    years = list(range(args.start, args.end + 1))
    print(f"\nCollecting WNBA stats for seasons: {years}\n")

    for year in tqdm(years, desc="Seasons"):
        print(f"\n── Season {year} ──")
        try:
            collect_team_stats(year, args.out)
            collect_player_stats(year, args.out)
            collect_game_logs(year, args.out)
            collect_schedule(year, args.out)
        except Exception as e:
            print(f"  [ERROR] Season {year} failed: {e}")
            continue

    print("\n✅ Stats collection complete.")
    print(f"   Files saved to: {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
