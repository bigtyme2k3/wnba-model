"""
daily_runner.py — WNBA Daily Pipeline Orchestrator
Runs all three models and writes predictions JSON.

Usage:
    python daily_runner.py
    python daily_runner.py --date 2026-07-01
    python daily_runner.py --date 2026-07-01 --out predictions/today.json
"""

import os, sys, json, pickle, argparse, warnings
import numpy as np
import pandas as pd
from datetime import date, datetime
warnings.filterwarnings("ignore")

# ── Paths (relative — works on GitHub Actions and any machine) ─────────────────
MODEL_DIR  = "models"
DATA_DIR   = "data/processed"
OUTPUT_DIR = "predictions"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODEL_DIR,  exist_ok=True)

# ── Import local modules ───────────────────────────────────────────────────────
sys.path.insert(0, ".")
try:
    from feature_fixes import compute_improved_rolling, quality_floor, anchored_rolling, blowout_dampened_margin
except ImportError:
    print("[WARN] feature_fixes.py not found — some spread features will be skipped")
    compute_improved_rolling = None

try:
    from totals_model import engineer_totals_features, TOTALS_FEATURES
except ImportError:
    print("[WARN] totals_model.py not found")
    engineer_totals_features = None
    TOTALS_FEATURES = []

try:
    from props_model import PROP_TARGETS
except ImportError:
    print("[WARN] props_model.py not found")
    PROP_TARGETS = ["pts","reb","ast","threes","pra"]

try:
    from kelly_sizing import size_all_bets
    KELLY_AVAILABLE = True
except ImportError:
    print("[WARN] kelly_sizing.py not found — no unit sizing")
    KELLY_AVAILABLE = False

try:
    from scrape_refs import get_crew_stats
    REFS_AVAILABLE = True
except ImportError:
    REFS_AVAILABLE = False

try:
    from scrape_injuries import apply_injury_adjustments
    INJURIES_AVAILABLE = True
except ImportError:
    INJURIES_AVAILABLE = False


# ── Team metadata ──────────────────────────────────────────────────────────────
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

TEAM_ROLLING = {
    "Las Vegas Aces":         {"roll5": 2.5,"roll10": 4.1,"roll_pts":105,"roll_allowed": 78},
    "New York Liberty":       {"roll5":14.2,"roll10": 9.8,"roll_pts": 98,"roll_allowed": 93},
    "Minnesota Lynx":         {"roll5":-0.5,"roll10": 2.0,"roll_pts": 90,"roll_allowed": 91},
    "Connecticut Sun":        {"roll5":-8.0,"roll10":-3.5,"roll_pts": 82,"roll_allowed": 89},
    "Indiana Fever":          {"roll5":-1.5,"roll10": 0.5,"roll_pts":104,"roll_allowed":107},
    "Seattle Storm":          {"roll5":-4.8,"roll10":-2.1,"roll_pts": 89,"roll_allowed": 82},
    "Atlanta Dream":          {"roll5": 1.0,"roll10": 1.0,"roll_pts": 91,"roll_allowed": 90},
    "Dallas Wings":           {"roll5": 3.0,"roll10": 1.0,"roll_pts":107,"roll_allowed":104},
    "Chicago Sky":            {"roll5": 7.5,"roll10": 3.2,"roll_pts": 98,"roll_allowed": 83},
    "Phoenix Mercury":        {"roll5":16.7,"roll10": 5.8,"roll_pts": 79,"roll_allowed": 95},
    "Golden State Valkyries": {"roll5": 7.0,"roll10": 3.2,"roll_pts": 95,"roll_allowed": 79},
    "Toronto Tempo":          {"roll5":-1.5,"roll10":-1.0,"roll_pts": 65,"roll_allowed": 68},
    "Washington Mystics":     {"roll5": 1.5,"roll10": 0.8,"roll_pts": 93,"roll_allowed": 98},
    "Los Angeles Sparks":     {"roll5":-3.2,"roll10":-2.8,"roll_pts": 78,"roll_allowed":105},
    "Portland Fire":          {"roll5":-7.5,"roll10":-3.8,"roll_pts": 83,"roll_allowed": 98},
}

