"""
props_fallback_generator.py
---------------------------
Creates fallback WNBA prop projections when sportsbook player prop markets are
unavailable because The Odds API quota is exhausted or props return empty.

This does NOT pretend these are live sportsbook lines. It uses committed player
baselines and today's game slate to create estimated lines so the Props tab and
model intelligence layers remain usable until API credits reset.

Outputs:
  - data/raw/player_points_today.csv
  - data/raw/player_points_YYYY-MM-DD.csv
  - data/raw/props_fallback_status.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from typing import List

import pandas as pd

from player_points import OUTPUT_COLUMNS, load_player_baselines, load_injuries, make_projection, safe_float

RAW_DIR = "data/raw"
PRED_DIR = "predictions"
SUPPORTED_STATS = ["pts", "reb", "ast", "threes", "pra"]
MIN_FALLBACK_ROWS = 35

# Starter/rotation fallback pool. Used only when live sportsbook props are empty.
# These are estimated model baselines, not official sportsbook lines.
TEAM_FALLBACK_PLAYERS = {
    "Minnesota Lynx": {
        "Napheesa Collier": {"pos":"F","mpg":34,"usage":0.290,"ts":0.601,"roll5_pts":20.8,"roll5_reb":8.4,"roll5_ast":3.6,"roll5_threes":0.4},
        "Kayla McBride": {"pos":"G","mpg":32,"usage":0.230,"ts":0.585,"roll5_pts":14.8,"roll5_reb":3.0,"roll5_ast":3.2,"roll5_threes":2.1},
        "Courtney Williams": {"pos":"G","mpg":31,"usage":0.220,"ts":0.540,"roll5_pts":12.6,"roll5_reb":4.8,"roll5_ast":5.4,"roll5_threes":0.8},
        "Alanna Smith": {"pos":"F","mpg":28,"usage":0.180,"ts":0.575,"roll5_pts":10.4,"roll5_reb":5.8,"roll5_ast":2.6,"roll5_threes":1.1},
        "Bridget Carleton": {"pos":"F","mpg":28,"usage":0.150,"ts":0.560,"roll5_pts":7.8,"roll5_reb":3.6,"roll5_ast":2.0,"roll5_threes":1.6},
    },
    "Connecticut Sun": {
        "Marina Mabrey": {"pos":"G","mpg":32,"usage":0.245,"ts":0.565,"roll5_pts":15.4,"roll5_reb":4.2,"roll5_ast":4.1,"roll5_threes":2.0},
        "Tina Charles": {"pos":"C","mpg":28,"usage":0.235,"ts":0.555,"roll5_pts":14.0,"roll5_reb":8.2,"roll5_ast":1.8,"roll5_threes":0.2},
        "Brionna Jones": {"pos":"F","mpg":28,"usage":0.225,"ts":0.575,"roll5_pts":13.2,"roll5_reb":5.6,"roll5_ast":2.0,"roll5_threes":0.1},
        "Saniya Rivers": {"pos":"G","mpg":26,"usage":0.180,"ts":0.520,"roll5_pts":8.6,"roll5_reb":4.0,"roll5_ast":3.6,"roll5_threes":0.7},
        "Olivia Nelson-Ododa": {"pos":"C","mpg":20,"usage":0.145,"ts":0.560,"roll5_pts":5.8,"roll5_reb":4.7,"roll5_ast":1.2,"roll5_threes":0.0},
    },
    "Golden State Valkyries": {
        "Kayla Thornton": {"pos":"F","mpg":31,"usage":0.200,"ts":0.555,"roll5_pts":12.4,"roll5_reb":6.4,"roll5_ast":2.1,"roll5_threes":1.5},
        "Tiffany Hayes": {"pos":"G","mpg":27,"usage":0.230,"ts":0.555,"roll5_pts":11.8,"roll5_reb":3.4,"roll5_ast":2.7,"roll5_threes":1.0},
        "Veronica Burton": {"pos":"G","mpg":30,"usage":0.170,"ts":0.520,"roll5_pts":8.2,"roll5_reb":3.6,"roll5_ast":4.8,"roll5_threes":0.7},
        "Janelle Salaun": {"pos":"F","mpg":24,"usage":0.165,"ts":0.525,"roll5_pts":7.4,"roll5_reb":4.6,"roll5_ast":1.5,"roll5_threes":1.1},
        "Temi Fagbenle": {"pos":"C","mpg":21,"usage":0.165,"ts":0.565,"roll5_pts":7.0,"roll5_reb":5.2,"roll5_ast":1.4,"roll5_threes":0.1},
    },
    "Washington Mystics": {
        "Brittney Sykes": {"pos":"G","mpg":31,"usage":0.260,"ts":0.545,"roll5_pts":16.0,"roll5_reb":4.0,"roll5_ast":4.4,"roll5_threes":1.2},
        "Aaliyah Edwards": {"pos":"F","mpg":28,"usage":0.190,"ts":0.550,"roll5_pts":10.6,"roll5_reb":7.2,"roll5_ast":1.6,"roll5_threes":0.1},
        "Kiki Iriafen": {"pos":"F","mpg":27,"usage":0.210,"ts":0.540,"roll5_pts":11.8,"roll5_reb":6.4,"roll5_ast":1.4,"roll5_threes":0.2},
        "Sonia Citron": {"pos":"G","mpg":29,"usage":0.185,"ts":0.555,"roll5_pts":10.8,"roll5_reb":4.2,"roll5_ast":2.5,"roll5_threes":1.4},
        "Shakira Austin": {"pos":"C","mpg":24,"usage":0.210,"ts":0.535,"roll5_pts":10.2,"roll5_reb":6.1,"roll5_ast":1.2,"roll5_threes":0.0},
    },
    "Seattle Storm": {
        "Nneka Ogwumike": {"pos":"F","mpg":32,"usage":0.250,"ts":0.590,"roll5_pts":17.0,"roll5_reb":7.2,"roll5_ast":2.5,"roll5_threes":0.6},
        "Skylar Diggins": {"pos":"G","mpg":32,"usage":0.255,"ts":0.545,"roll5_pts":14.6,"roll5_reb":2.8,"roll5_ast":6.0,"roll5_threes":1.1},
        "Gabby Williams": {"pos":"F","mpg":30,"usage":0.180,"ts":0.535,"roll5_pts":9.4,"roll5_reb":4.8,"roll5_ast":3.4,"roll5_threes":0.8},
        "Ezi Magbegor": {"pos":"C","mpg":29,"usage":0.205,"ts":0.570,"roll5_pts":12.0,"roll5_reb":7.5,"roll5_ast":1.8,"roll5_threes":0.4},
        "Erica Wheeler": {"pos":"G","mpg":22,"usage":0.190,"ts":0.520,"roll5_pts":7.8,"roll5_reb":2.2,"roll5_ast":3.0,"roll5_threes":0.7},
    },
    "Los Angeles Sparks": {
        "Kelsey Plum": {"pos":"G","mpg":34,"usage":0.285,"ts":0.575,"roll5_pts":19.2,"roll5_reb":2.8,"roll5_ast":5.0,"roll5_threes":2.3},
        "Dearica Hamby": {"pos":"F","mpg":33,"usage":0.230,"ts":0.560,"roll5_pts":16.2,"roll5_reb":9.5,"roll5_ast":3.5,"roll5_threes":0.8},
        "Rickea Jackson": {"pos":"F","mpg":30,"usage":0.235,"ts":0.555,"roll5_pts":14.8,"roll5_reb":4.2,"roll5_ast":1.7,"roll5_threes":1.2},
        "Azura Stevens": {"pos":"F","mpg":25,"usage":0.200,"ts":0.550,"roll5_pts":10.6,"roll5_reb":6.0,"roll5_ast":1.8,"roll5_threes":1.0},
        "Cameron Brink": {"pos":"C","mpg":24,"usage":0.185,"ts":0.555,"roll5_pts":9.2,"roll5_reb":6.2,"roll5_ast":1.7,"roll5_threes":0.6},
    },
}


def load_existing_player_points(target: str, raw_dir: str) -> pd.DataFrame:
    for path in [os.path.join(raw_dir, f"player_points_{target}.csv"), os.path.join(raw_dir, "player_points_today.csv")]:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                if not df.empty:
                    return df
            except Exception:
                pass
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _abbr_to_team(abbr: str) -> str:
    try:
        from daily_runner import TEAM_ABBR
        return TEAM_ABBR.get(str(abbr or "").upper(), abbr)
    except Exception:
        return abbr


def games_from_predictions(target: str) -> List[dict]:
    path = os.path.join(PRED_DIR, f"predictions_{target}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return []
    games = []
    for g in data.get("games", []) or []:
        home_obj = g.get("home", {}) if isinstance(g.get("home"), dict) else {}
        away_obj = g.get("away", {}) if isinstance(g.get("away"), dict) else {}
        home = home_obj.get("name") or _abbr_to_team(home_obj.get("abbr") or g.get("home_team") or g.get("home"))
        away = away_obj.get("name") or _abbr_to_team(away_obj.get("abbr") or g.get("away_team") or g.get("away"))
        if not home or not away:
            continue
        games.append({
            "home_team": home,
            "away_team": away,
            "game": f"{away} @ {home}",
            "game_time": g.get("tip") or g.get("commence_time") or "",
            "source": "predictions_schedule",
        })
    if games:
        print(f"  Loaded {len(games)} games for fallback props from predictions schedule")
    return games


def load_games(target: str, raw_dir: str) -> List[dict]:
    candidates = [os.path.join(raw_dir, f"odds_{target}.csv"), os.path.join(raw_dir, "odds_today.csv")]
    for path in candidates:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
            except Exception:
                continue
            games = []
            for _, row in df.iterrows():
                home = str(row.get("home_team", "") or "").strip()
                away = str(row.get("away_team", "") or "").strip()
                if not home or not away:
                    continue
                games.append({"home_team": home, "away_team": away, "game": f"{away} @ {home}", "game_time": row.get("commence_time", ""), "source": path})
            if games:
                print(f"  Loaded {len(games)} games for fallback props from {path}")
                return games

    games = games_from_predictions(target)
    if games:
        return games

    print("  [WARN] No game slate found for fallback props.")
    return []


def expand_baselines_for_games(baselines: dict, games: List[dict]) -> dict:
    expanded = dict(baselines or {})
    teams_today = set()
    for g in games:
        teams_today.add(g["home_team"])
        teams_today.add(g["away_team"])
    added = 0
    for team in teams_today:
        for player, profile in TEAM_FALLBACK_PLAYERS.get(team, {}).items():
            existing = expanded.get(player, {}) or {}
            merged = {"team": team, "source": "fallback-rotation-profile", **profile, **existing}
            if not existing:
                added += 1
            else:
                merged.setdefault("team", team)
            expanded[player] = merged
    if added:
        print(f"  Added {added} rotation fallback players for today's slate")
    return expanded


def stat_line(base: dict, stat: str) -> float:
    pts = safe_float(base.get("ppg", base.get("roll5_pts", 0)))
    reb = safe_float(base.get("reb", base.get("roll5_reb", 0)))
    ast = safe_float(base.get("ast", base.get("roll5_ast", 0)))
    threes = safe_float(base.get("roll5_threes", 0))
    if stat == "pts": val = pts
    elif stat == "reb": val = reb
    elif stat == "ast": val = ast
    elif stat == "threes": val = threes
    elif stat == "pra": val = pts + reb + ast
    else: val = 0
    if val <= 0:
        val = {"pts": 10.5, "reb": 4.5, "ast": 2.5, "threes": 1.5, "pra": 17.5}.get(stat, 5.5)
    return max(0.5, round(val * 2) / 2)


def synthetic_market_row(player: str, base: dict, game: dict, stat: str, target: str) -> dict:
    team = str(base.get("team", "") or "")
    home = game["home_team"]
    away = game["away_team"]
    opp = away if team == home else home if team == away else game["game"]
    return {
        "game_date": target,
        "event_id": f"fallback-{target}-{away[:3]}-{home[:3]}",
        "player": player,
        "team": team,
        "position": base.get("pos", ""),
        "opp_team": opp,
        "is_home": team == home,
        "stat_raw": stat,
        "stat": stat,
        "line": stat_line(base, stat),
        "over_price": -110,
        "under_price": -110,
        "yes_price": None,
        "no_price": None,
        "num_books": 0,
        "odds_type": "fallback_estimated_line",
        "game_time": game.get("game_time", ""),
        "home_team": home,
        "away_team": away,
        "source": "fallback-player-baseline",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def build_fallback(target: str, raw_dir: str) -> tuple[pd.DataFrame, dict]:
    status = {"status": "unknown", "target_date": target, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "reason": "sportsbook props unavailable or empty", "rows": 0, "games": 0, "players": 0, "source": "fallback-player-baseline", "warning": "Estimated props only. Not live sportsbook lines."}

    games = load_games(target, raw_dir)
    status["games"] = len(games)

    existing = load_existing_player_points(target, raw_dir)
    if not existing.empty and len(existing) >= MIN_FALLBACK_ROWS:
        status.update({"status": "skipped_existing_player_points", "rows": int(len(existing)), "players": int(existing["player"].nunique()) if "player" in existing.columns else 0})
        return existing, status
    if not existing.empty:
        print(f"  Existing player points only has {len(existing)} rows; rebuilding expanded fallback slate")

    baselines = expand_baselines_for_games(load_player_baselines(), games)
    injuries = load_injuries(target, raw_dir)
    if not games or not baselines:
        status["status"] = "empty_no_games_or_baselines"
        return pd.DataFrame(columns=OUTPUT_COLUMNS), status

    market_rows = []
    teams_today = set()
    for g in games:
        teams_today.add(g["home_team"])
        teams_today.add(g["away_team"])
    for player, base in baselines.items():
        team = str(base.get("team", "") or "")
        if team not in teams_today:
            continue
        game = next((g for g in games if g["home_team"] == team or g["away_team"] == team), None)
        if not game:
            continue
        for stat in SUPPORTED_STATS:
            market_rows.append(synthetic_market_row(player, base, game, stat, target))

    output_rows = []
    skipped = 0
    for row in market_rows:
        try:
            proj = make_projection(row, baselines, injuries)
            if proj:
                proj["market_status"] = "FALLBACK ESTIMATED LINE"
                proj["reasoning"] = str(proj.get("reasoning", "")) + " Fallback generated because live sportsbook props were unavailable."
                output_rows.append(proj)
            else:
                skipped += 1
        except Exception as exc:
            skipped += 1
            print(f"  [WARN] fallback prop skipped: {exc}")

    df = pd.DataFrame(output_rows, columns=OUTPUT_COLUMNS)
    if not df.empty:
        conf_order = {"HIGH": 0, "MED": 1, "LOW": 2}
        df["conf_rank"] = df["conf"].map(conf_order).fillna(9)
        df["abs_edge"] = df["edge"].abs()
        df = df.sort_values(["conf_rank", "ev", "abs_edge", "player"], ascending=[True, False, False, True]).drop(columns=["conf_rank", "abs_edge"])
    status.update({"status": "ok" if not df.empty else "empty", "rows": int(len(df)), "players": int(df["player"].nunique()) if not df.empty else 0, "skipped": skipped})
    return df, status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out", default=RAW_DIR)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print(f"\n═══ FALLBACK WNBA PROPS — {args.date} ═══\n")
    df, status = build_fallback(args.date, args.out)
    today_path = os.path.join(args.out, "player_points_today.csv")
    dated_path = os.path.join(args.out, f"player_points_{args.date}.csv")
    status_path = os.path.join(args.out, "props_fallback_status.json")
    df.to_csv(today_path, index=False)
    df.to_csv(dated_path, index=False)
    with open(status_path, "w") as f:
        json.dump(status, f, indent=2)
    print(f"  Saved → {today_path}")
    print(f"  Saved → {dated_path}")
    print(f"  Status → {status_path}")
    print(f"  Rows: {len(df)}")
    if not df.empty:
        print(df[["player", "game", "stat", "pred", "line", "edge", "signal", "conf", "market_status"]].head(25).to_string(index=False))
    print("✅ Fallback props complete.")


if __name__ == "__main__":
    main()
