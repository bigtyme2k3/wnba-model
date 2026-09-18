"""
scrape_scores.py — Live WNBA scores and results from ESPN's public API.
No auth, no key. Clean JSON.

Endpoints:
  Today's scoreboard: https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard
  Specific date:      ...?dates=YYYYMMDD
  Game summary:       https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event={game_id}

Output:
  data/raw/scores_today.csv          — today's scores (updates live)
  data/raw/scores_YYYY-MM-DD.csv     — daily snapshot
  data/raw/scores_historical.csv     — master file, appended daily

Usage:
  python scrape_scores.py                         # today
  python scrape_scores.py --date 2026-05-10       # specific date
  python scrape_scores.py --historical 2022 2024  # bulk historical pull
  python scrape_scores.py --live                  # poll every 2 min during games
"""

import io, os, time, argparse
from datetime import date, datetime, timedelta
import requests, pandas as pd

OUT_DIR      = "data/raw"
ESPN_BASE    = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"
BOARD_URL    = f"{ESPN_BASE}/scoreboard"
SUMMARY_URL  = f"{ESPN_BASE}/summary"
WNBA_SCHEDULE_URL = "https://cdn.wnba.com/static/json/staticData/scheduleLeagueV2.json"
SPORTSDATAVERSE_SCHEDULE_URL = (
    "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
    "espn_wnba_schedules/wnba_schedule_{year}.csv"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept":     "application/json",
}


