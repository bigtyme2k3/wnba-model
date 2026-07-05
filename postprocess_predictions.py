"""
postprocess_predictions.py
--------------------------
Patches today's predictions JSON after daily_runner.py by:
  - merging The Odds API CSV lines into each game
  - recomputing spread/total edges and confidence
  - embedding player_points_YYYY-MM-DD.csv into the predictions JSON
  - rebuilding best_bets as actionable MED/HIGH plays only
  - adding a spread board and props board
  - adding data_health metadata for the dashboard
"""

import argparse
import glob
import json
import os
from datetime import datetime, timezone

import pandas as pd

PREDICTIONS_DIR = "predictions"
RAW_DIR = "data/raw"

CONF_THRESHOLDS = {
    "spread": {"HIGH": 5.0, "MED": 3.0},
    "totals": {"HIGH": 4.0, "MED": 2.0},
    "props": {"HIGH": 3.0, "MED": 1.5},
}

ALIASES = {
    "golden state valkyries": "golden state valkyries",
    "gs valkyries": "golden state valkyries",
    "gsv": "golden state valkyries",
    "portland fire": "portland fire",
    "pdx fire": "portland fire",
    "toronto tempo": "toronto tempo",
}


def norm_team(name):
    name = str(name or "").strip().lower().replace("  ", " ")
    return ALIASES.get(name, name)


