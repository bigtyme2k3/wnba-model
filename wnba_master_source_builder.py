from __future__ import annotations
import argparse, csv, importlib.util, json, os
from datetime import date, datetime, timedelta, timezone
from typing import Any

MASTER_DIR = "data/master"
DASH_DIR = "data/dashboard"
RAW_DIR = "data/raw"
CONFIG = "config/source_registry.json"


def load_json(path: str, default: Any):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def read_csv(path: str):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return list(csv.DictReader(f))
    except Exception:
        pass
    return []


def first_csv(paths: list[str]):
    for p in paths:
        rows = read_csv(p)
        if rows:
            return rows, p
    return [], None


def team_name(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("name") or v.get("abbreviation") or v.get("abbr") or "")
    return str(v or "")


def norm_team(row: dict, side: str):
    keys = [f"{side}_team", f"{side}", f"{side}_name", "visitor_team" if side == "away" else "home_team"]
    for k in keys:
        v = row.get(k)
        if v:
            return team_name(v)
    return ""


def norm_score(row: dict, side: str):
    keys = [f"{side}_score", f"score_{side}", "visitor_score" if side == "away" else "home_score"]
    for k in keys:
        if row.get(k) not in (None, ""):
            return row.get(k)
    if side == "away" and isinstance(row.get("away"), dict):
        return row["away"].get("score")
    if side == "home" and isinstance(row.get("home"), dict):
        return row["home"].get("score")
    return ""


def game_key(away: str, home: str, game_date: str):
    return f"{game_date}|{away.strip().lower()}|{home.strip().lower()}"


def display_game(away: str, home: str):
    return f"{away} @ {home}" if away and home else ""


def parse_game_text(g: str):
    if " @ " in g:
        return g.split(" @ ", 1)
    if " at " in g:
        return g.split(" at ", 1)
    if " vs " in g:
        home, away = g.split(" vs ", 1)
        return away, home
    return "", ""


def clean_num(v):
    try:
        if v in (None, ""):
            return ""
        f = float(v)
        return int(f) if f.is_integer() else round(f, 2)
    except Exception:
        return v or ""


def prediction_games(target: str):
    pred = load_json(f"predictions/predictions_{target}.json", {})
    games = []
    for g in pred.get("games", []):
        away = team_name(g.get("away")) or g.get("away_team", "")
        home = team_name(g.get("home")) or g.get("home_team", "")
        if not away or not home:
            continue
        tip = g.get("tip") or g.get("start_time") or ""
        spread = g.get("spread", {}) if isinstance(g.get("spread"), dict) else {}
        totals = g.get("totals", {}) if isinstance(g.get("totals"), dict) else {}
        games.append({
            "game_id": g.get("game_id") or game_key(away, home, target),
            "game_date": target,
            "bucket": "today",
            "game": display_game(away, home),
            "away_team": away,
            "home_team": home,
            "away_score": "",
            "home_score": "",
            "status": "Pregame",
            "start_time": tip,
            "spread": clean_num(spread.get("posted_line") if spread else g.get("spread_home")),
            "model_spread": spread.get("model_line") if spread else "",
            "total": clean_num(totals.get("line") if totals else g.get("total")),
            "model_total": clean_num(totals.get("pred") if totals else ""),
            "total_play": totals.get("play") if totals else "",
            "source": "predictions_schedule",
        })
    return dedupe_games(games, target)


def games_from_scores(target: str, bucket: str = "yesterday"):
    y = str(datetime.strptime(target, "%Y-%m-%d").date() - timedelta(days=1)) if len(target) == 10 else ""
    paths = [f"{RAW_DIR}/scores_{y}.csv"] if bucket == "yesterday" else [f"{RAW_DIR}/scores_{target}.csv", f"{RAW_DIR}/scores_today.csv"]
    rows, src = first_csv(paths)
    out = []
    for r in rows:
        gd = r.get("game_date") or r.get("date") or (target if bucket == "today" else y)
        away = norm_team(r, "away")
        home = norm_team(r, "home")
        if (not away or not home) and r.get("game"):
            away, home = parse_game_text(str(r.get("game")))
        if not away or not home:
            continue
        away_score = norm_score(r, "away")
        home_score = norm_score(r, "home")
        out.append({
            "game_id": r.get("game_id") or r.get("event_id") or game_key(away, home, gd),
            "game_date": gd,
            "bucket": bucket,
            "game": display_game(away, home),
            "away_team": away,
            "home_team": home,
            "away_score": away_score,
            "home_score": home_score,
            "status": r.get("status") or r.get("game_status") or ("Final" if away_score or home_score else "Pregame"),
            "start_time": r.get("commence_time") or r.get("start_time") or r.get("tip") or r.get("time") or "",
            "spread": r.get("spread") or r.get("spread_home") or r.get("posted_spread") or "",
            "total": r.get("total") or r.get("posted_total") or "",
            "source": src or "scores_csv",
        })
    return dedupe_games(out, y if bucket == "yesterday" else target)


