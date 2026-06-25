"""
scrape_props.py — Pulls WNBA player props from PrizePicks public API.
No auth, no key. JSON returned directly.

Endpoint: https://api.prizepicks.com/projections?league_id=7&per_page=250&single_stat=true
WNBA league_id = 7

Output: data/raw/props_today.csv  |  data/raw/props_YYYY-MM-DD.csv
Usage:  python scrape_props.py
"""

import os, time, argparse
from datetime import date, datetime
import requests, pandas as pd

OUT_DIR    = "data/raw"
LEAGUE_ID  = 7   # WNBA on PrizePicks
BASE_URL   = "https://api.prizepicks.com"
PROJ_URL   = f"{BASE_URL}/projections"

HEADERS = {
    "User-Agent":    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept":        "application/json",
    "Referer":       "https://app.prizepicks.com/",
    "Origin":        "https://app.prizepicks.com",
    "Content-Type":  "application/json",
}

# PrizePicks stat_type → our model prop name
STAT_MAP = {
    "Points":                     "pts",
    "Rebounds":                   "reb",
    "Assists":                    "ast",
    "3-Point Made":               "threes",
    "3-Pointers Made":            "threes",
    "Pts+Rebs+Asts":              "pra",
    "Points+Rebounds+Assists":    "pra",
    "Pts+Asts":                   "pts_ast",
    "Pts+Rebs":                   "pts_reb",
    "Rebs+Asts":                  "reb_ast",
    "Blocked Shots":              "blk",
    "Steals":                     "stl",
    "Turnovers":                  "tov",
    "Fantasy Score":              "fantasy",
    "Minutes Played":             "min",
}

def fetch_projections(league_id=LEAGUE_ID):
    """Fetch all active props for a league from PrizePicks public API."""
    params = {
        "league_id":   league_id,
        "per_page":    250,
        "single_stat": "true",
    }
    resp = requests.get(PROJ_URL, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def parse_projections(data: dict, target_date: str) -> pd.DataFrame:
    """
    PrizePicks JSON structure:
    {
        "data": [projection objects],
        "included": [player objects, league objects]
    }
    """
    projections = data.get("data", [])
    included    = data.get("included", [])

    # Build lookup: id → player or league object
    lookup = {obj["id"]: obj for obj in included}

    rows = []
    for proj in projections:
        if proj.get("type") != "projection":
            continue

        attrs = proj.get("attributes", {})
        rels  = proj.get("relationships", {})

        # Get player details from included
        player_ref  = rels.get("new_player", rels.get("player", {})).get("data", {})
        player_id   = player_ref.get("id")
        player_obj  = lookup.get(player_id, {})
        player_attr = player_obj.get("attributes", {})

        # Game/league ref
        game_ref = rels.get("game", {}).get("data", {})
        game_obj = lookup.get(game_ref.get("id",""), {})
        game_attr = game_obj.get("attributes", {})

        stat_raw  = attrs.get("stat_type", attrs.get("stat_display",""))
        stat_norm = STAT_MAP.get(stat_raw, stat_raw.lower().replace(" ","_"))

        line = attrs.get("line_score", attrs.get("projection", None))
        if line is None:
            continue

        rows.append({
            "game_date":    target_date,
            "player":       player_attr.get("display_name", player_attr.get("name","")),
            "team":         player_attr.get("team", player_attr.get("team_name","")),
            "position":     player_attr.get("position",""),
            "opp_team":     attrs.get("description","").replace("vs","").replace("@","").strip(),
            "is_home":      "@" not in attrs.get("description",""),
            "stat_raw":     stat_raw,
            "stat":         stat_norm,
            "line":         float(line),
            "odds_type":    attrs.get("odds_type","standard"),  # standard / goblin / demon
            "game_time":    attrs.get("start_time", game_attr.get("start_time","")),
            "projection_id":proj.get("id"),
            "source":       "prizepicks",
            "scraped_at":   datetime.now().isoformat(),
        })

    return pd.DataFrame(rows)

def pivot_to_model_format(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reshape from long (one row per stat) to wide (one row per player-game)
    so it matches the format expected by props_model.py.
    """
    if df.empty:
        return df

    # Keep only props our model uses
    model_stats = {"pts","reb","ast","threes","pra"}
    df_model = df[df["stat"].isin(model_stats)].copy()

    if df_model.empty:
        return df

    pivot = df_model.pivot_table(
        index=["game_date","player","team","opp_team","is_home","game_time"],
        columns="stat",
        values="line",
        aggfunc="first"
    ).reset_index()

    # Flatten column names
    pivot.columns = [c if isinstance(c, str) else c for c in pivot.columns]

    # Rename to posted_ prefix (matches daily_runner.py expectations)
    for stat in model_stats:
        if stat in pivot.columns:
            pivot.rename(columns={stat: f"posted_{stat}"}, inplace=True)

    return pivot

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",  default=None)
    parser.add_argument("--out",   default="data/raw")
    parser.add_argument("--league-id", default=LEAGUE_ID, type=int,
                        help="PrizePicks league ID (7=WNBA)")
    args = parser.parse_args()

    target = args.date or str(date.today())
    os.makedirs(args.out, exist_ok=True)

    print(f"Fetching PrizePicks WNBA props — {target}")
    data = fetch_projections(args.league_id)

    total_included = len(data.get("included", []))
    total_projs    = len(data.get("data", []))
    print(f"  Raw response: {total_projs} projections, {total_included} included objects")

    df = parse_projections(data, target)

    if df.empty:
        print("  [WARN] No props parsed. Check league_id or PrizePicks availability.")
        return

    print(f"  Parsed {len(df)} props for {df['player'].nunique()} players")
    print(f"  Stat types: {sorted(df['stat'].unique())}")

    # Save raw long format
    raw_path   = os.path.join(args.out, f"props_raw_{target}.csv")
    today_path = os.path.join(args.out, "props_today.csv")
    df.to_csv(raw_path,   index=False)
    df.to_csv(today_path, index=False)

    # Save wide/pivoted format for model
    pivot_df  = pivot_to_model_format(df)
    wide_path = os.path.join(args.out, f"props_wide_{target}.csv")
    pivot_df.to_csv(wide_path, index=False)

    # Append to historical
    hist_path = os.path.join(args.out, "props_historical.csv")
    if os.path.exists(hist_path):
        hist = pd.read_csv(hist_path)
        hist = hist[hist["game_date"] != target]
        pd.concat([hist, df], ignore_index=True).to_csv(hist_path, index=False)
    else:
        df.to_csv(hist_path, index=False)

    print(f"\n  Today's props (sample):")
    sample = df[df["stat"].isin({"pts","reb","ast","pra"})].sort_values("player")
    print(sample[["player","team","opp_team","stat","line","odds_type"]].head(15).to_string(index=False))

    print(f"\n  Saved → {today_path}")
    print(f"  Saved → {raw_path}")
    print(f"  Saved → {wide_path}  (model-ready pivot)")
    print(f"  Appended → {hist_path}")
    print("\n✅ Props scrape complete.")

if __name__ == "__main__":
    main()
