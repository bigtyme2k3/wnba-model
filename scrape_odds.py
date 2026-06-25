"""
scrape_odds.py — Scrapes WNBA spreads, totals, moneylines from OddsShark.
No API key required. Public HTML page.

Target: https://www.oddsshark.com/wnba/odds
Output: data/raw/odds_today.csv  |  data/raw/odds_YYYY-MM-DD.csv  |  data/raw/odds_historical.csv
Usage:  python scrape_odds.py
        python scrape_odds.py --historical   (also pulls closing-line game logs)
"""

import os, re, time, argparse, json
from datetime import date, datetime
import requests, pandas as pd
from bs4 import BeautifulSoup

OUT_DIR = "data/raw"
URL     = "https://www.oddsshark.com/wnba/odds"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.oddsshark.com/wnba",
}

TEAM_MAP = {
    "Atlanta":"Atlanta Dream","Chicago":"Chicago Sky","Connecticut":"Connecticut Sun",
    "Dallas":"Dallas Wings","Golden State":"Golden State Valkyries","Indiana":"Indiana Fever",
    "Las Vegas":"Las Vegas Aces","Los Angeles":"Los Angeles Sparks","Minnesota":"Minnesota Lynx",
    "New York":"New York Liberty","Phoenix":"Phoenix Mercury","Portland":"Portland Fire",
    "Seattle":"Seattle Storm","Toronto":"Toronto Tempo","Washington":"Washington Mystics",
}

def norm(raw):
    raw = raw.strip()
    for k, v in TEAM_MAP.items():
        if k.lower() in raw.lower(): return v
    return raw

def parse_num(s):
    try:
        s = str(s).replace("½",".5").replace("PK","0").strip()
        m = re.search(r"[-+]?\d+\.?\d*", s)
        return float(m.group()) if m else None
    except: return None

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def parse_page(soup, target_date):
    rows = []

    # Method 1: Next.js __NEXT_DATA__ JSON blob (most reliable)
    for script in soup.find_all("script"):
        txt = script.string or ""
        if "__NEXT_DATA__" in txt:
            try:
                raw = re.search(r'__NEXT_DATA__\s*=\s*(\{.*\})', txt, re.DOTALL)
                if raw:
                    data  = json.loads(raw.group(1))
                    games = (data.get("props",{}).get("pageProps",{})
                                 .get("oddsData", data.get("props",{})
                                 .get("pageProps",{}).get("matchups",[])))
                    for g in games:
                        teams = g.get("teams", g.get("participants",[]))
                        if len(teams) < 2: continue
                        c = g.get("consensus", g.get("odds",{}))
                        sp = c.get("spread",{})
                        tot = c.get("total",{})
                        ml  = c.get("moneyLine", c.get("moneyline",{}))
                        rows.append({
                            "game_date":  target_date,
                            "home_team":  norm(teams[-1].get("name", teams[-1].get("fullName",""))),
                            "away_team":  norm(teams[0].get("name",  teams[0].get("fullName",""))),
                            "spread_home": sp.get("home"),
                            "spread_away": sp.get("away"),
                            "total":       tot.get("total"),
                            "total_over_juice":  tot.get("overOdds"),
                            "total_under_juice": tot.get("underOdds"),
                            "ml_home":    ml.get("home"),
                            "ml_away":    ml.get("away"),
                            "game_time":  g.get("gameDateTime",""),
                            "source":     "oddsshark",
                            "scraped_at": datetime.now().isoformat(),
                        })
                    if rows:
                        print(f"  [{len(rows)} games parsed from JSON blob]")
                        return rows
            except: pass

    # Method 2: HTML table fallback
    print("  [Falling back to HTML table parsing]")
    teams = [norm(t.get_text(strip=True)) for t in soup.select(".op-matchup-team")]
    cells = soup.select(".op-item")
    for i in range(0, len(teams)-1, 2):
        try:
            b = (i//2) * 6
            rows.append({
                "game_date":   target_date,
                "away_team":   teams[i],
                "home_team":   teams[i+1],
                "spread_away": parse_num(cells[b].get_text()),
                "spread_home": parse_num(cells[b+1].get_text()),
                "total":       parse_num(cells[b+2].get_text().replace("O","").replace("U","")),
                "ml_away":     parse_num(cells[b+4].get_text()),
                "ml_home":     parse_num(cells[b+5].get_text()),
                "source":      "oddsshark",
                "scraped_at":  datetime.now().isoformat(),
            })
        except: continue

    return rows

def scrape_historical_gamelogs(out_dir):
    """Pull closing-line game logs from OddsShark team pages (2022-present)."""
    TEAM_IDS = {
        "Atlanta Dream":28,"Chicago Sky":29,"Connecticut Sun":30,"Dallas Wings":31,
        "Indiana Fever":32,"Las Vegas Aces":33,"Los Angeles Sparks":34,
        "Minnesota Lynx":35,"New York Liberty":36,"Phoenix Mercury":37,
        "Seattle Storm":38,"Washington Mystics":39,
    }
    all_rows = []
    for team, tid in TEAM_IDS.items():
        url = f"https://www.oddsshark.com/stats/gamelog/basketball/wnba/{tid}"
        print(f"  {team}...", end="", flush=True)
        try:
            soup  = fetch(url)
            table = soup.find("table", {"id":"game-log"}) or soup.find("table")
            if table:
                df = pd.read_html(str(table))[0]
                df["team"] = team
                all_rows.append(df)
                print(f" {len(df)} games")
            else:
                print(" no table found")
            time.sleep(3)
        except Exception as e:
            print(f" error: {e}")
    if all_rows:
        master = pd.concat(all_rows, ignore_index=True)
        path = os.path.join(out_dir, "odds_historical_gamelogs.csv")
        master.to_csv(path, index=False)
        print(f"\n  Saved {len(master)} rows → {path}")
    return pd.DataFrame() if not all_rows else master

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",       default=None)
    parser.add_argument("--out",        default="data/raw")
    parser.add_argument("--historical", action="store_true")
    args = parser.parse_args()

    target = args.date or str(date.today())
    os.makedirs(args.out, exist_ok=True)

    print(f"Scraping OddsShark WNBA odds — {target}")
    soup = fetch(URL)
    rows = parse_page(soup, target)

    if not rows:
        print("  [WARN] No games found. OddsShark may have no WNBA games posted today.")
        return

    df = pd.DataFrame(rows)

    today_path = os.path.join(args.out, "odds_today.csv")
    dated_path = os.path.join(args.out, f"odds_{target}.csv")
    hist_path  = os.path.join(args.out, "odds_historical.csv")

    df.to_csv(today_path, index=False)
    df.to_csv(dated_path, index=False)

    if os.path.exists(hist_path):
        hist = pd.read_csv(hist_path)
        hist = hist[hist["game_date"] != target]
        pd.concat([hist, df], ignore_index=True).to_csv(hist_path, index=False)
    else:
        df.to_csv(hist_path, index=False)

    print(f"\n  {len(df)} games saved:")
    display_cols = [c for c in ["away_team","home_team","spread_home","total","ml_home"] if c in df.columns]
    print(df[display_cols].to_string(index=False))
    print(f"\n  → {today_path}")
    print(f"  → {dated_path}")

    if args.historical:
        print("\nScraping historical closing-line game logs...")
        scrape_historical_gamelogs(args.out)

    print("\n✅ Odds scrape complete.")

if __name__ == "__main__":
    main()