def fetch_scoreboard(target_date: str = None) -> dict:
    """Fetch ESPN scoreboard for a date (YYYY-MM-DD) or today."""
    params = {}
    if target_date:
        params["dates"] = target_date.replace("-","")  # ESPN wants YYYYMMDD
    resp = requests.get(BOARD_URL, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_game_summary(game_id: str) -> dict:
    """Fetch detailed game summary including box score and betting info."""
    resp = requests.get(SUMMARY_URL, headers=HEADERS, params={"event": game_id}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_official_schedule() -> dict:
    """Fetch the WNBA's public season schedule and final-score feed."""
    resp = requests.get(WNBA_SCHEDULE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_sportsdataverse_schedule(target_date: str) -> pd.DataFrame:
    """Fetch the current SportsDataverse ESPN-backed WNBA schedule release."""
    url = SPORTSDATAVERSE_SCHEDULE_URL.format(year=target_date[:4])
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), low_memory=False)


def official_game_date(value) -> str:
    text = str(value or "").strip()
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if "%H" in fmt else text[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def official_team_name(team: dict) -> str:
    city = str(team.get("teamCity") or "").strip()
    name = str(team.get("teamName") or team.get("teamNickname") or "").strip()
    full = " ".join(part for part in (city, name) if part)
    return full or str(team.get("teamTricode") or "").strip()


def parse_official_schedule(data: dict, target_date: str) -> pd.DataFrame:
    """Normalize final scores from the official WNBA CDN schedule payload."""
    schedule = data.get("leagueSchedule") or {}
    rows = []
    for date_block in schedule.get("gameDates") or []:
        block_date = official_game_date(date_block.get("gameDate"))
        for game in date_block.get("games") or []:
            game_date = block_date or official_game_date(game.get("gameDateTimeEst"))
            if game_date != target_date:
                continue
            away = game.get("awayTeam") or {}
            home = game.get("homeTeam") or {}
            status_text = str(game.get("gameStatusText") or "").strip()
            status_code = game.get("gameStatus")
            is_final = str(status_code) == "3" or status_text.upper().startswith("FINAL")
            away_score = away.get("score")
            home_score = home.get("score")
            try:
                away_score = int(away_score) if away_score not in (None, "") else None
                home_score = int(home_score) if home_score not in (None, "") else None
            except (TypeError, ValueError):
                away_score = home_score = None
            rows.append({
                "game_date": target_date,
                "event_start_utc": game.get("gameDateTimeUTC") or "",
                "game_id": str(game.get("gameId") or ""),
                "status": "STATUS_FINAL" if is_final else status_text or f"STATUS_{status_code}",
                "is_final": is_final,
                "in_progress": str(status_code) == "2",
                "home_team": official_team_name(home),
                "away_team": official_team_name(away),
                "home_score": home_score,
                "away_score": away_score,
                "actual_spread": home_score - away_score if home_score is not None and away_score is not None else None,
                "actual_total": home_score + away_score if home_score is not None and away_score is not None else None,
                "posted_spread": "",
                "posted_total": None,
                "venue": str((game.get("arena") or {}).get("arenaName") or ""),
                "attendance": None,
                "source": "wnba_official_schedule_cdn",
                "scraped_at": datetime.now().isoformat(),
            })
    return pd.DataFrame(rows)


def parse_sportsdataverse_schedule(data: pd.DataFrame, target_date: str) -> pd.DataFrame:
    """Normalize exact-date results from SportsDataverse's WNBA schedule release."""
    if data.empty or "game_date" not in data.columns:
        return pd.DataFrame()

    def clean(value, default=""):
        return default if pd.isna(value) else value

    def score(value):
        if pd.isna(value) or value == "":
            return None
        return int(float(value))

    def truthy(value) -> bool:
        if isinstance(value, bool):
            return value
        return str(clean(value)).strip().lower() in {"1", "true", "yes"}

    rows = []
    exact_date = data[data["game_date"].astype(str).str[:10] == target_date]
    for _, game in exact_date.iterrows():
        status = str(clean(game.get("status_type_name"))).strip()
        state = str(clean(game.get("status_type_state"))).strip().lower()
        is_final = truthy(game.get("status_type_completed")) or "FINAL" in status.upper()
        home_score = score(game.get("home_score"))
        away_score = score(game.get("away_score"))
        game_id = clean(game.get("game_id"), clean(game.get("id")))
        rows.append({
            "game_date": target_date,
            "event_start_utc": str(clean(game.get("date"), clean(game.get("start_date")))),
            "game_id": str(game_id),
            "status": status,
            "is_final": is_final,
            "in_progress": state == "in",
            "home_team": str(clean(game.get("home_display_name"))),
            "away_team": str(clean(game.get("away_display_name"))),
            "home_score": home_score,
            "away_score": away_score,
            "actual_spread": home_score - away_score if home_score is not None and away_score is not None else None,
            "actual_total": home_score + away_score if home_score is not None and away_score is not None else None,
            "posted_spread": "",
            "posted_total": None,
            "venue": str(clean(game.get("venue_full_name"))),
            "attendance": score(game.get("attendance")),
            "source": "sportsdataverse_espn_schedule_release",
            "scraped_at": datetime.now().isoformat(),
        })
    return pd.DataFrame(rows)


def parse_scoreboard(data: dict, target_date: str) -> pd.DataFrame:
    """Parse ESPN scoreboard JSON into a clean game-level DataFrame."""
    events = data.get("events", [])
    rows   = []

    for event in events:
        game_id   = event.get("id")
        event_start_utc = event.get("date", "")
        # ESPN event timestamps are UTC, so evening WNBA games commonly cross
        # into the next UTC date. The requested scoreboard date is the league
        # slate date and must remain the grading key.
        game_date = target_date or event_start_utc[:10]
        status    = event.get("status", {})
        state     = status.get("type", {}).get("name","")  # STATUS_FINAL, STATUS_IN_PROGRESS, etc.

        comps = event.get("competitions", [{}])[0]
        competitors = comps.get("competitors", [])

        if len(competitors) < 2:
            continue

        # ESPN: homeAway field identifies which is home
        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home_team  = home.get("team", {}).get("displayName","")
        away_team  = away.get("team", {}).get("displayName","")
        home_score = home.get("score")
        away_score = away.get("score")

        # Betting line if available
        odds_obj   = comps.get("odds", [{}])
        spread     = odds_obj[0].get("details","")  if odds_obj else ""  # e.g. "NYL -8.5"
        over_under = odds_obj[0].get("overUnder")   if odds_obj else None

        # Period scores
        home_line_scores = [ls.get("value") for ls in home.get("linescores",[])]
        away_line_scores = [ls.get("value") for ls in away.get("linescores",[])]

        row = {
            "game_date":    game_date or target_date,
            "event_start_utc": event_start_utc,
            "game_id":      game_id,
            "status":       state,
            "is_final":     "FINAL" in state.upper(),
            "in_progress":  "IN_PROGRESS" in state.upper() or "PROGRESS" in state.upper(),
            "home_team":    home_team,
            "away_team":    away_team,
            "home_score":   int(home_score) if home_score is not None else None,
            "away_score":   int(away_score) if away_score is not None else None,
            "actual_spread":int(home_score) - int(away_score) if (home_score and away_score) else None,
            "actual_total": int(home_score) + int(away_score) if (home_score and away_score) else None,
            "home_q1":      home_line_scores[0] if len(home_line_scores) > 0 else None,
            "home_q2":      home_line_scores[1] if len(home_line_scores) > 1 else None,
            "home_q3":      home_line_scores[2] if len(home_line_scores) > 2 else None,
            "home_q4":      home_line_scores[3] if len(home_line_scores) > 3 else None,
            "away_q1":      away_line_scores[0] if len(away_line_scores) > 0 else None,
            "away_q2":      away_line_scores[1] if len(away_line_scores) > 1 else None,
            "away_q3":      away_line_scores[2] if len(away_line_scores) > 2 else None,
            "away_q4":      away_line_scores[3] if len(away_line_scores) > 3 else None,
            "posted_spread":spread,
            "posted_total": over_under,
            "venue":        comps.get("venue",{}).get("fullName",""),
            "attendance":   comps.get("attendance"),
            "source":       "espn_scoreboard",
            "scraped_at":   datetime.now().isoformat(),
        }
        rows.append(row)

    return pd.DataFrame(rows)


def parse_box_score(summary: dict, game_id: str, target_date: str | None = None) -> pd.DataFrame:
    """
    Extract player-level box score from ESPN game summary.
    Returns a DataFrame with one row per player per game.
    Useful for updating rolling stats in real time.
    """
    rows = []
    event_start_utc = summary.get("header",{}).get("competitions",[{}])[0].get("date","")
    game_date = target_date or event_start_utc[:10]

    for team_data in summary.get("boxscore",{}).get("players",[]):
        team_name = team_data.get("team",{}).get("displayName","")
        for stat_group in team_data.get("statistics",[]):
            labels  = stat_group.get("labels",[])
            for athlete in stat_group.get("athletes",[]):
                stats   = athlete.get("stats",[])
                player  = athlete.get("athlete",{})
                stat_dict = dict(zip(labels, stats))

                def g(key, default=None):
                    val = stat_dict.get(key, default)
                    try: return float(val) if val not in (None,"--","") else default
                    except: return default

                rows.append({
                    "game_date": game_date,
                    "event_start_utc": event_start_utc,
                    "game_id":   game_id,
                    "player":    player.get("displayName",""),
                    "team":      team_name,
                    "position":  player.get("position",{}).get("abbreviation",""),
                    "starter":   athlete.get("starter", False),
                    "minutes":   g("MIN"),
                    "pts":       g("PTS"),
                    "reb":       g("REB"),
                    "ast":       g("AST"),
                    "stl":       g("STL"),
                    "blk":       g("BLK"),
                    "tov":       g("TO"),
                    "fgm":       g("FGM"),
                    "fga":       g("FGA"),
                    "threes":    g("3PM"),
                    "threes_att":g("3PA"),
                    "ftm":       g("FTM"),
                    "fta":       g("FTA"),
                    "plus_minus":g("+/-"),
                    "scraped_at":datetime.now().isoformat(),
                })

    return pd.DataFrame(rows)


def save(df, path, append_to_hist=True, hist_key="game_date"):
    """Save DataFrame to path and optionally append to historical master."""
    df.to_csv(path, index=False)
    if append_to_hist and not df.empty:
        base = os.path.dirname(path)
        name = os.path.basename(path)
        # Derive historical filename
        hist_name = re.sub(r"_\d{4}-\d{2}-\d{2}", "", name).replace("today","historical")
        hist_path = os.path.join(base, hist_name)
        if os.path.exists(hist_path):
            hist = pd.read_csv(hist_path)
            if hist_key in hist.columns and hist_key in df.columns:
                today_dates = df[hist_key].unique()
                hist = hist[~hist[hist_key].isin(today_dates)]
            pd.concat([hist, df], ignore_index=True).to_csv(hist_path, index=False)
        else:
            df.to_csv(hist_path, index=False)

import re

def scrape_date(target_date: str, out_dir: str, include_boxscores: bool = False) -> pd.DataFrame:
    os.makedirs(out_dir, exist_ok=True)

    print(f"Fetching ESPN WNBA scores — {target_date}")
    df = pd.DataFrame()
    try:
        df = parse_scoreboard(fetch_scoreboard(target_date), target_date)
    except (requests.RequestException, ValueError) as exc:
        print(f"  ESPN scoreboard unavailable ({type(exc).__name__}).")

    if df.empty:
        print("  Checking official WNBA schedule feed.")
        try:
            df = parse_official_schedule(fetch_official_schedule(), target_date)
        except (requests.RequestException, ValueError) as exc:
            print(f"  Official WNBA schedule unavailable ({type(exc).__name__}).")

    if df.empty:
        print("  Checking SportsDataverse WNBA schedule release.")
        try:
            release = fetch_sportsdataverse_schedule(target_date)
            df = parse_sportsdataverse_schedule(release, target_date)
        except (requests.RequestException, ValueError, pd.errors.ParserError) as exc:
            print(f"  SportsDataverse schedule unavailable ({type(exc).__name__}).")
            raise RuntimeError(f"No verified WNBA result source available for {target_date}") from exc

    if df.empty:
        print("  No games found for this date.")
        return df

    finals    = df[df["is_final"]].shape[0]
    live      = df[df["in_progress"]].shape[0]
    scheduled = df.shape[0] - finals - live
    print(f"  {df.shape[0]} games: {finals} final  |  {live} live  |  {scheduled} upcoming")

    today_path = os.path.join(out_dir, "scores_today.csv")
    dated_path = os.path.join(out_dir, f"scores_{target_date}.csv")
    df.to_csv(today_path, index=False)
    save(df, dated_path, append_to_hist=True, hist_key="game_date")

    # Print summary table
    show_cols = [c for c in ["away_team","home_team","away_score","home_score","actual_spread","status"] if c in df.columns]
    print(f"\n  {'AWAY':<24} {'HOME':<24} {'AWAY':>5} {'HOME':>5} {'SPREAD':>7}  STATUS")
    print("  " + "─"*75)
    for _, r in df.iterrows():
        aw = str(r.get("away_score","—") or "—")
        hw = str(r.get("home_score","—") or "—")
        sp = f"{r['actual_spread']:+.0f}" if r.get("actual_spread") is not None else "—"
        st = r.get("status","").replace("STATUS_","")
        print(f"  {r['away_team']:<24} {r['home_team']:<24} {aw:>5} {hw:>5} {sp:>7}  {st}")

    # Optional: pull full box scores for completed games
    if include_boxscores:
        print(f"\n  Fetching box scores for {finals} completed games...")
        box_rows = []
        for _, game in df[df["is_final"]].iterrows():
            try:
                summary = fetch_game_summary(str(game["game_id"]))
                box_df  = parse_box_score(summary, str(game["game_id"]), target_date)
                box_rows.append(box_df)
                time.sleep(1)
            except Exception as e:
                print(f"    Error for game {game['game_id']}: {e}")
        if box_rows:
            box_master = pd.concat(box_rows, ignore_index=True)
            box_path   = os.path.join(out_dir, f"boxscores_{target_date}.csv")
            box_master.to_csv(box_path, index=False)
            print(f"  Box scores → {box_path}  ({len(box_master)} player rows)")

    return df


def scrape_historical(start_year: int, end_year: int, out_dir: str):
    """Pull all results from start_year through end_year."""
    os.makedirs(out_dir, exist_ok=True)
    all_dfs = []

    for year in range(start_year, end_year + 1):
        # WNBA season: roughly May 15 – Sept 20
        start = date(year, 5, 14)
        end   = date(year, 9, 22)
        current = start
        season_rows = []

        print(f"\nSeason {year}:")
        while current <= end:
            try:
                data = fetch_scoreboard(str(current))
                df   = parse_scoreboard(data, str(current))
                if not df.empty and df["is_final"].any():
                    season_rows.append(df[df["is_final"]])
                    print(f"  {current}: {df['is_final'].sum()} final games", end="\r")
            except Exception as e:
                print(f"  {current}: error — {e}")
            current += timedelta(days=1)
            time.sleep(1.5)  # Polite

        if season_rows:
            season_df = pd.concat(season_rows, ignore_index=True)
            path = os.path.join(out_dir, f"scores_{year}.csv")
            season_df.to_csv(path, index=False)
            print(f"\n  Season {year}: {len(season_df)} games → {path}")
            all_dfs.append(season_df)

    if all_dfs:
        master = pd.concat(all_dfs, ignore_index=True)
        master.to_csv(os.path.join(out_dir, "scores_historical.csv"), index=False)
        print(f"\n✅ Historical scores: {len(master)} games saved.")


def live_poll(out_dir: str, interval: int = 120):
    """Poll every `interval` seconds during live games."""
    print(f"Live polling every {interval}s. Ctrl+C to stop.\n")
    while True:
        today = str(date.today())
        df = scrape_date(today, out_dir)
        live = df[df["in_progress"]].shape[0] if not df.empty else 0
        if live == 0:
            print("\nNo live games. Polling slowed to 10 min.")
            time.sleep(600)
        else:
            print(f"\n{live} games live. Next update in {interval}s...")
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",       default=None)
    parser.add_argument("--out",        default="data/raw")
    parser.add_argument("--boxscores",  action="store_true", help="Also pull player box scores")
    parser.add_argument("--historical", nargs=2, type=int, metavar=("START","END"),
                        help="Pull historical results e.g. --historical 2022 2024")
    parser.add_argument("--live",       action="store_true", help="Poll live scores every 2 min")
    parser.add_argument("--interval",   default=120, type=int)
    args = parser.parse_args()

    if args.historical:
        scrape_historical(args.historical[0], args.historical[1], args.out)
    elif args.live:
        live_poll(args.out, args.interval)
    else:
        target = args.date or str(date.today())
        scrape_date(target, args.out, include_boxscores=args.boxscores)
        print("\n✅ Scores scrape complete.")

if __name__ == "__main__":
    main()
