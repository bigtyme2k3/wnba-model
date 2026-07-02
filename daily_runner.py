"""
daily_runner.py
---------------
Master pipeline orchestrator. Run every morning before games tip off.

Steps:
  1. Fetch today's schedule from live sports feed
  2. Load latest team + player rolling stats
  3. Run spread model  → spread predictions per game
  4. Run totals model  → over/under predictions per game
  5. Run props model   → player prop signals per game
  6. Rank all plays by confidence
  7. Write predictions_YYYY-MM-DD.json

Usage:
    python daily_runner.py
    python daily_runner.py --date 2026-05-12
    python daily_runner.py --date 2026-05-12 --out /path/to/output.json
"""

import os, sys, json, pickle, argparse, warnings
import numpy as np
import pandas as pd
from datetime import date, datetime
warnings.filterwarnings("ignore")

BASE_DIR   = "."
MODEL_DIR  = "models"
DATA_DIR   = "data/processed"
OUTPUT_DIR = f"{BASE_DIR}/predictions"
os.makedirs(OUTPUT_DIR, exist_ok=True)

sys.path.insert(0, BASE_DIR)
from feature_fixes   import compute_improved_rolling, quality_floor, anchored_rolling, blowout_dampened_margin
from totals_model    import engineer_totals_features, TOTALS_FEATURES
from props_model     import prepare_data as prepare_props, PROP_TARGETS


# ── Team metadata ─────────────────────────────────────────────────────────────

WEST = {"Las Vegas Aces","Golden State Valkyries","Seattle Storm",
        "Los Angeles Sparks","Phoenix Mercury","Portland Fire","Dallas Wings","Minnesota Lynx"}
EAST = {"New York Liberty","Connecticut Sun","Atlanta Dream",
        "Washington Mystics","Indiana Fever","Toronto Tempo","Chicago Sky"}

TEAM_ABBR = {
    "ATL":"Atlanta Dream","CHI":"Chicago Sky","CON":"Connecticut Sun",
    "DAL":"Dallas Wings","GSV":"Golden State Valkyries","IND":"Indiana Fever",
    "LAS":"Los Angeles Sparks","LVA":"Las Vegas Aces","MIN":"Minnesota Lynx",
    "NYL":"New York Liberty","PDX":"Portland Fire","PHX":"Phoenix Mercury",
    "SEA":"Seattle Storm","TOR":"Toronto Tempo","WAS":"Washington Mystics",
}

# Current season stats — updated weekly from collect_stats.py
# These get overwritten once the real pipeline runs
CURRENT_TEAM_STATS = {
    "Las Vegas Aces":         {"net_rtg": 8.4,"ortg":109,"drtg":101,"pace":86,"ts_pct":0.595},
    "New York Liberty":       {"net_rtg": 8.1,"ortg":108,"drtg":100,"pace":86,"ts_pct":0.601},
    "Minnesota Lynx":         {"net_rtg": 3.8,"ortg":105,"drtg":101,"pace":84,"ts_pct":0.566},
    "Connecticut Sun":        {"net_rtg": 2.1,"ortg":104,"drtg":102,"pace":84,"ts_pct":0.571},
    "Indiana Fever":          {"net_rtg": 1.8,"ortg":103,"drtg":101,"pace":84,"ts_pct":0.559},
    "Seattle Storm":          {"net_rtg":-1.5,"ortg":101,"drtg":103,"pace":83,"ts_pct":0.554},
    "Atlanta Dream":          {"net_rtg": 0.5,"ortg":102,"drtg":102,"pace":83,"ts_pct":0.534},
    "Dallas Wings":           {"net_rtg":-1.0,"ortg":101,"drtg":102,"pace":83,"ts_pct":0.537},
    "Chicago Sky":            {"net_rtg":-0.8,"ortg":101,"drtg":102,"pace":83,"ts_pct":0.543},
    "Phoenix Mercury":        {"net_rtg":-0.5,"ortg":102,"drtg":103,"pace":83,"ts_pct":0.531},
    "Golden State Valkyries": {"net_rtg": 0.0,"ortg":102,"drtg":102,"pace":84,"ts_pct":0.540},
    "Toronto Tempo":          {"net_rtg":-2.5,"ortg":100,"drtg":103,"pace":83,"ts_pct":0.526},
    "Washington Mystics":     {"net_rtg":-3.0,"ortg": 99,"drtg":102,"pace":82,"ts_pct":0.526},
    "Los Angeles Sparks":     {"net_rtg":-4.5,"ortg": 97,"drtg":104,"pace":82,"ts_pct":0.515},
    "Portland Fire":          {"net_rtg":-3.0,"ortg": 99,"drtg":102,"pace":82,"ts_pct":0.515},
}

