"""
scrape_odds.py
--------------
Fetches WNBA spreads, totals, and moneylines from The Odds API.
Free tier: 500 requests/month — well within daily WNBA use.

Requires: ODDS_API_KEY environment variable (GitHub Secret)

Usage:
    python scrape_odds.py
    python scrape_odds.py --date 2026-07-04
"""

import os, json, argparse, requests, pandas as pd
from datetime import date, datetime

API_KEY  = os.getenv("ODDS_API_KEY")
SPORT    = "basketball_wnba"
REGIONS  = "us"
MARKETS  = "h2h,spreads,totals"
ODDS_FMT = "american"
BASE_URL = "https://api.the-odds-api.com/v4/sports"

TEAM_MAP = {
    "Atlanta Dream":          "Atlanta Dream",
    "Chicago Sky":            "Chicago Sky",
    "Connecticut Sun":        "Connecticut Sun",
    "Dallas Wings":           "Dallas Wings",
    "Golden State Valkyries": "Golden State Valkyries",
    "Indiana Fever":          "Indiana Fever",
    "Las Vegas Aces":         "Las Vegas Aces",
    "Los Angeles Sparks":     "Los Angeles Sparks",
    "Minnesota Lynx":         "Minnesota Lynx",
    "New York Liberty":       "New York Liberty",
    "Phoenix Mercury":        "Phoenix Mercury",
    "Portland Fire":          "Portland Fire",
    "Seattle Storm":          "Seattle Storm",
    "Toronto Tempo":          "Toronto Tempo",
    "Washington Mystics":     "Washington Mystics",
}

def fetch_odds():
    if not API_KEY:
        raise ValueError("ODDS_API_KEY not set. Add it as a GitHub Secret.")

    url = f"{BASE_URL}/{SPORT}/odds"
    params = {
        "apiKey":     API_KEY,
        "regions":    REGIONS,
        "markets":    MARKETS,
        "oddsFormat": ODDS_FMT,
    }

    resp = requests.get(url, params=params, timeout=15)

    # Log quota usage
    remaining = resp.headers.get("x-requests-remaining", "?")
    used      = resp.headers.get("x-requests-used", "?")
    print(f"  API quota — used: {used} | remaining: {remaining}")

    if resp.status_code == 401:
        raise ValueError("Invalid API key.")
    if resp.status_code == 422:
        print("  [INFO] No WNBA games currently available.")
        return []

    resp.raise_for_status()
    return resp.json()


def parse_games(games: list, target_date: str) -> pd.DataFrame:
    rows = []
    for g in games:
        home = g.get("home_team","")
        away = g.get("away_team","")
        start= g.get("commence_time","")
        gid  = g.get("id","")

        # Average lines across bookmakers
        spread_home_lines, spread_home_prices = [], []
        total_points, total_over_prices       = [], []
        ml_home_prices, ml_away_prices        = [], []

        for bm in g.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                key      = mkt.get("key")
                outcomes = {o["name"]: o for o in mkt.get("outcomes", [])}

                if key == "spreads":
                    h = outcomes.get(home, {})
                    if h.get("point") is not None:
                        spread_home_lines.append(h["point"])
                    if h.get("price") is not None:
                        spread_home_prices.append(h["price"])

                elif key == "totals":
                    ov = outcomes.get("Over", {})
                    if ov.get("point") is not None:
                        total_points.append(ov["point"])
                    if ov.get("price") is not None:
                        total_over_prices.append(ov["price"])

                elif key == "h2h":
                    if outcomes.get(home, {}).get("price") is not None:
                        ml_home_prices.append(outcomes[home]["price"])
                    if outcomes.get(away, {}).get("price") is not None:
                        ml_away_prices.append(outcomes[away]["price"])

        def avg(lst): return round(sum(lst)/len(lst), 2) if lst else None

        rows.append({
            "game_date":        target_date,
            "game_id":          gid,
            "commence_time":    start,
            "home_team":        home,
            "away_team":        away,
            "spread_home":      avg(spread_home_lines),
            "spread_home_juice":avg(spread_home_prices),
            "total":            avg(total_points),
            "total_over_juice": avg(total_over_prices),
            "ml_home":          avg(ml_home_prices),
            "ml_away":          avg(ml_away_prices),
            "num_books":        len(g.get("bookmakers", [])),
            "source":           "the-odds-api",
            "scraped_at":       datetime.now().isoformat(),
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out",  default="data/raw")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    target = args.date

    print(f"Fetching WNBA odds from The Odds API — {target}")
    games = fetch_odds()

    if not games:
        print("  No games found. Writing empty odds file.")
        df = pd.DataFrame()
    else:
        df = parse_games(games, target)
        print(f"  Parsed {len(df)} games | Books per game: {df['num_books'].mean():.1f}")
        print(f"  Lines found: {df['spread_home'].notna().sum()} spreads, {df['total'].notna().sum()} totals")

    # Save
    today_path = os.path.join(args.out, "odds_today.csv")
    dated_path = os.path.join(args.out, f"odds_{target}.csv")
    hist_path  = os.path.join(args.out, "odds_historical.csv")

    df.to_csv(today_path, index=False)
    df.to_csv(dated_path, index=False)

    if os.path.exists(hist_path) and not df.empty:
        hist = pd.read_csv(hist_path)
        hist = hist[hist["game_date"] != target]
        pd.concat([hist, df], ignore_index=True).to_csv(hist_path, index=False)
    elif not df.empty:
        df.to_csv(hist_path, index=False)

    if not df.empty:
        print(f"\n  Today's lines:")
        cols = [c for c in ["away_team","home_team","spread_home","total","ml_home"] if c in df.columns]
        print(df[cols].to_string(index=False))

    print(f"\n  Saved → {today_path}")
    print("✅ Odds scrape complete.")


if __name__ == "__main__":
    main()
