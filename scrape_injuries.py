"""
scrape_injuries.py
------------------
Scrapes WNBA injury reports and reallocates projected minutes
to bench players when starters are out.

Sources:
  1. ESPN injuries API  — official injury designations
  2. Rotowire WNBA      — detailed injury notes (backup)

Output:
  data/raw/injuries_today.csv     — current injury report
  data/raw/minute_projections.csv — adjusted minutes per player per game

Usage:
    python scrape_injuries.py
    python scrape_injuries.py --date 2026-07-04
"""

import os, json, time, argparse, requests
import pandas as pd
from datetime import date, datetime

OUT_DIR   = "data/raw"
HEADERS   = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"

# Typical minutes by position when starter sits
# Based on WNBA rotation patterns
BENCH_FILL_PCT = {
    "G": 0.75,   # Guards — bench gets ~75% of starter minutes
    "F": 0.70,
    "C": 0.65,
    "": 0.70,
}

# ── ESPN injuries ─────────────────────────────────────────────────────────────

TEAM_IDS = {
    "Atlanta Dream":          28,
    "Chicago Sky":            29,
    "Connecticut Sun":        30,
    "Dallas Wings":           27,
    "Golden State Valkyries": 132052,
    "Indiana Fever":          32,
    "Las Vegas Aces":         33,
    "Los Angeles Sparks":     34,
    "Minnesota Lynx":         35,
    "New York Liberty":       36,
    "Phoenix Mercury":        37,
    "Portland Fire":          132051,
    "Seattle Storm":          38,
    "Toronto Tempo":          132053,
    "Washington Mystics":     39,
}

STATUS_SEVERITY = {
    "Out":           "OUT",
    "Doubtful":      "DOUBTFUL",
    "Questionable":  "QUESTIONABLE",
    "Probable":      "PROBABLE",
    "Day-To-Day":    "QUESTIONABLE",
    "IR":            "OUT",
    "Suspended":     "OUT",
}

def fetch_espn_injuries(team_name: str, team_id: int) -> list:
    """Fetch injury report for one team from ESPN."""
    url  = f"{ESPN_BASE}/teams/{team_id}/injuries"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return []

    injuries = []
    for item in data.get("injuries", []):
        athlete = item.get("athlete", {})
        status  = item.get("status","")
        inj_type= item.get("type","")
        detail  = item.get("details", {})

        severity = STATUS_SEVERITY.get(status, "UNKNOWN")
        if severity == "UNKNOWN":
            continue

        pos = athlete.get("position", {}).get("abbreviation", "")
        injuries.append({
            "team":        team_name,
            "player":      athlete.get("displayName",""),
            "player_id":   athlete.get("id",""),
            "position":    pos,
            "status":      status,
            "severity":    severity,
            "injury_type": inj_type,
            "detail":      detail.get("detail",""),
            "return_date": detail.get("returnDate",""),
            "is_out":      severity in ("OUT","DOUBTFUL"),
            "scraped_at":  datetime.now().isoformat(),
        })

    return injuries


def fetch_all_injuries(out_dir: str, target_date: str) -> pd.DataFrame:
    """Pull injury reports for all 15 WNBA teams."""
    print(f"Fetching injury reports for {target_date}...")
    all_injuries = []

    for team, tid in TEAM_IDS.items():
        injuries = fetch_espn_injuries(team, tid)
        all_injuries.extend(injuries)
        if injuries:
            out_names = [i["player"] for i in injuries if i["is_out"]]
            q_names   = [i["player"] for i in injuries if not i["is_out"]]
            if out_names:
                print(f"  {team}: OUT — {', '.join(out_names)}")
            if q_names:
                print(f"  {team}: Q   — {', '.join(q_names)}")
        time.sleep(0.3)

    df = pd.DataFrame(all_injuries)
    if not df.empty:
        df["game_date"] = target_date
        path = os.path.join(out_dir, "injuries_today.csv")
        df.to_csv(path, index=False)
        hist_path = os.path.join(out_dir, "injuries_historical.csv")
        if os.path.exists(hist_path):
            hist = pd.read_csv(hist_path)
            hist = hist[hist["game_date"] != target_date]
            pd.concat([hist, df], ignore_index=True).to_csv(hist_path, index=False)
        else:
            df.to_csv(hist_path, index=False)
        print(f"\n  {len(df)} injury designations saved → {path}")
    else:
        print("  No injuries found (all teams healthy or data unavailable)")

    return df