def to_float(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def clean_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def score_confidence(edge, model_type):
    thresholds = CONF_THRESHOLDS.get(model_type, {"HIGH": 5.0, "MED": 3.0})
    ae = abs(edge) if edge is not None else 0.0
    if ae >= thresholds["HIGH"]:
        return "HIGH", 3
    if ae >= thresholds["MED"]:
        return "MED", 2
    return "LOW", 1


def fmt_spread_line(team, line):
    if line is None:
        return team
    if abs(line) < 0.05:
        return f"{team} PK"
    sign = "+" if line > 0 else ""
    return f"{team} {sign}{line:.1f}"


def prediction_path(target_date):
    exact = os.path.join(PREDICTIONS_DIR, f"predictions_{target_date}.json")
    if os.path.exists(exact):
        return exact
    files = sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")))
    if not files:
        raise FileNotFoundError("No predictions JSON found")
    return files[-1]


def load_csv(candidates, label):
    for path in candidates:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                print(f"  Loaded {label}: {path} ({len(df)} rows)")
                return df
            except Exception as exc:
                print(f"  [WARN] Could not read {path}: {exc}")
    print(f"  [WARN] No {label} CSV found")
    return pd.DataFrame()


def load_odds(target_date):
    return load_csv([
        os.path.join(RAW_DIR, f"odds_{target_date}.csv"),
        os.path.join(RAW_DIR, "odds_today.csv"),
    ], "odds")


def load_props(target_date):
    return load_csv([
        os.path.join(RAW_DIR, f"props_raw_{target_date}.csv"),
        os.path.join(RAW_DIR, "props_today.csv"),
    ], "props")


def load_player_points(target_date):
    return load_csv([
        os.path.join(RAW_DIR, f"player_points_{target_date}.csv"),
        os.path.join(RAW_DIR, "player_points_today.csv"),
    ], "player points")


def find_odds_row(odds_df, home, away):
    if odds_df.empty:
        return None
    h = norm_team(home)
    a = norm_team(away)
    for _, row in odds_df.iterrows():
        rh = norm_team(row.get("home_team"))
        ra = norm_team(row.get("away_team"))
        if rh == h and ra == a:
            return row
    return None


def build_spread_board(games):
    board = []
    for game in games:
        sp = game.get("spread", {})
        if sp.get("posted_line") is None:
            status = "WAIT"
        elif (sp.get("stars") or 1) >= 2:
            status = "BET"
        else:
            status = "WATCH"
        board.append({
            "game": f"{game['away']['name']} @ {game['home']['name']}",
            "tip": game.get("tip"),
            "market_line": sp.get("posted_line"),
            "model_line": sp.get("model_line"),
            "play": sp.get("play") or sp.get("model_line"),
            "edge": sp.get("edge_abs"),
            "conf": sp.get("conf", "LOW"),
            "stars": sp.get("stars", 1),
            "status": status,
            "books": game.get("market", {}).get("books", 0),
        })
    board.sort(key=lambda x: (x.get("status") != "BET", -(x.get("edge") or 0)))
    return board


def build_player_points_board(points_df):
    if points_df.empty:
        return []
    board = []
    for _, row in points_df.iterrows():
        edge = to_float(row.get("edge"))
        conf = str(clean_value(row.get("conf")) or "LOW").upper()
        signal = clean_value(row.get("signal"))
        if signal is not None:
            signal = str(signal).upper()
        conf_calc, stars = score_confidence(edge, "props")
        if conf not in {"HIGH", "MED", "LOW"}:
            conf = conf_calc
        board.append({
            "player": clean_value(row.get("player")) or "",
            "team": clean_value(row.get("team")) or "",
            "opp": clean_value(row.get("opp")) or "",
            "pos": clean_value(row.get("pos")) or "",
            "season_avg": to_float(row.get("season_avg")),
            "projection": to_float(row.get("pred")),
            "pred": to_float(row.get("pred")),
            "low": to_float(row.get("low")),
            "high": to_float(row.get("high")),
            "range": clean_value(row.get("range")) or "",
            "line": to_float(row.get("line")),
            "edge": edge,
            "signal": signal,
            "conf": conf,
            "stars": {"HIGH": 3, "MED": 2, "LOW": 1}.get(conf, stars),
            "reasoning": clean_value(row.get("reasoning")) or "",
            "game": clean_value(row.get("game")) or "",
        })
    board.sort(key=lambda x: (-abs(x.get("edge") or 0), x.get("player", "")))
    return board


def build_props_board(props_df, games, player_points=None):
    if player_points:
        return player_points
    if props_df.empty:
        return []

    game_team_names = set()
    for g in games:
        game_team_names.add(norm_team(g.get("home", {}).get("name")))
        game_team_names.add(norm_team(g.get("away", {}).get("name")))

    keep_stats = {"pts", "reb", "ast", "threes", "pra"}
    df = props_df.copy()
    if "stat" in df.columns:
        df = df[df["stat"].isin(keep_stats)]
    if "team" in df.columns and game_team_names:
        df = df[df["team"].apply(lambda x: norm_team(x) in game_team_names if pd.notna(x) else False)]

    if df.empty:
        return []

    stat_order = {"pts": 1, "pra": 2, "reb": 3, "ast": 4, "threes": 5}
    board = []
    for _, row in df.sort_values(by=["player", "stat"]).iterrows():
        stat = str(row.get("stat", "")).lower()
        line = to_float(row.get("line"))
        board.append({
            "player": row.get("player", ""),
            "team": row.get("team", ""),
            "opp": row.get("opp_team", ""),
            "stat": stat.upper() if stat != "threes" else "3PM",
            "line": line,
            "odds_type": row.get("odds_type", "standard"),
            "game_time": row.get("game_time", ""),
            "source": row.get("source", "prizepicks"),
            "status": "MARKET",
            "rank_key": stat_order.get(stat, 99),
        })

    board.sort(key=lambda x: (x.get("player", ""), x.get("rank_key", 99)))
    for item in board:
        item.pop("rank_key", None)
    return board[:80]


def rebuild_best_bets(games):
    bets = []
    for game in games:
        home = game["home"]["name"]
        away = game["away"]["name"]
        matchup = f"{away} @ {home}"
        tip = game.get("tip")

        spread = game.get("spread", {})
        if spread.get("edge") is not None and (spread.get("stars") or 1) >= 2:
            bets.append({
                "type": "SPREAD",
                "game": matchup,
                "play": spread.get("play") or spread.get("model_line"),
                "edge": spread.get("edge_abs", abs(spread.get("edge", 0))),
                "edge_abs": spread.get("edge_abs", abs(spread.get("edge", 0))),
                "conf": spread.get("conf", "LOW"),
                "stars": spread.get("stars", 1),
                "tip": tip,
                "market_line": spread.get("posted_line"),
                "model_line": spread.get("model_line"),
                "verdict": "BET",
            })

        totals = game.get("totals", {})
        if totals.get("edge") is not None and (totals.get("stars") or 1) >= 2:
            bets.append({
                "type": "TOTAL",
                "game": matchup,
                "play": f"{totals.get('play')} {totals.get('line')}",
                "edge": totals.get("edge"),
                "edge_abs": abs(totals.get("edge", 0)),
                "conf": totals.get("conf", "LOW"),
                "stars": totals.get("stars", 1),
                "tip": tip,
                "market_line": totals.get("line"),
                "model_line": totals.get("pred"),
                "verdict": "BET",
            })

    bets.sort(key=lambda b: (-b.get("stars", 1), -abs(b.get("edge_abs", b.get("edge", 0)))))
    for i, bet in enumerate(bets[:8], start=1):
        bet["rank"] = i
    return bets[:8]


def patch_predictions(target_date):
    path = prediction_path(target_date)
    with open(path) as f:
        data = json.load(f)

    odds_df = load_odds(target_date)
    props_df = load_props(target_date)
    points_df = load_player_points(target_date)
    odds_loaded = not odds_df.empty
    props_loaded = not props_df.empty
    points_loaded = not points_df.empty
    spreads_found = 0
    totals_found = 0

    for game in data.get("games", []):
        home = game.get("home", {}).get("name")
        away = game.get("away", {}).get("name")
        odds_row = find_odds_row(odds_df, home, away)

        if odds_row is not None:
            posted_spread = to_float(odds_row.get("spread_home"))
            posted_total = to_float(odds_row.get("total"))
            game["market"] = {
                "source": odds_row.get("source", "the-odds-api"),
                "books": int(odds_row.get("num_books", 0) or 0),
                "scraped_at": str(odds_row.get("scraped_at", "")),
            }
        else:
            posted_spread = None
            posted_total = None
            game["market"] = {"source": None, "books": 0, "scraped_at": None}

        spread = game.setdefault("spread", {})
        model_margin = to_float(spread.get("pred"))
        if posted_spread is not None and model_margin is not None:
            home_edge = round(model_margin + posted_spread, 1)
            bet_home = home_edge >= 0
            play_team = home if bet_home else away
            play_line = posted_spread if bet_home else -posted_spread
            edge_abs = abs(home_edge)
            conf, stars = score_confidence(edge_abs, "spread")
            spread.update({
                "posted_line": posted_spread,
                "edge": round(home_edge, 1),
                "edge_abs": round(edge_abs, 1),
                "play": fmt_spread_line(play_team, play_line),
                "conf": conf,
                "stars": stars,
            })
            spreads_found += 1
        else:
            spread.update({"posted_line": posted_spread, "edge": None, "edge_abs": None})

        totals = game.setdefault("totals", {})
        model_total = to_float(totals.get("pred"))
        if posted_total is not None and model_total is not None:
            edge = round(model_total - posted_total, 1)
            conf, stars = score_confidence(edge, "totals")
            totals.update({
                "line": posted_total,
                "edge": edge,
                "play": "OVER" if edge > 0 else "UNDER",
                "conf": conf,
                "stars": stars,
            })
            totals_found += 1
        else:
            if totals.get("line") is None:
                totals.update({"edge": None, "play": None})

    player_points = build_player_points_board(points_df)
    data["player_points"] = player_points
    data["spread_board"] = build_spread_board(data.get("games", []))
    data["props_board"] = build_props_board(props_df, data.get("games", []), player_points)
    data["best_bets"] = rebuild_best_bets(data.get("games", []))
    data["data_health"] = {
        "odds": "loaded" if odds_loaded else "missing",
        "props": "loaded" if props_loaded else "missing",
        "player_points": "loaded" if points_loaded else "missing",
        "spreads_found": spreads_found,
        "totals_found": totals_found,
        "props_found": len(data.get("props_board", [])),
        "player_points_found": len(player_points),
        "games": len(data.get("games", [])),
        "actionable_bets": len([b for b in data.get("best_bets", []) if b.get("stars", 0) >= 2]),
        "high_bets": len([b for b in data.get("best_bets", []) if b.get("stars") == 3]),
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  Patched predictions: {path}")
    print(f"  Odds health: {spreads_found} spreads, {totals_found} totals")
    print(f"  Player points: {len(player_points)} rows")
    print(f"  Props board: {len(data['props_board'])} props")
    print(f"  Best bets rebuilt: {len(data['best_bets'])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    print(f"\n═══ POSTPROCESS PREDICTIONS — {args.date} ═══\n")
    patch_predictions(args.date)
    print("✅ Postprocess complete.")


if __name__ == "__main__":
    main()
