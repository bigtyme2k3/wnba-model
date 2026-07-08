from __future__ import annotations
import argparse, csv, glob, importlib.util, json, os
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


def norm_team(row: dict, side: str):
    keys = [
        f"{side}_team", f"{side}", f"{side}_name",
        "away" if side == "away" else "home",
        "visitor_team" if side == "away" else "home_team",
        "team" if side == "home" else "opponent",
    ]
    for k in keys:
        v = row.get(k)
        if v:
            if isinstance(v, dict):
                return v.get("name") or v.get("abbreviation") or ""
            return str(v)
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


def games_from_scores(target: str):
    y = str(datetime.strptime(target, "%Y-%m-%d").date() - timedelta(days=1)) if len(target) == 10 else ""
    today_rows, today_src = first_csv([f"{RAW_DIR}/scores_{target}.csv", f"{RAW_DIR}/scores_today.csv"])
    y_rows, y_src = first_csv([f"{RAW_DIR}/scores_{y}.csv"])
    out = []
    for bucket, rows, src in [("today", today_rows, today_src), ("yesterday", y_rows, y_src)]:
        for r in rows:
            gd = r.get("game_date") or r.get("date") or (target if bucket == "today" else y)
            away = norm_team(r, "away")
            home = norm_team(r, "home")
            away_score = norm_score(r, "away")
            home_score = norm_score(r, "home")
            if not away and not home and r.get("game"):
                game = str(r.get("game"))
                if " @ " in game:
                    away, home = game.split(" @ ", 1)
                elif " vs " in game:
                    home, away = game.split(" vs ", 1)
            out.append({
                "game_id": r.get("game_id") or r.get("event_id") or game_key(away, home, gd),
                "game_date": gd,
                "bucket": bucket,
                "away_team": away,
                "home_team": home,
                "away_score": away_score,
                "home_score": home_score,
                "status": r.get("status") or r.get("game_status") or ("Final" if away_score or home_score else "Pregame"),
                "start_time": r.get("commence_time") or r.get("start_time") or r.get("tip") or r.get("time") or "",
                "spread": r.get("spread") or r.get("spread_home") or "",
                "total": r.get("total") or "",
                "source": src or "scores_csv",
            })
    return out


def games_from_consensus(target: str, existing: list[dict]):
    sb = load_json(f"{DASH_DIR}/wnba_sportsbook_consensus.json", {})
    seen = {g.get("game_id") for g in existing}
    out = []
    for m in sb.get("markets", []):
        g = m.get("game") or ""
        if not g:
            continue
        away = home = ""
        if " @ " in g:
            away, home = g.split(" @ ", 1)
        elif " vs " in g:
            home, away = g.split(" vs ", 1)
        gid = game_key(away, home, target)
        if gid in seen:
            continue
        seen.add(gid)
        out.append({
            "game_id": gid,
            "game_date": target,
            "bucket": "today",
            "away_team": away,
            "home_team": home,
            "away_score": "",
            "home_score": "",
            "status": "Pregame",
            "start_time": "",
            "spread": "",
            "total": "",
            "source": "sportsbook_consensus",
        })
    return out


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
    out = []
    for m in sb.get("markets", []):
        out.append({
            "player": m.get("player", ""),
            "game": m.get("game", ""),
            "stat": m.get("stat", ""),
            "line": m.get("consensus_line"),
            "best_over_book": m.get("best_over_book"),
            "best_over_price": m.get("best_over_price"),
            "best_under_book": m.get("best_under_book"),
            "best_under_price": m.get("best_under_price"),
            "book_count": m.get("book_count", 0),
            "books": m.get("books", []),
            "source": "sportsbook_consensus",
        })
    return out


def source_status(name: str, status: str, rows: int = 0, detail: str = ""):
    return {"source": name, "status": status, "rows": rows, "detail": detail, "checked_at_utc": datetime.now(timezone.utc).isoformat()}


def optional_package_status(pkg: str):
    return "installed" if importlib.util.find_spec(pkg) else "not_installed"


def build(target: str):
    registry = load_json(CONFIG, {})
    games = games_from_scores(target)
    games += games_from_consensus(target, games)
    players = player_stats_from_live()
    props = props_from_consensus()
    odds = load_json(f"{DASH_DIR}/wnba_sportsbook_consensus.json", {})
    stats_quality = load_json(f"{DASH_DIR}/wnba_stats_quality.json", {})
    source_health = load_json(f"{DASH_DIR}/wnba_source_health.json", {})

    health = [
        source_status("sportsdataverse", "optional_package_" + optional_package_status("sportsdataverse"), len(games), "Schedule/game data falls back to scores CSV and consensus odds until importer is enabled."),
        source_status("nba_api", "optional_package_" + optional_package_status("nba_api"), len(players), "Advanced stats falls back to owned boxscore warehouse."),
        source_status("boxscore_warehouse", "ok" if players else "missing", len(players), "wnba_players_live.json generated from official stats or boxscore fallback."),
        source_status("odds_pipeline", "ok" if props else "missing", len(props), "sportsbook consensus markets normalized into master props."),
        source_status("the_odds_api", "backup_only", 0, "Do not use as primary because credits burn quickly."),
        source_status("litellm", "optional_package_" + optional_package_status("litellm"), 0, "AI gateway planned; not required for current dashboard."),
        source_status("optuna", "optional_package_" + optional_package_status("optuna"), 0, "Model tuning planned; not required for current dashboard."),
    ]

    master = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "schema_version": "master-v1",
        "registry": registry,
        "summary": {
            "games": len(games),
            "today_games": sum(1 for g in games if g.get("bucket") == "today"),
            "yesterday_games": sum(1 for g in games if g.get("bucket") == "yesterday"),
            "players": len(players),
            "props": len(props),
            "sportsbook_markets": odds.get("summary", {}).get("markets", 0),
            "books": odds.get("summary", {}).get("books_detected", []),
        },
        "games": games,
        "players": players,
        "props": props,
        "odds_summary": odds.get("summary", {}),
        "stats_quality": stats_quality,
        "source_health": source_health,
        "source_matrix": health,
    }
    os.makedirs(MASTER_DIR, exist_ok=True)
    os.makedirs(DASH_DIR, exist_ok=True)
    for p in [f"{MASTER_DIR}/wnba_master.json", f"{DASH_DIR}/wnba_master.json"]:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(master, f, indent=2)
    with open(f"{DASH_DIR}/wnba_master_source_health.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at_utc": master["generated_at_utc"], "target_date": target, "summary": master["summary"], "sources": health}, f, indent=2)
    print("Master source built:", master["summary"])
    return master


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