# ── Minute reallocation ───────────────────────────────────────────────────────

# Default starter minute profiles (updated from wehoop player box data)
DEFAULT_MINUTES = {
    "A'ja Wilson":         32, "Kelsey Plum":        30, "Jackie Young":       31,
    "Chelsea Gray":        28, "Breanna Stewart":    33, "Sabrina Ionescu":    34,
    "Jonquel Jones":       29, "Napheesa Collier":   34, "Courtney Williams":  27,
    "Alyssa Thomas":       34, "DeWanna Bonner":     28, "Caitlin Clark":      35,
    "Aliyah Boston":       28, "Nneka Ogwumike":     29, "Skylar Diggins":     31,
    "Angel Reese":         30, "Marina Mabrey":      28, "Arike Ogunbowale":   33,
    "Rhyne Howard":        32, "Elena Delle Donne":  29, "Dearica Hamby":      30,
}

# Bench players who absorb minutes (team → list of bench players with avg min)
BENCH_DEPTH = {
    "Las Vegas Aces":         [("Kate Martin",    22), ("Tiffany Hayes",   18)],
    "New York Liberty":       [("Leonie Fiebich", 22), ("Betnijah Laney",  20)],
    "Minnesota Lynx":         [("Olivia Miles",   24), ("Natasha Howard",  20)],
    "Connecticut Sun":        [("Marina Mabrey",  20), ("Brionna Jones",   18)],
    "Indiana Fever":          [("NaLyssa Smith",  22), ("Kelsey Mitchell", 20)],
    "Seattle Storm":          [("Jewell Loyd",    28), ("Victoria Vivians",18)],
    "Atlanta Dream":          [("Allisha Gray",   25), ("Tina Charles",    22)],
    "Dallas Wings":           [("Natasha Howard", 22), ("Odyssey Sims",    18)],
    "Chicago Sky":            [("Chennedy Carter",24), ("Isabelle Harrison",20)],
    "Phoenix Mercury":        [("Sophie Cunningham",22),("Diana Taurasi",  24)],
    "Golden State Valkyries": [("Kayla Thornton", 22), ("Rebecca Harris",  18)],
    "Washington Mystics":     [("Ariel Atkins",   24), ("Julie Allemand",  20)],
    "Los Angeles Sparks":     [("Lexie Brown",    22), ("Azura Stevens",   20)],
    "Toronto Tempo":          [("Kayla McBride",  26), ("Sonia Citron",    20)],
    "Portland Fire":          [("Gabby Williams", 24), ("Satou Sabally",   22)],
}