# Rolling form — updated daily from game log
TEAM_ROLLING = {
    "Las Vegas Aces":         {"roll5": 2.5, "roll10": 4.1, "roll_pts":105,"roll_allowed": 78},
    "New York Liberty":       {"roll5":14.2, "roll10": 9.8, "roll_pts": 98,"roll_allowed": 93},
    "Minnesota Lynx":         {"roll5":-0.5, "roll10": 2.0, "roll_pts": 90,"roll_allowed": 91},
    "Connecticut Sun":        {"roll5":-8.0, "roll10":-3.5, "roll_pts": 82,"roll_allowed": 89},
    "Indiana Fever":          {"roll5":-1.5, "roll10": 0.5, "roll_pts":104,"roll_allowed":107},
    "Seattle Storm":          {"roll5":-4.8, "roll10":-2.1, "roll_pts": 89,"roll_allowed": 82},
    "Atlanta Dream":          {"roll5": 1.0, "roll10": 1.0, "roll_pts": 91,"roll_allowed": 90},
    "Dallas Wings":           {"roll5": 3.0, "roll10": 1.0, "roll_pts":107,"roll_allowed":104},
    "Chicago Sky":            {"roll5": 7.5, "roll10": 3.2, "roll_pts": 98,"roll_allowed": 83},
    "Phoenix Mercury":        {"roll5":16.7, "roll10": 5.8, "roll_pts": 79,"roll_allowed": 95},
    "Golden State Valkyries": {"roll5": 7.0, "roll10": 3.2, "roll_pts": 95,"roll_allowed": 79},
    "Toronto Tempo":          {"roll5":-1.5, "roll10":-1.0, "roll_pts": 65,"roll_allowed": 68},
    "Washington Mystics":     {"roll5": 1.5, "roll10": 0.8, "roll_pts": 93,"roll_allowed": 98},
    "Los Angeles Sparks":     {"roll5":-3.2, "roll10":-2.8, "roll_pts": 78,"roll_allowed":105},
    "Portland Fire":          {"roll5":-7.5, "roll10":-3.8, "roll_pts": 83,"roll_allowed": 98},
}

