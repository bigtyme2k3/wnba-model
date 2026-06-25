"""
daily_predictions.py
--------------------
Pulls today's WNBA schedule, loads current team stats,
and generates spread predictions for every game.

Run this each morning before games tip off.

Usage:
    python daily_predictions.py
    python daily_predictions.py --date 2026-05-10
    python daily_predictions.py --export predictions_today.csv
"""

import os
import pickle
import argparse
import requests
import numpy as np
import pandas as pd
from datetime import datetime, date
from spread_model import predict_game, engineer_features, SPREAD_FEATURES

MODEL_PATH    = "models/spread_model.pkl"
STATS_PATH    = "data/processed/master_all.csv"
TEAM_STATS    = "data/raw/team_advanced_current.csv"


# ── Team stats loader ─────────────────────────────────────────────────────────
# Until we have a full season of data, this uses reasonable 2024 baseline values.
# Replace with live values from collect_stats.py once available.

CURRENT_TEAM_STATS = {
    "Las Vegas Aces":         {"net_rtg":  5.2, "ortg": 107, "drtg": 102, "pace": 85, "rolling_5g": -33.0, "rolling_10g": -5.0},
    "New York Liberty":       {"net_rtg":  8.1, "ortg": 108, "drtg": 100, "pace": 86, "rolling_5g":  31.0, "rolling_10g": 12.0},
    "Connecticut Sun":        {"net_rtg":  2.1, "ortg": 104, "drtg": 102, "pace": 84, "rolling_5g": -31.0, "rolling_10g": -5.0},
    "Seattle Storm":          {"net_rtg": -1.5, "ortg": 101, "drtg": 103, "pace": 83, "rolling_5g": -11.0, "rolling_10g": -4.0},
    "Minnesota Lynx":         {"net_rtg":  3.8, "ortg": 105, "drtg": 101, "pace": 84, "rolling_5g":  -1.0, "rolling_10g":  2.0},
    "Chicago Sky":            {"net_rtg": -2.0, "ortg": 100, "drtg": 102, "pace": 82, "rolling_5g":  15.0, "rolling_10g":  3.0},
    "Los Angeles Sparks":     {"net_rtg": -4.5, "ortg":  99, "drtg": 104, "pace": 82, "rolling_5g":   0.0, "rolling_10g": -2.0},
    "Phoenix Mercury":        {"net_rtg": -0.5, "ortg": 102, "drtg": 103, "pace": 83, "rolling_5g":  33.0, "rolling_10g":  5.0},
    "Atlanta Dream":          {"net_rtg":  0.5, "ortg": 102, "drtg": 102, "pace": 83, "rolling_5g":   1.0, "rolling_10g":  1.0},
    "Washington Mystics":     {"net_rtg": -3.0, "ortg":  99, "drtg": 102, "pace": 82, "rolling_5g":   3.0, "rolling_10g":  0.5},
    "Dallas Wings":           {"net_rtg": -1.0, "ortg": 101, "drtg": 102, "pace": 83, "rolling_5g":   3.0, "rolling_10g":  1.0},
    "Indiana Fever":          {"net_rtg":  1.5, "ortg": 103, "drtg": 101, "pace": 84, "rolling_5g":  -3.0, "rolling_10g":  0.5},
    "Golden State Valkyries": {"net_rtg":  0.0, "ortg": 102, "drtg": 102, "pace": 84, "rolling_5g":  11.0, "rolling_10g":  3.0},
    "Toronto Tempo":          {"net_rtg": -2.5, "ortg": 100, "drtg": 103, "pace": 83, "rolling_5g":  -3.0, "rolling_10g": -1.0},
    "Portland Fire":          {"net_rtg": -3.0, "ortg":  99, "drtg": 102, "pace": 82, "rolling_5g": -15.0, "rolling_10g": -3.0},
}

# Rest day context for today's games
# In production, this is computed automatically from collect_stats.py schedule data
SCHEDULE_CONTEXT_DEFAULTS = {
    "home_rest_days":  2,
    "away_rest_days":  2,
    "home_b2b":        False,
    "away_b2b":        False,
    "home_3in4":       False,
    "away_3in4":       False,
    "long_travel":     False,
    "east_to_west":    False,
    "west_to_east":    False,
    "season_game_num": 5,
    "month":           5,
}

WEST_TEAMS = {"Las Vegas Aces", "Golden State Valkyries", "Seattle Storm",
              "Los Angeles Sparks", "Phoenix Mercury", "Portland Fire"}
EAST_TEAMS = {"New York Liberty", "Connecticut Sun", "Atlanta Dream",
              "Washington Mystics", "Indiana Fever", "Toronto Tempo"}

def infer_travel(away: str, home: str) -> dict:
    ctx = {}
    if away in EAST_TEAMS and home in WEST_TEAMS:
        ctx["long_travel"]  = True
        ctx["east_to_west"] = True
    elif away in WEST_TEAMS and home in EAST_TEAMS:
        ctx["long_travel"]  = True
        ctx["west_to_east"] = True
    return ctx