def reallocate_minutes(injuries_df: pd.DataFrame, games: list) -> dict:
    """
    For each game, compute adjusted minute projections accounting for injuries.

    Returns dict: {player_name: adjusted_minutes}
    """
    if injuries_df.empty:
        return {}

    # Players definitely out
    out_players = set(
        injuries_df[injuries_df["is_out"]]["player"].tolist()
    )
    # Players questionable (50% minute reduction)
    q_players = set(
        injuries_df[~injuries_df["is_out"]]["player"].tolist()
    )

    adjustments = {}

    # Get teams playing today
    teams_playing = set()
    for g in games:
        teams_playing.add(g.get("home",""))
        teams_playing.add(g.get("away",""))

    for team in teams_playing:
        bench = BENCH_DEPTH.get(team, [])
        total_missing_min = 0

        # Find starters who are out for this team
        team_out = injuries_df[
            (injuries_df["team"] == team) & injuries_df["is_out"]
        ]["player"].tolist()

        team_q = injuries_df[
            (injuries_df["team"] == team) & ~injuries_df["is_out"]
        ]["player"].tolist()

        for player in team_out:
            missing = DEFAULT_MINUTES.get(player, 25)
            total_missing_min += missing
            adjustments[player] = 0  # Out — zero minutes
            print(f"  {player} ({team}): OUT — 0 min (was ~{missing})")

        for player in team_q:
            orig = DEFAULT_MINUTES.get(player, 25)
            adj  = orig * 0.6  # Questionable: 60% of normal
            adjustments[player] = adj
            print(f"  {player} ({team}): QUESTIONABLE — {adj:.0f} min (was ~{orig})")

        # Distribute missing minutes to bench
        if total_missing_min > 0 and bench:
            per_bench = total_missing_min / len(bench)
            for bench_player, base_min in bench:
                pos = ""
                fill_pct = BENCH_FILL_PCT.get(pos, 0.70)
                extra = per_bench * fill_pct
                new_min = base_min + extra
                new_min = min(new_min, 36)  # Cap at 36 min
                adjustments[bench_player] = new_min
                print(f"  {bench_player} ({team}): PROMOTED — {new_min:.0f} min (+{extra:.0f})")

    return adjustments


def save_projections(adjustments: dict, games: list, out_dir: str, target_date: str):
    """Save minute projections to CSV."""
    rows = []
    for player, minutes in adjustments.items():
        rows.append({
            "game_date":  target_date,
            "player":     player,
            "proj_min":   round(minutes, 1),
            "adjusted":   True,
        })
    if rows:
        df = pd.DataFrame(rows)
        path = os.path.join(out_dir, "minute_projections.csv")
        df.to_csv(path, index=False)
        print(f"\n  Minute projections → {path} ({len(df)} players adjusted)")
        return df
    return pd.DataFrame()


# ── Impact on props model ─────────────────────────────────────────────────────

def apply_injury_adjustments(player_games: list, adjustments: dict) -> list:
    """
    Apply minute adjustments to player game inputs before props prediction.
    Call this in daily_runner.py before running props model.
    """
    adjusted = []
    for pg in player_games:
        player = pg.get("player","")
        if player in adjustments:
            new_min = adjustments[player]
            orig_min = pg.get("proj_minutes", pg.get("mpg", 28))
            if new_min == 0:
                pg["proj_minutes"]  = 0
                pg["is_out"]        = True
            else:
                scale = new_min / max(orig_min, 1)
                pg["proj_minutes"]  = new_min
                pg["roll5_pts"]     = pg.get("roll5_pts", 15) * scale
                pg["roll5_reb"]     = pg.get("roll5_reb", 5)  * scale
                pg["roll5_ast"]     = pg.get("roll5_ast", 3)  * scale
                pg["roll5_threes"]  = pg.get("roll5_threes",1)* scale
                pg["roll5_pra"]     = pg.get("roll5_pra", 23) * scale
        adjusted.append(pg)
    return adjusted


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",    default=str(date.today()))
    parser.add_argument("--out",     default="data/raw")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    print(f"\n═══ Injury Report + Minute Projections — {args.date} ═══\n")

    injuries_df = fetch_all_injuries(args.out, args.date)

    # Example games (in production comes from daily_runner)
    games = []
    adjustments = reallocate_minutes(injuries_df, games)
    save_projections(adjustments, games, args.out, args.date)

    out_count = len(injuries_df[injuries_df["is_out"]]) if not injuries_df.empty else 0
    q_count   = len(injuries_df[~injuries_df["is_out"]]) if not injuries_df.empty else 0
    print(f"\n  Summary: {out_count} OUT, {q_count} Questionable")
    print("✅ Injury scrape complete.")


if __name__ == "__main__":
    main()