# Player props profiles — updated weekly from player_logs pipeline
PLAYER_PROPS = {
    "A'ja Wilson":       {"team":"Las Vegas Aces",    "pos":"C","mpg":32,"usage":0.310,"ts":0.615,
                          "roll5_pts":24.2,"roll5_reb":10.1,"roll5_ast":2.8,"roll5_threes":0.2,
                          "base_pts":22.8,"base_reb":9.4,"base_ast":2.4},
    "Kelsey Plum":       {"team":"Las Vegas Aces",    "pos":"G","mpg":30,"usage":0.265,"ts":0.598,
                          "roll5_pts":18.2,"roll5_reb":3.0,"roll5_ast":5.1,"roll5_threes":1.8,
                          "base_pts":17.8,"base_reb":2.9,"base_ast":4.8},
    "Breanna Stewart":   {"team":"New York Liberty",  "pos":"F","mpg":33,"usage":0.295,"ts":0.608,
                          "roll5_pts":22.8,"roll5_reb":8.8,"roll5_ast":4.1,"roll5_threes":1.4,
                          "base_pts":21.3,"base_reb":8.5,"base_ast":3.8},
    "Sabrina Ionescu":   {"team":"New York Liberty",  "pos":"G","mpg":34,"usage":0.280,"ts":0.591,
                          "roll5_pts":18.8,"roll5_reb":5.4,"roll5_ast":6.8,"roll5_threes":2.2,
                          "base_pts":19.4,"base_reb":5.8,"base_ast":6.1},
    "Napheesa Collier":  {"team":"Minnesota Lynx",    "pos":"F","mpg":34,"usage":0.290,"ts":0.601,
                          "roll5_pts":20.8,"roll5_reb":8.4,"roll5_ast":3.6,"roll5_threes":0.4,
                          "base_pts":20.4,"base_reb":8.1,"base_ast":3.5},
    "Caitlin Clark":     {"team":"Indiana Fever",     "pos":"G","mpg":35,"usage":0.302,"ts":0.574,
                          "roll5_pts":21.4,"roll5_reb":6.2,"roll5_ast":9.1,"roll5_threes":2.4,
                          "base_pts":19.2,"base_reb":5.7,"base_ast":8.4},
    "Angel Reese":       {"team":"Chicago Sky",       "pos":"C","mpg":30,"usage":0.248,"ts":0.548,
                          "roll5_pts":14.2,"roll5_reb":14.0,"roll5_ast":1.6,"roll5_threes":0.0,
                          "base_pts":13.6,"base_reb":13.1,"base_ast":1.5},
    "Arike Ogunbowale":  {"team":"Dallas Wings",      "pos":"G","mpg":33,"usage":0.298,"ts":0.581,
                          "roll5_pts":22.4,"roll5_reb":4.1,"roll5_ast":4.5,"roll5_threes":1.8,
                          "base_pts":21.8,"base_reb":3.9,"base_ast":4.2},
}

OPP_DEF_POS = {t: {"G":101,"F":102,"C":102} for t in CURRENT_TEAM_STATS}
OPP_DEF_POS.update({
    "Las Vegas Aces":   {"G": 98,"F": 99,"C":100},
    "New York Liberty": {"G": 99,"F": 99,"C":100},
    "Minnesota Lynx":   {"G":100,"F":100,"C":101},
    "Connecticut Sun":  {"G":100,"F": 99,"C":100},
})


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_models():
    with open(f"{MODEL_DIR}/spread_model_v2.pkl","rb") as f: spread = pickle.load(f)
    with open(f"{MODEL_DIR}/totals_model.pkl",    "rb") as f: totals = pickle.load(f)
    with open(f"{MODEL_DIR}/props_models.pkl",    "rb") as f: props  = pickle.load(f)
    return spread, totals, props


def build_schedule_context(home, away, target_date, game_num=5):
    """Build schedule context flags for a matchup."""
    long_travel = (home in WEST and away in EAST) or (home in EAST and away in WEST)
    e2w = int(away in EAST and home in WEST)
    w2e = int(away in WEST and home in EAST)
    return {
        "home_rest_days":  2,   # Updated from schedule scraper when live
        "away_rest_days":  2,
        "home_b2b":        False,
        "away_b2b":        False,
        "home_3in4":       False,
        "away_3in4":       False,
        "long_travel":     long_travel,
        "east_to_west":    e2w,
        "west_to_east":    w2e,
        "season_game_num": game_num,
        "month":           target_date.month,
    }


# ── Spread prediction ─────────────────────────────────────────────────────────