def odds_games(target: str):
    rows, src = first_csv([f"{RAW_DIR}/odds_{target}.csv", f"{RAW_DIR}/odds_today.csv"])
    latest = {}
    for r in rows:
        away = norm_team(r, "away")
        home = norm_team(r, "home")
        if not away or not home:
            continue
        gd = target
        key = game_key(away, home, gd)
        latest[key] = {
            "game_id": r.get("game_id") or key,
            "game_date": gd,
            "bucket": "today",
            "game": display_game(away, home),
            "away_team": away,
            "home_team": home,
            "away_score": "",
            "home_score": "",
            "status": "Pregame",
            "start_time": r.get("commence_time") or "",
            "spread": clean_num(r.get("spread_home")),
            "total": clean_num(r.get("total")),
            "moneyline_home": clean_num(r.get("ml_home")),
            "moneyline_away": clean_num(r.get("ml_away")),
            "source": src or "odds_csv",
        }
    return list(latest.values())


def consensus_games(target: str):
    sb = load_json(f"{DASH_DIR}/wnba_sportsbook_consensus.json", {})
    latest = {}
    for m in sb.get("markets", []):
        away, home = parse_game_text(str(m.get("game") or ""))
        if not away or not home:
            continue
        key = game_key(away, home, target)
        latest[key] = {
            "game_id": key,
            "game_date": target,
            "bucket": "today",
            "game": display_game(away, home),
            "away_team": away,
            "home_team": home,
            "away_score": "",
            "home_score": "",
            "status": "Pregame",
            "start_time": "",
            "spread": "",
            "total": "",
            "source": "sportsbook_consensus",
        }
    return list(latest.values())


def dedupe_games(games: list[dict], target: str):
    merged = {}
    for g in games:
        away = g.get("away_team", "")
        home = g.get("home_team", "")
        if not away or not home:
            continue
        key = game_key(away, home, target)
        if key not in merged:
            merged[key] = dict(g)
        else:
            for k, v in g.items():
                if merged[key].get(k) in (None, "", "Pregame") and v not in (None, ""):
                    merged[key][k] = v
    return list(merged.values())


def attach_market_data(schedule_games: list[dict], extras: list[dict], target: str):
    # Attach odds/consensus only to games that are already in the official daily schedule.
    # Do not add extra games here; old line files often contain stale games.
    by_key = {game_key(g["away_team"], g["home_team"], target): g for g in schedule_games if g.get("away_team") and g.get("home_team")}
    for g in extras:
        if not g.get("away_team") or not g.get("home_team"):
            continue
        key = game_key(g["away_team"], g["home_team"], target)
        if key not in by_key:
            continue
        base = by_key[key]
        for k, v in g.items():
            if base.get(k) in (None, "", "Pregame") and v not in (None, ""):
                base[k] = v
    return list(by_key.values())


def merge_today_games(target: str):
    schedule = prediction_games(target)
    if schedule:
        return attach_market_data(schedule, odds_games(target) + consensus_games(target), target)
    # Fallback only when no schedule exists.
    fallback = odds_games(target) or consensus_games(target)
    return dedupe_games(fallback, target)