PLAYER_PROPS = {
    "A'ja Wilson":      {"team":"Las Vegas Aces",   "pos":"C","mpg":32,"usage":0.310,"ts":0.615,
                         "roll5_pts":24.2,"roll5_reb":10.1,"roll5_ast":2.8,"roll5_threes":0.2},
    "Breanna Stewart":  {"team":"New York Liberty", "pos":"F","mpg":33,"usage":0.295,"ts":0.608,
                         "roll5_pts":22.8,"roll5_reb":8.8,"roll5_ast":4.1,"roll5_threes":1.4},
    "Napheesa Collier": {"team":"Minnesota Lynx",   "pos":"F","mpg":34,"usage":0.290,"ts":0.601,
                         "roll5_pts":20.8,"roll5_reb":8.4,"roll5_ast":3.6,"roll5_threes":0.4},
    "Caitlin Clark":    {"team":"Indiana Fever",    "pos":"G","mpg":35,"usage":0.302,"ts":0.574,
                         "roll5_pts":21.4,"roll5_reb":6.2,"roll5_ast":9.1,"roll5_threes":2.4},
    "Sabrina Ionescu":  {"team":"New York Liberty", "pos":"G","mpg":34,"usage":0.280,"ts":0.591,
                         "roll5_pts":18.8,"roll5_reb":5.4,"roll5_ast":6.8,"roll5_threes":2.2},
    "Arike Ogunbowale": {"team":"Dallas Wings",     "pos":"G","mpg":33,"usage":0.298,"ts":0.581,
                         "roll5_pts":22.4,"roll5_reb":4.1,"roll5_ast":4.5,"roll5_threes":1.8},
    "Angel Reese":      {"team":"Chicago Sky",      "pos":"C","mpg":30,"usage":0.248,"ts":0.548,
                         "roll5_pts":14.2,"roll5_reb":14.0,"roll5_ast":1.6,"roll5_threes":0.0},
}

OPP_DEF_POS = {t: {"G":101,"F":102,"C":102} for t in CURRENT_TEAM_STATS}
OPP_DEF_POS.update({
    "Las Vegas Aces":   {"G": 98,"F": 99,"C":100},
    "New York Liberty": {"G": 99,"F": 99,"C":100},
    "Minnesota Lynx":   {"G":100,"F":100,"C":101},
    "Connecticut Sun":  {"G":100,"F": 99,"C":100},
})


# ── Get today's schedule from ESPN ────────────────────────────────────────────

def fetch_todays_schedule(target_date: date) -> list:
    """Pull today's WNBA games from ESPN public API."""
    import requests
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
    params = {"dates": target_date.strftime("%Y%m%d")}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [WARN] Could not fetch schedule: {e}")
        return []

    games = []
    for event in data.get("events", []):
        comps = event.get("competitions", [{}])[0]
        competitors = comps.get("competitors", [])
        if len(competitors) < 2:
            continue
        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
        home_name = home.get("team", {}).get("displayName","")
        away_name = away.get("team", {}).get("displayName","")
        tip_time  = event.get("date","")

        odds_list = comps.get("odds",[{}])
        posted_total = odds_list[0].get("overUnder") if odds_list else None

        games.append({
            "home":         home_name,
            "away":         away_name,
            "tip":          tip_time,
            "posted_total": posted_total,
            "home_rest":    2,
            "away_rest":    2,
        })

    print(f"  Fetched {len(games)} games from ESPN for {target_date}")
    return games


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_models():
    models = {}
    for key, fname in [("spread","spread_model_v2.pkl"),
                        ("totals","totals_model.pkl"),
                        ("props", "props_models.pkl")]:
        path = os.path.join(MODEL_DIR, fname)
        if os.path.exists(path):
            with open(path,"rb") as f:
                models[key] = pickle.load(f)
            print(f"  ✅ {fname} loaded")
        else:
            print(f"  [WARN] {fname} not found — skipping {key} predictions")
            models[key] = None
    return models.get("spread"), models.get("totals"), models.get("props")