def run_spread(home, away, ctx, spread_bundle):
    model  = spread_bundle["model"]
    feats  = spread_bundle["feature_names"]
    hs     = CURRENT_TEAM_STATS.get(home, {})
    as_    = CURRENT_TEAM_STATS.get(away, {})
    hr     = TEAM_ROLLING.get(home, {})
    ar     = TEAM_ROLLING.get(away, {})

    row = {f: 0 for f in feats}
    row.update({
        "home_improved_5g":  hr.get("roll5", 0),
        "away_improved_5g":  ar.get("roll5", 0),
        "improved_diff_5g":  hr.get("roll5", 0) - ar.get("roll5", 0),
        "home_improved_10g": hr.get("roll10", 0),
        "away_improved_10g": ar.get("roll10", 0),
        "home_net_rtg":      hs.get("net_rtg", 0),
        "away_net_rtg":      as_.get("net_rtg", 0),
        "net_rtg_diff":      hs.get("net_rtg", 0) - as_.get("net_rtg", 0),
        "home_ortg":         hs.get("ortg", 102),
        "away_ortg":         as_.get("ortg", 102),
        "home_drtg":         hs.get("drtg", 102),
        "away_drtg":         as_.get("drtg", 102),
        "home_pace":         hs.get("pace", 83),
        "away_pace":         as_.get("pace", 83),
        "avg_pace":          (hs.get("pace",83) + as_.get("pace",83)) / 2,
        "home_rest_days":    ctx["home_rest_days"],
        "away_rest_days":    ctx["away_rest_days"],
        "rest_diff":         ctx["home_rest_days"] - ctx["away_rest_days"],
        "home_back_to_back": int(ctx["home_b2b"]),
        "away_back_to_back": int(ctx["away_b2b"]),
        "home_three_in_four":int(ctx["home_3in4"]),
        "away_three_in_four":int(ctx["away_3in4"]),
        "long_travel":       int(ctx["long_travel"]),
        "east_to_west":      ctx["east_to_west"],
        "west_to_east":      ctx["west_to_east"],
        "season_game_num":   ctx["season_game_num"],
        "month":             ctx["month"],
        "is_playoff":        int(ctx["month"] >= 9),
    })

    X    = pd.DataFrame([row])[feats]
    pred = float(model.predict(X)[0])
    return round(pred, 1)   # positive = home favored


# ── Totals prediction ─────────────────────────────────────────────────────────

def run_totals(home, away, ctx, totals_bundle):
    model  = totals_bundle["model"]
    feats  = totals_bundle["feature_names"]
    hs     = CURRENT_TEAM_STATS.get(home, {})
    as_    = CURRENT_TEAM_STATS.get(away, {})
    hr     = TEAM_ROLLING.get(home, {})
    ar     = TEAM_ROLLING.get(away, {})
    avg_p  = (hs.get("pace",83) + as_.get("pace",83)) / 2

    row = {f: 0 for f in feats}
    row.update({
        "avg_pace":               avg_p,
        "home_pace":              hs.get("pace",83),
        "away_pace":              as_.get("pace",83),
        "pace_sum":               hs.get("pace",83) + as_.get("pace",83),
        "home_ortg":              hs.get("ortg",102),
        "away_ortg":              as_.get("ortg",102),
        "combined_ortg":          hs.get("ortg",102) + as_.get("ortg",102),
        "home_drtg":              hs.get("drtg",102),
        "away_drtg":              as_.get("drtg",102),
        "combined_drtg":          hs.get("drtg",102) + as_.get("drtg",102),
        "home_ts_pct":            hs.get("ts_pct",0.555),
        "away_ts_pct":            as_.get("ts_pct",0.555),
        "combined_ts":            hs.get("ts_pct",0.555) + as_.get("ts_pct",0.555),
        "pace_x_ortg":            avg_p * (hs.get("ortg",102)+as_.get("ortg",102)) / 200,
        "def_mismatch":           abs((hs.get("ortg",102)-as_.get("drtg",102))-(as_.get("ortg",102)-hs.get("drtg",102))),
        "home_rolling_total_5g":  hr.get("roll_pts",  hs.get("ortg",102)),
        "away_rolling_total_5g":  ar.get("roll_pts",  as_.get("ortg",102)),
        "home_rolling_allowed_5g":hr.get("roll_allowed",hs.get("drtg",102)),
        "away_rolling_allowed_5g":ar.get("roll_allowed",as_.get("drtg",102)),
        "rolling_total_sum_5g":   hr.get("roll_pts",102) + ar.get("roll_pts",102),
        "home_back_to_back":      int(ctx["home_b2b"]),
        "away_back_to_back":      int(ctx["away_b2b"]),
        "both_b2b":               int(ctx["home_b2b"] and ctx["away_b2b"]),
        "home_rest_days":         ctx["home_rest_days"],
        "away_rest_days":         ctx["away_rest_days"],
        "long_travel":            int(ctx["long_travel"]),
        "month":                  ctx["month"],
        "is_playoff":             int(ctx["month"] >= 9),
        "season_game_num":        ctx["season_game_num"],
    })

    X    = pd.DataFrame([row])[feats]
    pred = float(model.predict(X)[0])
    return round(pred, 1)