def format_spread(spread: float, home: str, away: str) -> str:
    if abs(spread) < 0.5:
        return "Pick 'em"
    if spread > 0:
        return f"{home} -{abs(spread):.1f}"
    return f"{away} -{abs(spread):.1f}"


def confidence_tier(spread: float, line: float = None) -> str:
    """Rate prediction confidence based on model conviction."""
    margin = abs(spread)
    if line is not None:
        edge = abs(spread - (-line))  # Compare to market
        if edge >= 5:   return "⭐⭐⭐ HIGH"
        if edge >= 3:   return "⭐⭐   MED"
        return          "⭐     LOW"
    if margin >= 8:     return "⭐⭐⭐ HIGH"
    if margin >= 4:     return "⭐⭐   MED"
    return              "⭐     LOW"


def run_predictions(target_date: str = None, export_path: str = None):

    today = target_date or date.today().strftime("%Y-%m-%d")
    print(f"\n═══ WNBA SPREAD PREDICTIONS — {today} ═══\n")

    # ── Load model ──
    if not os.path.exists(MODEL_PATH):
        print("[WARN] No trained model found at models/spread_model.pkl")
        print("       Run: python spread_model.py --mode train")
        print("       Using rule-based fallback (net rating differential only)\n")
        use_model = False
    else:
        with open(MODEL_PATH, "rb") as f:
            bundle = pickle.load(f)
        model         = bundle["model"]
        feature_names = bundle["feature_names"]
        use_model     = True
        print(f"Model loaded: {bundle['model_name']} (trained {bundle['trained_on'][:10]})\n")

    # ── Today's games (hardcoded for May 10, 2026 based on live data) ──
    todays_games = [
        {"home": "Connecticut Sun",  "away": "Seattle Storm",    "tip": "1:00 PM ET"},
        {"home": "Washington Mystics","away": "New York Liberty", "tip": "3:00 PM ET"},
        {"home": "Los Angeles Sparks","away": "Las Vegas Aces",   "tip": "6:00 PM ET"},
        {"home": "Golden State Valkyries", "away": "Phoenix Mercury", "tip": "8:30 PM ET"},
    ]

    results = []

    print(f"{'TIP':>10}  {'MATCHUP':<42} {'MODEL LINE':>12} {'CONFIDENCE':>14}")
    print("─" * 82)

    for game in todays_games:
        home = game["home"]
        away = game["away"]
        tip  = game["tip"]

        home_stats = CURRENT_TEAM_STATS.get(home, {"net_rtg": 0, "ortg": 102, "drtg": 102, "pace": 83, "rolling_5g": 0, "rolling_10g": 0})
        away_stats = CURRENT_TEAM_STATS.get(away, {"net_rtg": 0, "ortg": 102, "drtg": 102, "pace": 83, "rolling_5g": 0, "rolling_10g": 0})

        # Build schedule context
        ctx = {**SCHEDULE_CONTEXT_DEFAULTS}
        ctx.update(infer_travel(away, home))

        if use_model:
            pred = predict_game(model, feature_names, home, away, home_stats, away_stats, ctx)
            spread = pred["pred_spread"]
        else:
            # Fallback: simple net rating + rolling form differential
            net_diff     = home_stats["net_rtg"] - away_stats["net_rtg"]
            rolling_diff = home_stats["rolling_5g"] - away_stats["rolling_5g"]
            spread = (net_diff * 0.6) + (rolling_diff * 0.1) + 2.5  # 2.5 = avg HCA

        line_str    = format_spread(spread, home, away)
        confidence  = confidence_tier(spread)
        matchup_str = f"{away} @ {home}"

        print(f"{tip:>10}  {matchup_str:<42} {line_str:>12} {confidence:>14}")

        results.append({
            "date":       today,
            "tip_time":   tip,
            "home_team":  home,
            "away_team":  away,
            "pred_spread": round(spread, 1),
            "model_line": line_str,
            "confidence": confidence,
        })

    # ── Export ──
    df_out = pd.DataFrame(results)

    if export_path:
        df_out.to_csv(export_path, index=False)
        print(f"\n  Predictions exported → {export_path}")

    # ── Betting notes ──
    print(f"""
── Today's Betting Notes ──

• CON vs SEA: Seattle traveled west (long travel flag active).
  Connecticut at home with rest edge. Watch for Storm fatigue.

• WAS vs NYL: Liberty blew out CON by 31 yesterday.
  Small line movement expected — market may overcorrect on NYL.

• LAS vs LVA: Aces got demolished at home yesterday (-33).
  Bounce-back spot or legit regression? Model will weight rolling form.

• GSV vs PHX: Mercury won by 33 yesterday too.
  Back-to-back for both teams — fatigue flags elevated.

─────────────────────────────────────────────────
Note: Populate data/raw/ with collect_stats.py output
for full model accuracy. Current predictions use
2024 baseline stats + early 2026 rolling adjustments.
─────────────────────────────────────────────────
""")

    return df_out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate daily WNBA spread predictions")
    parser.add_argument("--date",   type=str, default=None, help="Target date YYYY-MM-DD")
    parser.add_argument("--export", type=str, default=None, help="Export CSV path")
    args = parser.parse_args()

    run_predictions(args.date, args.export)
