"""
postprocess_predictions.py
--------------------------
Patches today's predictions JSON after daily_runner.py by merging market odds,
embedding player prop rows, rebuilding boards/best bets, adding EV/Kelly ranking,
line-shopping recommendations, and model tracking metadata.
"""

import argparse, glob, json, os
from datetime import datetime, timezone
import pandas as pd

from betting_engine import enrich_bet, rank_bets, tracking_summary

PREDICTIONS_DIR = "predictions"
RAW_DIR = "data/raw"
CONF_THRESHOLDS = {"spread": {"HIGH": 5.0, "MED": 3.0}, "totals": {"HIGH": 4.0, "MED": 2.0}, "props": {"HIGH": 2.0, "MED": 1.0}}
ALIASES = {"golden state valkyries": "golden state valkyries", "gs valkyries": "golden state valkyries", "gsv": "golden state valkyries", "portland fire": "portland fire", "pdx fire": "portland fire", "toronto tempo": "toronto tempo"}


def norm_team(name):
    name = str(name or "").strip().lower().replace("  ", " ")
    return ALIASES.get(name, name)


def norm_txt(value):
    return str(value or "").strip().lower().replace("’", "'")


def to_float(value, default=None):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def clean_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def maybe_json(value, default):
    if value is None or isinstance(value, list):
        return value if isinstance(value, list) else default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else default
    except Exception:
        return default


def score_confidence(edge, model_type):
    t = CONF_THRESHOLDS.get(model_type, {"HIGH": 5.0, "MED": 3.0})
    ae = abs(edge) if edge is not None else 0.0
    if ae >= t["HIGH"]:
        return "HIGH", 3
    if ae >= t["MED"]:
        return "MED", 2
    return "LOW", 1


def fmt_spread_line(team, line):
    if line is None:
        return team
    if abs(line) < 0.05:
        return f"{team} PK"
    return f"{team} {'+' if line > 0 else ''}{line:.1f}"


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
    return load_csv([os.path.join(RAW_DIR, f"odds_{target_date}.csv"), os.path.join(RAW_DIR, "odds_today.csv")], "odds")


def load_props(target_date):
    return load_csv([os.path.join(RAW_DIR, f"props_raw_{target_date}.csv"), os.path.join(RAW_DIR, "props_today.csv")], "props")


def load_player_points(target_date):
    return load_csv([os.path.join(RAW_DIR, f"player_points_{target_date}.csv"), os.path.join(RAW_DIR, "player_points_today.csv")], "player points")


def load_line_shopping(target_date):
    return load_csv([os.path.join(RAW_DIR, f"line_shopping_best_{target_date}.csv"), os.path.join(RAW_DIR, "line_shopping_best_today.csv")], "line shopping")


def find_odds_row(odds_df, home, away):
    if odds_df.empty:
        return None
    h, a = norm_team(home), norm_team(away)
    for _, row in odds_df.iterrows():
        if norm_team(row.get("home_team")) == h and norm_team(row.get("away_team")) == a:
            return row
    return None


def find_prop_price(props_df, player, stat, line, signal):
    if props_df.empty or not player or not stat or not signal:
        return -110
    stat_key = str(stat).upper().replace("3PM", "THREES").lower()
    df = props_df.copy()
    if "player" in df.columns:
        df = df[df["player"].astype(str).str.lower().eq(str(player).lower())]
    if "stat" in df.columns:
        wanted = {"pts":"pts","reb":"reb","ast":"ast","threes":"threes","pra":"pra"}.get(stat_key, stat_key)
        df = df[df["stat"].astype(str).str.lower().eq(wanted)]
    if df.empty:
        return -110
    row = df.iloc[0]
    return to_float(row.get("over_price" if signal == "OVER" else "under_price"), -110)


def best_line(line_df, market_type, game=None, side=None, player=None, stat=None, team_hint=None):
    if line_df.empty:
        return {}
    df = line_df[line_df["market_type"].astype(str).str.upper().eq(market_type.upper())].copy()
    if game and "game" in df.columns:
        df = df[df["game"].astype(str).str.lower().eq(str(game).lower())]
    if side and "side" in df.columns:
        df = df[df["side"].astype(str).str.upper().eq(str(side).upper())]
    if player and "player" in df.columns:
        df = df[df["player"].astype(str).str.lower().eq(str(player).lower())]
    if stat and "stat" in df.columns:
        df = df[df["stat"].astype(str).str.upper().eq(str(stat).upper())]
    if team_hint and market_type.upper() == "SPREAD" and "team" in df.columns:
        hint = norm_txt(team_hint)
        df = df[df["team"].astype(str).apply(lambda x: norm_txt(x) in hint or hint in norm_txt(x))]
    if df.empty:
        return {}
    row = df.iloc[0]
    return {"best_book": clean_value(row.get("book_key")) or clean_value(row.get("book_title")), "best_book_title": clean_value(row.get("book_title")) or clean_value(row.get("book_key")), "best_line": to_float(row.get("line")), "best_odds": to_float(row.get("odds")), "available_books": int(to_float(row.get("available_books"), 1) or 1)}