# ── Props prediction ──────────────────────────────────────────────────────────

def run_props(home, away, ctx, props_bundle, posted_lines=None):
    models     = props_bundle["models"]
    thresholds = props_bundle["thresholds"]
    posted     = posted_lines or {}
    results    = []

    avg_pace = (CURRENT_TEAM_STATS.get(home,{}).get("pace",83) +
                CURRENT_TEAM_STATS.get(away,{}).get("pace",83)) / 2

    for player, pdata in PLAYER_PROPS.items():
        if pdata["team"] not in [home, away]:
            continue

        opp = away if pdata["team"] == home else home
        opp_def = OPP_DEF_POS.get(opp, {}).get(pdata["pos"], 102)
        is_home = int(pdata["team"] == home)
        b2b     = ctx["home_b2b"] if is_home else ctx["away_b2b"]
        rest    = ctx["home_rest_days"] if is_home else ctx["away_rest_days"]
        proj_min = pdata["mpg"] * (0.88 if b2b else 1.0)

        row = {
            "minutes":        proj_min,
            "roll5_minutes":  pdata["mpg"],
            "usage":          pdata["usage"],
            "ts_pct":         pdata["ts"],
            "opp_drtg_pos":   opp_def,
            "avg_pace":       avg_pace,
            "team_pace":      CURRENT_TEAM_STATS.get(pdata["team"],{}).get("pace",83),
            "rest_days":      rest,
            "is_home":        is_home,
            "roll5_pts":      pdata["roll5_pts"],
            "roll5_reb":      pdata["roll5_reb"],
            "roll5_ast":      pdata["roll5_ast"],
            "roll5_threes":   pdata.get("roll5_threes",1.0),
            "roll5_pra":      pdata["roll5_pts"]+pdata["roll5_reb"]+pdata["roll5_ast"],
            "season_game_num":ctx["season_game_num"],
            "month":          ctx["month"],
            "def_adj":        102 - opp_def,
            "usage_pace":     pdata["usage"] * avg_pace / 83.0,
            "min_risk_flag":  int(proj_min < pdata["mpg"] * 0.75),
        }

        player_result = {
            "player":    player,
            "team":      pdata["team"],
            "opp":       opp,
            "pos":       pdata["pos"],
            "proj_min":  round(proj_min, 1),
            "b2b":       b2b,
            "props":     {}
        }

        for target in PROP_TARGETS:
            m      = models[target]
            feats  = [f for f in m["features"] if f in row]
            X      = pd.DataFrame([row])[feats]
            pred   = float(m["model"].predict(X)[0])
            thresh = thresholds[target]
            line   = posted.get(player, {}).get(target)
            edge   = round(pred - line, 1) if line else None
            signal = None
            if edge is not None:
                if edge >  thresh: signal = "OVER"
                elif edge < -thresh: signal = "UNDER"

            player_result["props"][target] = {
                "pred":   round(pred, 1),
                "line":   line,
                "edge":   edge,
                "signal": signal,
            }

        results.append(player_result)

    return results


# ── Confidence scoring ────────────────────────────────────────────────────────

def score_confidence(edge, model_type):
    thresholds = {
        "spread": {"HIGH": 5.0, "MED": 3.0},
        "totals": {"HIGH": 4.0, "MED": 2.0},
        "props":  {"HIGH": 3.5, "MED": 2.0},
    }
    t = thresholds.get(model_type, {"HIGH":5,"MED":3})
    abs_edge = abs(edge)
    if abs_edge >= t["HIGH"]: return "HIGH", 3
    if abs_edge >= t["MED"]:  return "MED",  2
    return "LOW", 1