def build_context(home, away, target_date, game):
    long_travel = (home in WEST and away in EAST) or (home in EAST and away in WEST)
    return {
        "home_rest_days":  game.get("home_rest", 2),
        "away_rest_days":  game.get("away_rest", 2),
        "home_b2b":        game.get("home_b2b", False),
        "away_b2b":        game.get("away_b2b", False),
        "home_3in4":       False,
        "away_3in4":       False,
        "long_travel":     long_travel,
        "east_to_west":    int(away in EAST and home in WEST),
        "west_to_east":    int(away in WEST and home in EAST),
        "season_game_num": game.get("game_num", 10),
        "month":           target_date.month,
    }


# ── Predictions ────────────────────────────────────────────────────────────────

def run_spread(home, away, ctx, bundle):
    if bundle is None: return 0.0
    model = bundle["model"]
    feats = bundle["feature_names"]
    hs, as_ = CURRENT_TEAM_STATS.get(home,{}), CURRENT_TEAM_STATS.get(away,{})
    hr, ar  = TEAM_ROLLING.get(home,{}), TEAM_ROLLING.get(away,{})
    row = {f: 0 for f in feats}
    row.update({
        "home_improved_5g":  hr.get("roll5",0),
        "away_improved_5g":  ar.get("roll5",0),
        "improved_diff_5g":  hr.get("roll5",0) - ar.get("roll5",0),
        "home_improved_10g": hr.get("roll10",0),
        "away_improved_10g": ar.get("roll10",0),
        "home_net_rtg":      hs.get("net_rtg",0),
        "away_net_rtg":      as_.get("net_rtg",0),
        "net_rtg_diff":      hs.get("net_rtg",0) - as_.get("net_rtg",0),
        "home_ortg":         hs.get("ortg",102),
        "away_ortg":         as_.get("ortg",102),
        "home_drtg":         hs.get("drtg",102),
        "away_drtg":         as_.get("drtg",102),
        "home_pace":         hs.get("pace",83),
        "away_pace":         as_.get("pace",83),
        "avg_pace":          (hs.get("pace",83)+as_.get("pace",83))/2,
        "home_rest_days":    ctx["home_rest_days"],
        "away_rest_days":    ctx["away_rest_days"],
        "rest_diff":         ctx["home_rest_days"]-ctx["away_rest_days"],
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
    try:
        X = pd.DataFrame([row])[feats]
        return round(float(model.predict(X)[0]), 1)
    except Exception as e:
        print(f"  [WARN] Spread prediction error: {e}")
        return 0.0


def run_totals(home, away, ctx, bundle):
    if bundle is None: return 160.0
    model = bundle["model"]
    feats = bundle["feature_names"]
    hs, as_ = CURRENT_TEAM_STATS.get(home,{}), CURRENT_TEAM_STATS.get(away,{})
    hr, ar  = TEAM_ROLLING.get(home,{}), TEAM_ROLLING.get(away,{})
    avg_p = (hs.get("pace",83)+as_.get("pace",83))/2
    row = {f: 0 for f in feats}
    row.update({
        "avg_pace": avg_p, "home_pace": hs.get("pace",83), "away_pace": as_.get("pace",83),
        "pace_sum": hs.get("pace",83)+as_.get("pace",83),
        "home_ortg": hs.get("ortg",102), "away_ortg": as_.get("ortg",102),
        "combined_ortg": hs.get("ortg",102)+as_.get("ortg",102),
        "home_drtg": hs.get("drtg",102), "away_drtg": as_.get("drtg",102),
        "combined_drtg": hs.get("drtg",102)+as_.get("drtg",102),
        "home_ts_pct": hs.get("ts_pct",0.555), "away_ts_pct": as_.get("ts_pct",0.555),
        "combined_ts": hs.get("ts_pct",0.555)+as_.get("ts_pct",0.555),
        "pace_x_ortg": avg_p*(hs.get("ortg",102)+as_.get("ortg",102))/200,
        "def_mismatch": abs((hs.get("ortg",102)-as_.get("drtg",102))-(as_.get("ortg",102)-hs.get("drtg",102))),
        "home_rolling_total_5g": hr.get("roll_pts",102),
        "away_rolling_total_5g": ar.get("roll_pts",102),
        "rolling_total_sum_5g": hr.get("roll_pts",102)+ar.get("roll_pts",102),
        "home_back_to_back": int(ctx["home_b2b"]),
        "away_back_to_back": int(ctx["away_b2b"]),
        "both_b2b": int(ctx["home_b2b"] and ctx["away_b2b"]),
        "home_rest_days": ctx["home_rest_days"], "away_rest_days": ctx["away_rest_days"],
        "long_travel": int(ctx["long_travel"]),
        "month": ctx["month"], "is_playoff": int(ctx["month"]>=9),
        "season_game_num": ctx["season_game_num"],
    })
    try:
        X = pd.DataFrame([row])[feats]
        return round(float(model.predict(X)[0]), 1)
    except Exception as e:
        print(f"  [WARN] Totals prediction error: {e}")
        return 160.0


def run_props(home, away, ctx, bundle, posted_lines=None):
    if bundle is None: return []
    models     = bundle["models"]
    thresholds = bundle["thresholds"]
    posted     = posted_lines or {}
    results    = []
    avg_pace = (CURRENT_TEAM_STATS.get(home,{}).get("pace",83) +
                CURRENT_TEAM_STATS.get(away,{}).get("pace",83)) / 2

    for player, pdata in PLAYER_PROPS.items():
        if pdata["team"] not in [home, away]:
            continue
        opp     = away if pdata["team"] == home else home
        opp_def = OPP_DEF_POS.get(opp,{}).get(pdata["pos"],102)
        is_home = int(pdata["team"] == home)
        b2b     = ctx["home_b2b"] if is_home else ctx["away_b2b"]
        rest    = ctx["home_rest_days"] if is_home else ctx["away_rest_days"]
        proj_min= pdata["mpg"] * (0.88 if b2b else 1.0)

        row = {
            "minutes": proj_min, "roll5_minutes": pdata["mpg"],
            "usage": pdata["usage"], "ts_pct": pdata["ts"],
            "opp_drtg_pos": opp_def, "avg_pace": avg_pace,
            "team_pace": CURRENT_TEAM_STATS.get(pdata["team"],{}).get("pace",83),
            "rest_days": rest, "is_home": is_home,
            "roll5_pts": pdata.get("roll5_pts",15), "roll5_reb": pdata.get("roll5_reb",5),
            "roll5_ast": pdata.get("roll5_ast",3),  "roll5_threes": pdata.get("roll5_threes",1),
            "roll5_pra": pdata.get("roll5_pts",15)+pdata.get("roll5_reb",5)+pdata.get("roll5_ast",3),
            "season_game_num": ctx["season_game_num"], "month": ctx["month"],
            "def_adj": 102-opp_def,
            "usage_pace": pdata["usage"]*avg_pace/83.0,
        }

        player_result = {"player": player, "team": pdata["team"],
                         "opp": opp, "pos": pdata["pos"],
                         "proj_min": round(proj_min,1), "b2b": b2b, "props": {}}

        for target in PROP_TARGETS:
            if target not in models: continue
            m     = models[target]
            feats = [f for f in m["features"] if f in row]
            try:
                X    = pd.DataFrame([row])[feats]
                pred = float(m["model"].predict(X)[0])
            except:
                pred = m.get("mean_stat", 10.0)
            thresh = thresholds.get(target, 2.0)
            line   = posted.get(player,{}).get(target)
            edge   = round(pred-line,1) if line else None
            signal = None
            if edge is not None:
                if edge > thresh:  signal = "OVER"
                elif edge < -thresh: signal = "UNDER"
            player_result["props"][target] = {
                "pred": round(pred,1), "line": line, "edge": edge, "signal": signal}

        results.append(player_result)
    return results


def score_confidence(edge, model_type):
    t = {"spread":{"HIGH":5.0,"MED":3.0},"totals":{"HIGH":4.0,"MED":2.0},"props":{"HIGH":3.5,"MED":2.0}}.get(model_type,{"HIGH":5,"MED":3})
    ae = abs(edge) if edge else 0
    if ae >= t["HIGH"]: return "HIGH", 3
    if ae >= t["MED"]:  return "MED",  2
    return "LOW", 1


def collect_best_bets(games_output):
    bets = []
    for g in games_output:
        home, away = g["home"]["name"], g["away"]["name"]
        matchup = f"{away} @ {home}"
        sp = g["spread"]
        if sp.get("edge"):
            conf, stars = score_confidence(sp["edge"], "spread")
            if stars >= 2:
                bets.append({"type":"SPREAD","game":matchup,"play":sp["model_line"],
                              "edge":sp["edge"],"conf":conf,"stars":stars,"tip":g["tip"]})
        tot = g["totals"]
        if tot.get("edge"):
            conf, stars = score_confidence(tot["edge"], "totals")
            if stars >= 2:
                bets.append({"type":"TOTAL","game":matchup,
                              "play":f"{tot['play']} {tot['line']}",
                              "edge":tot["edge"],"conf":conf,"stars":stars,"tip":g["tip"]})
        for pr in g.get("props",[]):
            for pt, pd_data in pr["props"].items():
                if pd_data["signal"] and pd_data["edge"] is not None:
                    conf, stars = score_confidence(pd_data["edge"], "props")
                    if stars >= 2:
                        bets.append({"type":"PROP","game":matchup,
                                     "play":f"{pr['player']} {pt.upper()} {pd_data['signal']} {pd_data['line']}",
                                     "edge":pd_data["edge"],"conf":conf,"stars":stars,"tip":g["tip"]})
    bets.sort(key=lambda b: (-b["stars"], -abs(b["edge"])))
    for i, b in enumerate(bets): b["rank"] = i+1
    return bets[:8]


def run_pipeline(target_date: date, schedule: list, posted_props: dict = None):
    print(f"\n═══ WNBA DAILY PIPELINE — {target_date} ═══\n")
    spread_bundle, totals_bundle, props_bundle = load_models()

    # Load injury adjustments
    injury_adjustments = {}
    injuries_path = "data/raw/injuries_today.csv"
    if INJURIES_AVAILABLE and os.path.exists(injuries_path):
        import pandas as pd
        inj_df = pd.read_csv(injuries_path)
        from scrape_injuries import reallocate_minutes
        injury_adjustments = reallocate_minutes(inj_df, schedule)
        out_count = len(inj_df[inj_df["is_out"]]) if "is_out" in inj_df.columns else 0
        print(f"  Injuries loaded: {out_count} OUT players")

    # Load referee stats
    ref_stats_df = None
    ref_path = "data/raw/ref_stats.csv"
    if REFS_AVAILABLE and os.path.exists(ref_path):
        import pandas as pd
        ref_stats_df = pd.read_csv(ref_path)
        print(f"  Ref stats loaded: {len(ref_stats_df)} officials")

    # Load today's ref assignments
    ref_assignments = {}
    ref_assign_path = "data/raw/ref_assignments_today.csv"
    if os.path.exists(ref_assign_path):
        import pandas as pd
        ra = pd.read_csv(ref_assign_path)
        if "refs" in ra.columns and "home_team" in ra.columns:
            for _, row in ra.iterrows():
                key = f"{row.get('away_team','')}@{row.get('home_team','')}"
                ref_assignments[key] = str(row.get("refs",""))

    posted_props  = posted_props or {}
    games_output  = []

    if not schedule:
        print("  No games scheduled today.")
    
    for game in schedule:
        home = game.get("home","")
        away = game.get("away","")
        tip  = game.get("tip","TBD")
        if not home or not away:
            continue

        print(f"  Processing: {away} @ {home}")
        ctx = build_context(home, away, target_date, game)

        # Add referee crew stats to context
        game_key_ref = f"{away}@{home}"
        refs_str = ref_assignments.get(game_key_ref, "")
        if refs_str and ref_stats_df is not None and REFS_AVAILABLE:
            crew = get_crew_stats(refs_str, ref_stats_df)
            ctx.update({
                "crew_avg_total": crew.get("crew_avg_total", 162.0),
                "crew_total_adj": crew.get("crew_total_adj", 0.0),
                "crew_over_rate": crew.get("crew_over_rate", 0.5),
                "crew_foul_rate": crew.get("crew_foul_rate", 38.0),
                "crew_refs":      refs_str,
            })

        spread_pred   = run_spread(home, away, ctx, spread_bundle)
        posted_spread = game.get("posted_spread")
        spread_edge   = round(spread_pred-(-posted_spread),1) if posted_spread else None
        spread_conf, spread_stars = score_confidence(spread_edge or 0, "spread")

        total_pred  = run_totals(home, away, ctx, totals_bundle)
        posted_total= game.get("posted_total")
        total_edge  = round(total_pred-posted_total,1) if posted_total else None
        total_play  = ("OVER" if total_edge and total_edge>0 else "UNDER") if total_edge else None
        total_conf, total_stars = score_confidence(total_edge or 0, "totals")

        props_out = run_props(home, away, ctx, props_bundle,
                              posted_props.get(f"{away}@{home}",{}))

        flags = []
        if ctx["away_b2b"]:    flags.append(f"B2B ({away[:3].upper()})")
        if ctx["home_b2b"]:    flags.append(f"B2B ({home[:3].upper()})")
        if ctx["long_travel"]: flags.append("Travel")

        def fmt_line(pred, h, a):
            if abs(pred) < 0.5: return "Pick'em"
            return f"{h} -{abs(pred):.1f}" if pred > 0 else f"{a} -{abs(pred):.1f}"

        hs  = CURRENT_TEAM_STATS.get(home,{})
        as_ = CURRENT_TEAM_STATS.get(away,{})

        games_output.append({
            "tip": tip,
            "home": {"name":home,"abbr":home[:3].upper(),"record":game.get("home_record","?-?"),"net_rtg":hs.get("net_rtg",0)},
            "away": {"name":away,"abbr":away[:3].upper(),"record":game.get("away_record","?-?"),"net_rtg":as_.get("net_rtg",0)},
            "spread": {"pred":spread_pred,"model_line":fmt_line(spread_pred,home,away),
                       "posted_line":posted_spread,"edge":spread_edge,
                       "conf":spread_conf,"stars":spread_stars},
            "totals": {"pred":total_pred,"line":posted_total,"edge":total_edge,
                       "play":total_play,"conf":total_conf,"stars":total_stars},
            "props": props_out, "flags": flags,
            "ctx": {k:v for k,v in ctx.items() if not isinstance(v, np.bool_)},
        })

    best_bets = collect_best_bets(games_output)

    # Apply Kelly sizing to best bets
    if KELLY_AVAILABLE and best_bets:
        best_bets = size_all_bets(best_bets, bankroll=1000.0)
        print(f"  Kelly sizing applied: {sum(1 for b in best_bets if b.get('units',0)>0)} bets sized")

    return {
        "date":       str(target_date),
        "generated":  datetime.now().isoformat(),
        "games":      games_output,
        "best_bets":  best_bets,
        "model_stats":{"spread":{"algo":"Ridge v2","cv_mae":9.72,"dir_acc":0.716,"strong_ats":0.815,"n":263},
                       "totals":{"algo":"Random Forest","cv_mae":6.77,"ou_acc":0.542,"strong_ou":0.554,"n":939},
                       "props": {"algo":"Ridge","cv_mae":6.00,"hit_rate":0.721,"strong_hr":0.754,"n":1337}},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out",  default=None)
    args = parser.parse_args()

    target   = datetime.strptime(args.date, "%Y-%m-%d").date()
    schedule = fetch_todays_schedule(target)

    result   = run_pipeline(target, schedule)
    out_path = args.out or os.path.join(OUTPUT_DIR, f"predictions_{target}.json")

    def convert(o):
        if isinstance(o, (np.integer,)):  return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, (np.bool_,)):    return bool(o)
        raise TypeError(f"Not serializable: {type(o)}")

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=convert)

    print(f"\n✅ Predictions written → {out_path}")
    print(f"   Games: {len(result['games'])} | Best bets: {len(result['best_bets'])}")
    for b in result["best_bets"][:3]:
        e = f"+{b['edge']}" if b['edge'] > 0 else str(b['edge'])
        print(f"  #{b['rank']} [{b['type']}] {b['play']}  {e} pts  {'★'*b['stars']}")
