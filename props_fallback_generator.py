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
from typing import Dict, List

import pandas as pd

from player_points import OUTPUT_COLUMNS, load_player_baselines, load_injuries, make_projection, safe_float

RAW_DIR = "data/raw"
SUPPORTED_STATS = ["pts", "reb", "ast", "threes", "pra"]


def load_existing_player_points(target: str, raw_dir: str) -> pd.DataFrame:
    for path in [os.path.join(raw_dir, f"player_points_{target}.csv"), os.path.join(raw_dir, "player_points_today.csv")]:
        if os.path.exists(path):
            try:
                return pd.read_csv(path)
            except Exception:
                return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


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
                games.append({
                    "home_team": home,
                    "away_team": away,
                    "game": f"{away} @ {home}",
                    "game_time": row.get("commence_time", ""),
                })
            if games:
                print(f"  Loaded {len(games)} games for fallback props from {path}")
                return games
    print("  [WARN] No game slate found for fallback props.")
    return []


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
    # Make it look like a common prop line ending in .5.
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
    status = {
        "status": "unknown",
        "target_date": target,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": "sportsbook props unavailable or empty",
        "rows": 0,
        "games": 0,
        "players": 0,
        "source": "fallback-player-baseline",
        "warning": "Estimated props only. Not live sportsbook lines.",
    }
    existing = load_existing_player_points(target, raw_dir)
    if not existing.empty:
        status.update({"status": "skipped_existing_player_points", "rows": int(len(existing))})
        return existing, status

    games = load_games(target, raw_dir)
    baselines = load_player_baselines()
    injuries = load_injuries(target, raw_dir)
    status["games"] = len(games)
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