def collect_best_bets(games_output):
    bets = []
    for g in games_output:
        home, away = g["home"]["name"], g["away"]["name"]
        matchup = f"{away} @ {home}"

        # Spread
        sp = g["spread"]
        if sp.get("edge"):
            conf, stars = score_confidence(sp["edge"], "spread")
            if stars >= 2:
                bets.append({
                    "type":"SPREAD","game":matchup,"play":sp["model_line"],
                    "edge":sp["edge"],"conf":conf,"stars":stars,
                    "tip": g["tip"],
                })

        # Totals
        tot = g["totals"]
        if tot.get("edge"):
            conf, stars = score_confidence(tot["edge"], "totals")
            if stars >= 2:
                bets.append({
                    "type":"TOTAL","game":matchup,
                    "play":f"{tot['play']} {tot['line']}",
                    "edge":tot["edge"],"conf":conf,"stars":stars,
                    "tip": g["tip"],
                })

        # Props
        for pr in g.get("props", []):
            for prop_type, pdata in pr["props"].items():
                if pdata["signal"] and pdata["edge"] is not None:
                    conf, stars = score_confidence(pdata["edge"], "props")
                    if stars >= 2:
                        bets.append({
                            "type":"PROP","game":matchup,
                            "play":f"{pr['player']} {prop_type.upper()} {pdata['signal']} {pdata['line']}",
                            "edge":pdata["edge"],"conf":conf,"stars":stars,
                            "tip": g["tip"],
                        })

    bets.sort(key=lambda b: (-b["stars"], -abs(b["edge"])))
    for i, b in enumerate(bets): b["rank"] = i + 1
    return bets[:8]   # top 8


# ── Main orchestrator ─────────────────────────────────────────────────────────