def player_stats_from_live():
    players = load_json(f"{RAW_DIR}/wnba_players_live.json", {})
    out = []
    if isinstance(players, dict):
        for name, p in players.items():
            out.append({
                "player": p.get("player") or name,
                "team": p.get("team", ""),
                "pos": p.get("pos", ""),
                "gp": p.get("gp", 0),
                "mpg": p.get("mpg", 0),
                "ppg": p.get("ppg", 0),
                "rpg": p.get("reb", 0),
                "apg": p.get("ast", 0),
                "usage": p.get("usage", 0),
                "roll5_pts": p.get("roll5_pts", p.get("ppg", 0)),
                "roll5_mpg": p.get("roll5_mpg", p.get("mpg", 0)),
                "source": p.get("source", "wnba_players_live"),
            })
    return out


def props_from_consensus():
    sb = load_json(f"{DASH_DIR}/wnba_sportsbook_consensus.json", {})
    return [{
        "player": m.get("player", ""), "game": m.get("game", ""), "stat": m.get("stat", ""),
        "line": m.get("consensus_line"), "best_over_book": m.get("best_over_book"),
        "best_over_price": m.get("best_over_price"), "best_under_book": m.get("best_under_book"),
        "best_under_price": m.get("best_under_price"), "book_count": m.get("book_count", 0),
        "books": m.get("books", []), "source": "sportsbook_consensus",
    } for m in sb.get("markets", [])]


def source_status(name: str, status: str, rows: int = 0, detail: str = ""):
    return {"source": name, "status": status, "rows": rows, "detail": detail, "checked_at_utc": datetime.now(timezone.utc).isoformat()}


def optional_package_status(pkg: str):
    return "installed" if importlib.util.find_spec(pkg) else "not_installed"


def build(target: str):
    registry = load_json(CONFIG, {})
    today_games = merge_today_games(target)
    yesterday_games = games_from_scores(target, "yesterday")
    games = today_games + yesterday_games
    players = player_stats_from_live()
    props = props_from_consensus()
    odds = load_json(f"{DASH_DIR}/wnba_sportsbook_consensus.json", {})
    stats_quality = load_json(f"{DASH_DIR}/wnba_stats_quality.json", {})
    source_health = load_json(f"{DASH_DIR}/wnba_source_health.json", {})
    health = [
        source_status("sportsdataverse", "optional_package_" + optional_package_status("sportsdataverse"), len(today_games), "Schedule source planned; predictions schedule is current source of truth."),
        source_status("nba_api", "optional_package_" + optional_package_status("nba_api"), len(players), "Advanced stats falls back to owned boxscore warehouse."),
        source_status("boxscore_warehouse", "ok" if players else "missing", len(players), "wnba_players_live.json generated from official stats or boxscore fallback."),
        source_status("odds_pipeline", "ok" if props else "missing", len(props), "sportsbook consensus markets normalized into master props."),
        source_status("the_odds_api", "backup_only", 0, "Do not use as primary because credits burn quickly."),
        source_status("litellm", "optional_package_" + optional_package_status("litellm"), 0, "AI gateway planned; not required for current dashboard."),
        source_status("optuna", "optional_package_" + optional_package_status("optuna"), 0, "Model tuning planned; not required for current dashboard."),
    ]
    master = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target, "schema_version": "master-v3",
        "registry": registry,
        "summary": {"games": len(games), "today_games": len(today_games), "yesterday_games": len(yesterday_games), "players": len(players), "props": len(props), "sportsbook_markets": odds.get("summary", {}).get("markets", 0), "books": odds.get("summary", {}).get("books_detected", [])},
        "games": games, "players": players, "props": props, "odds_summary": odds.get("summary", {}), "stats_quality": stats_quality, "source_health": source_health, "source_matrix": health,
    }
    os.makedirs(MASTER_DIR, exist_ok=True); os.makedirs(DASH_DIR, exist_ok=True)
    for p in [f"{MASTER_DIR}/wnba_master.json", f"{DASH_DIR}/wnba_master.json"]:
        json.dump(master, open(p, "w", encoding="utf-8"), indent=2)
    json.dump({"generated_at_utc": master["generated_at_utc"], "target_date": target, "summary": master["summary"], "sources": health}, open(f"{DASH_DIR}/wnba_master_source_health.json", "w", encoding="utf-8"), indent=2)
    print("Master source built:", master["summary"])
    return master


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--date", default=str(date.today())); args = ap.parse_args(); build(args.date)
if __name__ == "__main__": main()