def attach_best(payload, best):
    if best:
        payload.update(best)
        if best.get("best_odds") is not None:
            payload["odds"] = best.get("best_odds")
        if best.get("best_line") is not None:
            payload["best_market_line"] = best.get("best_line")
    return payload


def build_spread_board(games, line_df):
    board = []
    for game in games:
        sp = game.get("spread", {})
        matchup = f"{game['away']['name']} @ {game['home']['name']}"
        status = "WAIT" if sp.get("posted_line") is None else "BET" if (sp.get("stars") or 1) >= 2 else "WATCH"
        play = sp.get("play") or sp.get("model_line")
        b = {"type":"SPREAD", "game": matchup, "tip": game.get("tip"), "market_line": sp.get("posted_line"), "model_line": sp.get("model_line"), "play": play, "edge": sp.get("edge_abs"), "conf": sp.get("conf", "LOW"), "stars": sp.get("stars", 1), "status": status, "books": game.get("market", {}).get("books", 0), "odds": -110}
        b = attach_best(b, best_line(line_df, "SPREAD", game=matchup, team_hint=play))
        board.append(enrich_bet(b, "SPREAD"))
    board.sort(key=lambda x: (x.get("status") != "BET", -float(x.get("ev", 0) or 0), -(x.get("edge") or 0)))
    return board


def build_player_points_board(points_df, props_df, line_df):
    if points_df.empty:
        return []
    board = []
    for _, row in points_df.iterrows():
        edge = to_float(row.get("edge"))
        conf = str(clean_value(row.get("conf")) or "LOW").upper()
        signal = clean_value(row.get("signal"))
        signal = str(signal).upper() if signal is not None else None
        conf_calc, stars = score_confidence(edge, "props")
        if conf not in {"HIGH", "MED", "LOW"}:
            conf = conf_calc
        stat = clean_value(row.get("stat")) or "PTS"
        line = to_float(row.get("line"))
        odds = find_prop_price(props_df, row.get("player"), stat, line, signal)
        payload = {"type":"PROP", "player": clean_value(row.get("player")) or "", "team": clean_value(row.get("team")) or "", "opp": clean_value(row.get("opp")) or "", "pos": clean_value(row.get("pos")) or "", "stat": stat, "season_avg": to_float(row.get("season_avg")), "projection": to_float(row.get("pred")), "pred": to_float(row.get("pred")), "low": to_float(row.get("low")), "high": to_float(row.get("high")), "range": clean_value(row.get("range")) or "", "line": line, "edge": edge, "signal": signal, "conf": conf, "stars": {"HIGH":3,"MED":2,"LOW":1}.get(conf, stars), "odds": odds, "reasoning": clean_value(row.get("reasoning")) or "", "game": clean_value(row.get("game")) or "", "last5_vals": maybe_json(row.get("last5_vals"), []), "last5_opps": maybe_json(row.get("last5_opps"), []), "last5_hit": to_float(row.get("last5_hit"), 0), "last10_hit": to_float(row.get("last10_hit"), 0), "h2h_last5": maybe_json(row.get("h2h_last5"), []), "opp_rank": int(to_float(row.get("opp_rank"), 8) or 8), "injury_status": clean_value(row.get("injury_status")) or "ACTIVE", "market_status": clean_value(row.get("market_status")) or "ACTIVE MARKET"}
        payload = attach_best(payload, best_line(line_df, "PROP", side=signal, player=payload["player"], stat=stat))
        board.append(enrich_bet(payload, "PROP"))
    board.sort(key=lambda x: (-x.get("stars", 1), -float(x.get("ev", 0) or 0), -abs(x.get("edge") or 0), x.get("player", "")))
    return board


def rebuild_best_bets(games, player_points, line_df):
    bets = []
    for game in games:
        matchup = f"{game['away']['name']} @ {game['home']['name']}"
        tip = game.get("tip")
        sp = game.get("spread", {})
        if sp.get("edge") is not None and (sp.get("stars") or 1) >= 2:
            b = {"type":"SPREAD", "game":matchup, "play":sp.get("play") or sp.get("model_line"), "edge":sp.get("edge_abs", abs(sp.get("edge", 0))), "edge_abs":sp.get("edge_abs", abs(sp.get("edge", 0))), "conf":sp.get("conf", "LOW"), "stars":sp.get("stars", 1), "tip":tip, "market_line":sp.get("posted_line"), "model_line":sp.get("model_line"), "odds":-110, "verdict":"BET"}
            bets.append(attach_best(b, best_line(line_df, "SPREAD", game=matchup, team_hint=b["play"])))
        tot = game.get("totals", {})
        if tot.get("edge") is not None and (tot.get("stars") or 1) >= 2:
            side = tot.get("play")
            b = {"type":"TOTAL", "game":matchup, "play":f"{side} {tot.get('line')}", "edge":tot.get("edge"), "edge_abs":abs(tot.get("edge", 0)), "conf":tot.get("conf", "LOW"), "stars":tot.get("stars", 1), "tip":tip, "market_line":tot.get("line"), "model_line":tot.get("pred"), "odds":-110, "verdict":"BET"}
            bets.append(attach_best(b, best_line(line_df, "TOTAL", game=matchup, side=side)))
    for p in player_points:
        if p.get("signal") and p.get("line") is not None and (p.get("stars") or 1) >= 2:
            b = {"type":"PROP", "game":p.get("game"), "play":f"{p.get('player')} {p.get('stat')} {p.get('signal')} {p.get('line')}", "edge":p.get("edge"), "edge_abs":abs(p.get("edge") or 0), "conf":p.get("conf"), "stars":p.get("stars"), "tip":None, "market_line":p.get("line"), "model_line":p.get("pred"), "odds":p.get("best_odds", p.get("odds", -110)), "best_book":p.get("best_book"), "best_book_title":p.get("best_book_title"), "best_line":p.get("best_line"), "best_odds":p.get("best_odds"), "available_books":p.get("available_books"), "verdict":"BET"}
            bets.append(b)
    return rank_bets(bets, limit=12)