def run_pipeline(target_date: date, schedule: list, posted_totals: dict = None, posted_props: dict = None):
    print(f"\n═══ WNBA DAILY PIPELINE — {target_date} ═══\n")

    spread_bundle, totals_bundle, props_bundle = load_models()
    print("✅ Models loaded\n")

    posted_totals = posted_totals or {}
    posted_props  = posted_props  or {}
    games_output  = []

    for game in schedule:
        home = game["home"]
        away = game["away"]
        tip  = game["tip"]
        num  = game.get("game_num", 5)

        print(f"  Processing: {away} @ {home}  ({tip})")
        ctx = build_schedule_context(home, away, target_date, num)

        # Apply manual B2B overrides from schedule
        ctx.update({
            "home_b2b":      game.get("home_b2b", False),
            "away_b2b":      game.get("away_b2b", False),
            "home_rest_days":game.get("home_rest", 2),
            "away_rest_days":game.get("away_rest", 2),
        })

        # Spread
        spread_pred = run_spread(home, away, ctx, spread_bundle)
        posted_spread = game.get("posted_spread")
        spread_edge = None
        if posted_spread:
            spread_edge = round(spread_pred - (-posted_spread), 1)

        def fmt_line(pred, h, a):
            if abs(pred) < 0.5: return "Pick'em"
            return f"{h} -{abs(pred):.1f}" if pred > 0 else f"{a} -{abs(pred):.1f}"

        spread_conf, spread_stars = score_confidence(spread_edge or 0, "spread")

        # Totals
        total_pred   = run_totals(home, away, ctx, totals_bundle)
        posted_total = posted_totals.get(f"{away}@{home}") or game.get("posted_total")
        total_edge   = round(total_pred - posted_total, 1) if posted_total else None
        total_play   = ("OVER" if total_edge and total_edge > 0 else "UNDER") if total_edge else None
        total_conf, total_stars = score_confidence(total_edge or 0, "totals")

        # Props
        props_out = run_props(home, away, ctx, props_bundle,
                              posted_props.get(f"{away}@{home}", {}))

        # Flags
        flags = []
        if ctx["away_b2b"]:  flags.append(f"B2B ({TEAM_ABBR.get(away[:3].upper(), away[:3])})")
        if ctx["home_b2b"]:  flags.append(f"B2B ({TEAM_ABBR.get(home[:3].upper(), home[:3])})")
        if ctx["long_travel"]: flags.append("Travel")

        hs = CURRENT_TEAM_STATS.get(home, {})
        as_ = CURRENT_TEAM_STATS.get(away, {})

        games_output.append({
            "tip":  tip,
            "home": {"name": home, "abbr": home[:3].upper(),
                     "record": game.get("home_record","?-?"),
                     "net_rtg": hs.get("net_rtg", 0)},
            "away": {"name": away, "abbr": away[:3].upper(),
                     "record": game.get("away_record","?-?"),
                     "net_rtg": as_.get("net_rtg", 0)},
            "spread": {
                "pred":       spread_pred,
                "model_line": fmt_line(spread_pred, home, away),
                "posted_line":game.get("posted_spread"),
                "edge":       spread_edge,
                "conf":       spread_conf,
                "stars":      spread_stars,
            },
            "totals": {
                "pred":  total_pred,
                "line":  posted_total,
                "edge":  total_edge,
                "play":  total_play,
                "conf":  total_conf,
                "stars": total_stars,
            },
            "props": props_out,
            "flags": flags,
            "ctx":   {k: v for k, v in ctx.items() if not isinstance(v, np.bool_)},
        })

    best_bets = collect_best_bets(games_output)

    output = {
        "date":      str(target_date),
        "generated": datetime.now().isoformat(),
        "games":     games_output,
        "best_bets": best_bets,
        "model_stats": {
            "spread": {"algo":"Ridge v2","cv_mae":9.72,"dir_acc":0.716,"strong_ats":0.815,"n":263},
            "totals": {"algo":"Random Forest","cv_mae":6.77,"ou_acc":0.542,"strong_ou":0.554,"n":939},
            "props":  {"algo":"Ridge","cv_mae":6.00,"hit_rate":0.721,"strong_hr":0.754,"n":1337},
        },
    }

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out",  default=None)
    args = parser.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date()

    # Tonight's schedule — in production this comes from the live sports feed
    SCHEDULE = [
        {"home":"Dallas Wings",    "away":"Atlanta Dream",
         "tip":"8:00 PM ET","home_rest":2,"away_rest":2,"posted_total":158.5},
        {"home":"Phoenix Mercury", "away":"Minnesota Lynx",
         "tip":"10:00 PM ET","home_rest":1,"away_rest":1,"away_b2b":True,"posted_total":162.5},
        {"home":"Portland Fire",   "away":"New York Liberty",
         "tip":"10:00 PM ET","home_rest":2,"away_rest":1,"away_b2b":True,"posted_total":155.0},
    ]

    POSTED_PROPS = {
        "Atlanta Dream@Dallas Wings": {},
        "Minnesota Lynx@Phoenix Mercury": {
            "Napheesa Collier": {"pts":20.5,"reb":8.5,"ast":3.5,"threes":0.5,"pra":32.5},
        },
        "New York Liberty@Portland Fire": {
            "Sabrina Ionescu":  {"pts":18.5,"reb":5.5,"ast":6.5,"threes":2.5,"pra":30.5},
            "Breanna Stewart":  {"pts":22.5,"reb":8.5,"ast":4.0,"threes":1.5,"pra":35.0},
        },
    }

    result = run_pipeline(target, SCHEDULE, posted_props=POSTED_PROPS)

    out_path = args.out or f"{OUTPUT_DIR}/predictions_{target}.json"
    # Convert numpy types
    def convert(o):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, (np.bool_,)): return bool(o)
        raise TypeError(f"Not serializable: {type(o)}")

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=convert)

    print(f"\n✅ Predictions written → {out_path}")
    print(f"   Games: {len(result['games'])} | Best bets: {len(result['best_bets'])}")
    print(f"\nTop plays:")
    for b in result["best_bets"][:3]:
        print(f"  #{b['rank']} [{b['type']}] {b['play']}  edge={b['edge']}  conf={b['conf']}")
