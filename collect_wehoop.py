"""
collect_wehoop.py
-----------------
Pulls WNBA data from two sources:
  1. Sportsdataverse pre-built .rds releases  (2003–2024, historical)
  2. ESPN public API                           (current season, live)

Replaces Basketball-Reference scraper. No R needed — pyreadr reads .rds in Python.

Data collected:
  - Team box scores per game (pts, reb, ast, to, fg_pct, fg3_pct, ft_pct)
  - Player box scores per game (for props model)
  - Season schedules (rest days, home/away)

Usage:
    python collect_wehoop.py --start 2022 --end 2024   # historical
    python collect_wehoop.py --current                  # today's season
    python collect_wehoop.py --start 2022 --current     # both
"""

import os, time, argparse, requests, json
import pandas as pd
from datetime import date, datetime

OUT_DIR  = "data/raw"
HEADERS  = {"User-Agent": "Mozilla/5.0 (research project)"}

# ── URL patterns ───────────────────────────────────────────────────────────────
SDV_BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"

SDV_URLS = {
    "team_box":    f"{SDV_BASE}/espn_wnba_team_boxscores/team_box_{{year}}.rds",
    "player_box":  f"{SDV_BASE}/espn_wnba_player_boxscores/player_box_{{year}}.rds",
    "schedule":    f"{SDV_BASE}/espn_wnba_schedules/wnba_schedule_{{year}}.rds",
}

# Columns we care about from team box
TEAM_BOX_COLS = [
    "game_id","season","game_date","game_date_time",
    "team_id","team_name","team_location","team_abbreviation",
    "home_away",
    "field_goals_made","field_goals_attempted","field_goal_pct",
    "three_point_field_goals_made","three_point_field_goals_attempted","three_point_field_goal_pct",
    "free_throws_made","free_throws_attempted","free_throw_pct",
    "offensive_rebounds","defensive_rebounds","rebounds",
    "assists","steals","blocks","turnovers","fouls",
    "points",
    "largest_lead","team_turnovers","total_technical_fouls",
]

PLAYER_BOX_COLS = [
    "game_id","season","game_date","team_name","team_location","team_abbreviation",
    "athlete_id","athlete_display_name","athlete_position_abbreviation",
    "home_away","starter","did_not_play",
    "minutes","field_goals_made","field_goals_attempted","three_point_field_goals_made",
    "three_point_field_goals_attempted","free_throws_made","free_throws_attempted",
    "offensive_rebounds","defensive_rebounds","rebounds",
    "assists","steals","blocks","turnovers","fouls","points","plus_minus",
]


# ── RDS reader ────────────────────────────────────────────────────────────────

def read_rds_url(url: str) -> pd.DataFrame:
    """Download and parse an .rds file into a DataFrame using pyreadr."""
    try:
        import pyreadr
    except ImportError:
        raise ImportError("Install pyreadr: pip install pyreadr --break-system-packages")

    import tempfile
    resp = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
    if resp.status_code == 404:
        return pd.DataFrame()
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".rds", delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = tmp.name

    try:
        result = pyreadr.read_r(tmp_path)
        df = list(result.values())[0]
    finally:
        os.unlink(tmp_path)

    return df


# ── Historical data (SDV releases) ───────────────────────────────────────────

def fetch_historical_season(year: int, out_dir: str):
    print(f"\n── Season {year} (Sportsdataverse) ──")

    # Team box scores
    url = SDV_URLS["team_box"].format(year=year)
    print(f"  Downloading team box scores...", end="", flush=True)
    df = read_rds_url(url)
    if df.empty:
        print(f" [404 — not available]")
    else:
        cols = [c for c in TEAM_BOX_COLS if c in df.columns]
        df   = df[cols].copy()
        # Compute derived stats
        if "points" in df.columns:
            df["pts"] = pd.to_numeric(df["points"], errors="coerce")
        path = os.path.join(out_dir, f"wehoop_team_box_{year}.csv")
        df.to_csv(path, index=False)
        print(f" {len(df)} rows → {path}")

    time.sleep(2)

    # Player box scores
    url = SDV_URLS["player_box"].format(year=year)
    print(f"  Downloading player box scores...", end="", flush=True)
    df = read_rds_url(url)
    if df.empty:
        print(f" [404 — not available]")
    else:
        cols = [c for c in PLAYER_BOX_COLS if c in df.columns]
        df   = df[cols].copy()
        path = os.path.join(out_dir, f"wehoop_player_box_{year}.csv")
        df.to_csv(path, index=False)
        print(f" {len(df)} rows → {path}")

    time.sleep(2)

    # Schedule
    url = SDV_URLS["schedule"].format(year=year)
    print(f"  Downloading schedule...", end="", flush=True)
    df = read_rds_url(url)
    if df.empty:
        print(f" [404 — not available]")
    else:
        path = os.path.join(out_dir, f"wehoop_schedule_{year}.csv")
        df.to_csv(path, index=False)
        print(f" {len(df)} rows → {path}")

    time.sleep(2)