def compact_line_board(line_df):
    if line_df.empty:
        return []
    keep = ["market_type", "game", "player", "stat", "side", "book_key", "book_title", "line", "odds", "available_books"]
    rows = []
    for _, r in line_df.head(120).iterrows():
        rows.append({k: clean_value(r.get(k)) for k in keep if k in line_df.columns})
    return rows


def patch_predictions(target_date):
    path = prediction_path(target_date)
    with open(path) as f:
        data = json.load(f)
    odds_df, props_df, points_df, line_df = load_odds(target_date), load_props(target_date), load_player_points(target_date), load_line_shopping(target_date)
    spreads_found = totals_found = 0

    for game in data.get("games", []):
        home, away = game.get("home", {}).get("name"), game.get("away", {}).get("name")
        odds_row = find_odds_row(odds_df, home, away)
        if odds_row is not None:
            posted_spread, posted_total = to_float(odds_row.get("spread_home")), to_float(odds_row.get("total"))
            game["market"] = {"source": odds_row.get("source", "the-odds-api"), "books": int(odds_row.get("num_books", 0) or 0), "scraped_at": str(odds_row.get("scraped_at", ""))}
        else:
            posted_spread = posted_total = None
            game["market"] = {"source": None, "books": 0, "scraped_at": None}
        spread, model_margin = game.setdefault("spread", {}), to_float(game.setdefault("spread", {}).get("pred"))
        if posted_spread is not None and model_margin is not None:
            home_edge = round(model_margin + posted_spread, 1)
            bet_home = home_edge >= 0
            play_team, play_line = (home, posted_spread) if bet_home else (away, -posted_spread)
            conf, stars = score_confidence(abs(home_edge), "spread")
            spread.update({"posted_line": posted_spread, "edge": home_edge, "edge_abs": round(abs(home_edge), 1), "play": fmt_spread_line(play_team, play_line), "conf": conf, "stars": stars})
            spreads_found += 1
        else:
            spread.update({"posted_line": posted_spread, "edge": None, "edge_abs": None})
        totals, model_total = game.setdefault("totals", {}), to_float(game.setdefault("totals", {}).get("pred"))
        if posted_total is not None and model_total is not None:
            edge = round(model_total - posted_total, 1)
            conf, stars = score_confidence(edge, "totals")
            totals.update({"line": posted_total, "edge": edge, "play": "OVER" if edge > 0 else "UNDER", "conf": conf, "stars": stars})
            totals_found += 1
        elif totals.get("line") is None:
            totals.update({"edge": None, "play": None})

    player_points = build_player_points_board(points_df, props_df, line_df)
    data["props"] = player_points
    data["player_points"] = player_points
    data["spread_board"] = build_spread_board(data.get("games", []), line_df)
    data["props_board"] = player_points
    data["line_shopping"] = compact_line_board(line_df)
    data["best_bets"] = rebuild_best_bets(data.get("games", []), player_points, line_df)
    data["tracking"] = tracking_summary()
    data["model_tracking"] = data["tracking"]
    data["data_health"] = {"odds":"loaded" if not odds_df.empty else "missing", "props":"loaded" if not props_df.empty else "missing", "line_shopping":"loaded" if not line_df.empty else "missing", "player_points":"loaded" if not points_df.empty else "missing", "spreads_found":spreads_found, "totals_found":totals_found, "props_found":len(player_points), "player_points_found":len(player_points), "line_shopping_rows":len(line_df), "games":len(data.get("games", [])), "actionable_bets":len([b for b in data.get("best_bets", []) if b.get("grade") in {"A","B"}]), "high_bets":len([b for b in data.get("best_bets", []) if b.get("stars") == 3]), "last_updated_utc":datetime.now(timezone.utc).isoformat()}
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Patched predictions: {path}")
    print(f"  Player points: {len(player_points)} rows")
    print(f"  Line shopping: {len(line_df)} rows")
    print(f"  Best bets ranked: {len(data['best_bets'])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    print(f"\n═══ POSTPROCESS PREDICTIONS — {args.date} ═══\n")
    patch_predictions(args.date)
    print("✅ Postprocess complete.")


if __name__ == "__main__":
    main()