# ── Current season (ESPN API, game by game) ───────────────────────────────────

def fetch_espn_scoreboard(target_date: str) -> list:
    """Get all games for a date from ESPN."""
    url    = f"{ESPN_BASE}/scoreboard"
    params = {"dates": target_date.replace("-",""), "limit": 50}
    resp   = requests.get(url, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("events", [])


def fetch_espn_boxscore(game_id: str) -> dict:
    """Get full box score for a single game from ESPN."""
    url    = f"{ESPN_BASE}/summary"
    params = {"event": game_id}
    resp   = requests.get(url, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_espn_team_box(summary: dict, game_date: str, season: int) -> list:
    """Extract team-level stats from ESPN game summary."""
    rows = []
    comps = summary.get("header",{}).get("competitions",[{}])[0]
    game_id = comps.get("id","")

    for team_data in summary.get("boxscore",{}).get("teams",[]):
        team    = team_data.get("team",{})
        stats   = {s["name"]: s["displayValue"]
                   for s in team_data.get("statistics",[])}
        home_away = team_data.get("homeAway","")

        def g(key):
            val = stats.get(key,"")
            try: return float(val.replace("%",""))
            except: return None

        rows.append({
            "game_id":          game_id,
            "season":           season,
            "game_date":        game_date,
            "team_name":        team.get("name",""),
            "team_location":    team.get("location",""),
            "team_abbreviation":team.get("abbreviation",""),
            "home_away":        home_away,
            "pts":              g("points"),
            "field_goal_pct":   g("fieldGoalPct"),
            "three_point_pct":  g("threePointPct"),
            "free_throw_pct":   g("freeThrowPct"),
            "rebounds":         g("totalRebounds"),
            "assists":          g("assists"),
            "steals":           g("steals"),
            "blocks":           g("blocks"),
            "turnovers":        g("turnovers"),
            "fouls":            g("fouls"),
            "offensive_rebounds": g("offensiveRebounds"),
            "source":           "espn_api",
        })
    return rows


def parse_espn_player_box(summary: dict, game_date: str, season: int) -> list:
    """Extract player-level stats from ESPN game summary."""
    rows = []
    game_id = summary.get("header",{}).get("competitions",[{}])[0].get("id","")

    for team_data in summary.get("boxscore",{}).get("players",[]):
        team    = team_data.get("team",{})
        home_away = team_data.get("homeAway","")

        for stat_group in team_data.get("statistics",[]):
            labels = stat_group.get("labels",[])
            for athlete in stat_group.get("athletes",[]):
                pl      = athlete.get("athlete",{})
                vals    = athlete.get("stats",[])
                sd      = dict(zip(labels, vals))

                def gv(key, default=None):
                    try: return float(sd.get(key,"")) if sd.get(key,"") not in ("--","") else default
                    except: return default

                rows.append({
                    "game_id":      game_id,
                    "season":       season,
                    "game_date":    game_date,
                    "team_name":    team.get("name",""),
                    "team_abbr":    team.get("abbreviation",""),
                    "home_away":    home_away,
                    "player_id":    pl.get("id",""),
                    "player_name":  pl.get("displayName",""),
                    "position":     pl.get("position",{}).get("abbreviation",""),
                    "starter":      athlete.get("starter", False),
                    "did_not_play": athlete.get("didNotPlay", False),
                    "minutes":      gv("MIN"),
                    "pts":          gv("PTS"),
                    "reb":          gv("REB"),
                    "ast":          gv("AST"),
                    "stl":          gv("STL"),
                    "blk":          gv("BLK"),
                    "tov":          gv("TO"),
                    "fg_made":      gv("FGM"),
                    "fg_att":       gv("FGA"),
                    "threes_made":  gv("3PM"),
                    "threes_att":   gv("3PA"),
                    "ft_made":      gv("FTM"),
                    "ft_att":       gv("FTA"),
                    "plus_minus":   gv("+/-"),
                    "source":       "espn_api",
                })
    return rows


def fetch_current_season(season_year: int, out_dir: str):
    """
    Pull full current season box scores from ESPN API.
    Goes month by month through the WNBA season (May–Oct).
    """
    print(f"\n── Season {season_year} (ESPN API — current) ──")
    today = date.today()

    team_rows, player_rows = [], []
    seen_games = set()

    # WNBA season: May 14 through Sept 22
    from datetime import timedelta
    start = date(season_year, 5, 14)
    end   = min(date(season_year, 9, 22), today)

    current = start
    while current <= end:
        date_str = str(current)
        try:
            events = fetch_espn_scoreboard(date_str)
            for event in events:
                gid    = event.get("id","")
                status = event.get("status",{}).get("type",{}).get("name","")
                if "FINAL" not in status.upper() and current < today:
                    current += timedelta(days=1)
                    continue
                if gid in seen_games:
                    current += timedelta(days=1)
                    continue
                seen_games.add(gid)

                try:
                    summary = fetch_espn_boxscore(gid)
                    team_rows   += parse_espn_team_box(summary, date_str, season_year)
                    player_rows += parse_espn_player_box(summary, date_str, season_year)
                    time.sleep(0.5)
                except Exception as e:
                    print(f"    [WARN] Game {gid}: {e}")
        except Exception as e:
            print(f"  [WARN] {date_str}: {e}")

        current += timedelta(days=1)
        if current.day == 1:
            print(f"  Through {date_str}: {len(seen_games)} games")
        time.sleep(0.3)

    print(f"  Total: {len(seen_games)} games")

    if team_rows:
        df = pd.DataFrame(team_rows)
        path = os.path.join(out_dir, f"wehoop_team_box_{season_year}.csv")
        df.to_csv(path, index=False)
        print(f"  Team box → {path} ({len(df)} rows)")

    if player_rows:
        df = pd.DataFrame(player_rows)
        path = os.path.join(out_dir, f"wehoop_player_box_{season_year}.csv")
        df.to_csv(path, index=False)
        print(f"  Player box → {path} ({len(df)} rows)")


# ── Build master dataset from wehoop files ────────────────────────────────────

def build_wehoop_master(out_dir: str):
    """
    Combine all wehoop_team_box_*.csv files into a single master
    that merge_data.py can read alongside scores and odds.
    """
    files = sorted([f for f in os.listdir(out_dir) if f.startswith("wehoop_team_box_")])
    if not files:
        print("  No wehoop team box files found.")
        return

    dfs = []
    for f in files:
        df = pd.read_csv(os.path.join(out_dir, f))
        dfs.append(df)
        print(f"  Loaded {f}: {len(df)} rows")

    master = pd.concat(dfs, ignore_index=True)

    # Pivot to one row per game (home + away side by side)
    if "home_away" in master.columns:
        home = master[master["home_away"]=="home"].copy()
        away = master[master["home_away"]=="away"].copy()

        home_rename = {c: f"home_{c}" for c in home.columns if c not in ["game_id","season","game_date"]}
        away_rename = {c: f"away_{c}" for c in away.columns if c not in ["game_id","season","game_date"]}

        home = home.rename(columns=home_rename)
        away = away.rename(columns=away_rename)

        game_df = home.merge(away, on=["game_id","season","game_date"], how="inner")

        # Compute actual spread and total
        if "home_pts" in game_df.columns and "away_pts" in game_df.columns:
            game_df["home_pts"]     = pd.to_numeric(game_df["home_pts"], errors="coerce")
            game_df["away_pts"]     = pd.to_numeric(game_df["away_pts"], errors="coerce")
            game_df["actual_spread"]= game_df["home_pts"] - game_df["away_pts"]
            game_df["actual_total"] = game_df["home_pts"] + game_df["away_pts"]

        path = os.path.join(out_dir, "wehoop_games_master.csv")
        game_df.to_csv(path, index=False)
        print(f"\n  Master game file → {path} ({len(game_df)} games)")
    else:
        master.to_csv(os.path.join(out_dir, "wehoop_master.csv"), index=False)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Collect WNBA data via wehoop/ESPN")
    parser.add_argument("--start",   type=int, default=None, help="First historical year")
    parser.add_argument("--end",     type=int, default=2024,  help="Last historical year")
    parser.add_argument("--current", action="store_true",    help="Also pull current season from ESPN")
    parser.add_argument("--out",     default="data/raw")
    parser.add_argument("--master",  action="store_true",    help="Build master game CSV after download")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    print("\n═══ WNBA Data Collection — wehoop + ESPN ═══\n")

    # Historical via SDV
    if args.start:
        try:
            import pyreadr
        except ImportError:
            print("[INFO] Installing pyreadr for .rds file support...")
            os.system("pip install pyreadr --break-system-packages -q")
            import pyreadr

        for year in range(args.start, args.end + 1):
            try:
                fetch_historical_season(year, args.out)
            except Exception as e:
                print(f"  [ERROR] Season {year}: {e}")
                continue

    # Current season via ESPN
    if args.current:
        current_year = date.today().year
        fetch_current_season(current_year, args.out)

    # Build master
    if args.master or args.start or args.current:
        print("\nBuilding master game dataset...")
        build_wehoop_master(args.out)

    print("\n✅ wehoop collection complete.")


if __name__ == "__main__":
    main()
