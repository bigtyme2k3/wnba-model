"""
wnba_data_warehouse.py
----------------------
Normalizes multi-source WNBA data into one model-ready warehouse layer.

Primary stats source: sportsdataverse/wehoop (ESPN upstream).
Supplemental source: sports-skills.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List

RAW_WNBA = "data/wnba"
RAW_DIR = "data/raw"
PRED_DIR = "predictions"
OUT_DIR = "data/warehouse"
DASH_DIR = "data/dashboard"


def load_json(path: str, default: Any = None) -> Any:
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def csv_count(path: str) -> int:
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except Exception:
        return 0


def as_list(obj: Any) -> List[Any]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ["games", "events", "scoreboard", "data", "items", "injuries", "standings", "futures"]:
            val = obj.get(key)
            if isinstance(val, list):
                return val
        return [obj] if obj else []
    return []


def first(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in [None, ""]:
            return d.get(k)
    return default


def norm_team(value: Any) -> str:
    v = str(value or "").strip()
    return {
        "GSV": "Golden State Valkyries", "GS": "Golden State Valkyries", "GOL": "Golden State Valkyries",
        "WAS": "Washington Mystics", "MIN": "Minnesota Lynx", "CON": "Connecticut Sun",
        "SEA": "Seattle Storm", "LAS": "Los Angeles Sparks", "LOS": "Los Angeles Sparks",
        "ATL": "Atlanta Dream", "CHI": "Chicago Sky", "DAL": "Dallas Wings", "IND": "Indiana Fever",
        "NYL": "New York Liberty", "PHO": "Phoenix Mercury", "PHX": "Phoenix Mercury", "LVA": "Las Vegas Aces",
        "TOR": "Toronto Tempo", "POR": "Portland Fire"
    }.get(v.upper(), v)


def normalize_scores(scores: Any, target: str) -> List[Dict[str, Any]]:
    games = []
    for g in as_list(scores):
        if not isinstance(g, dict):
            continue
        home = first(g, ["home_team", "home", "homeTeam", "home_name", "homeName"])
        away = first(g, ["away_team", "away", "awayTeam", "away_name", "awayName"])
        if isinstance(home, dict): home = first(home, ["name", "displayName", "abbreviation", "abbr"])
        if isinstance(away, dict): away = first(away, ["name", "displayName", "abbreviation", "abbr"])
        home, away = norm_team(home), norm_team(away)
        if not home or not away:
            continue
        games.append({
            "date": first(g, ["date", "game_date", "commence_time", "start_time"], target),
            "game": f"{away} @ {home}", "home_team": home, "away_team": away,
            "home_score": first(g, ["home_score", "homeScore", "home_points", "homePoints"]),
            "away_score": first(g, ["away_score", "awayScore", "away_points", "awayPoints"]),
            "status": first(g, ["status", "game_status", "state", "phase"], "scheduled"),
            "source": "sports-skills", "raw_keys": sorted(list(g.keys()))[:25],
        })
    return games


def normalize_injuries(injuries: Any) -> List[Dict[str, Any]]:
    rows = []
    for r in as_list(injuries):
        if not isinstance(r, dict): continue
        player = first(r, ["player", "player_name", "name", "athlete"])
        if isinstance(player, dict): player = first(player, ["name", "displayName", "fullName"])
        if not player: continue
        rows.append({"player": str(player), "team": norm_team(first(r, ["team", "team_name", "teamName", "abbr", "team_abbr"])),
                     "status": str(first(r, ["status", "injury_status", "designation"], "UNKNOWN")).upper(),
                     "detail": first(r, ["detail", "description", "note", "comment", "injury"]),
                     "source": "sports-skills", "raw_keys": sorted(list(r.keys()))[:25]})
    return rows


def normalize_standings(standings: Any) -> List[Dict[str, Any]]:
    rows = []
    for r in as_list(standings):
        if not isinstance(r, dict): continue
        team = first(r, ["team", "team_name", "name", "displayName", "abbr"])
        if isinstance(team, dict): team = first(team, ["name", "displayName", "abbreviation", "abbr"])
        if not team: continue
        rows.append({"team": norm_team(team), "wins": first(r, ["wins", "w", "W"]), "losses": first(r, ["losses", "l", "L"]),
                     "win_pct": first(r, ["win_pct", "winPercentage", "pct"]), "rank": first(r, ["rank", "seed", "conference_rank"]),
                     "source": "sports-skills", "raw_keys": sorted(list(r.keys()))[:25]})
    return rows


def normalize_futures(futures: Any) -> List[Dict[str, Any]]:
    rows = []
    for r in as_list(futures):
        if not isinstance(r, dict): continue
        rows.append({"market": first(r, ["market", "title", "type", "name"], "future"),
                     "selection": norm_team(first(r, ["team", "team_name", "participant", "selection", "outcome"])),
                     "price": first(r, ["price", "odds", "american_odds", "americanOdds"]),
                     "book": first(r, ["book", "sportsbook", "bookmaker"]), "source": "sports-skills",
                     "raw_keys": sorted(list(r.keys()))[:25]})
    return rows


def predictions_games(target: str) -> List[Dict[str, Any]]:
    data = load_json(os.path.join(PRED_DIR, f"predictions_{target}.json"), {})
    out = []
    for g in data.get("games", []) or []:
        home_obj = g.get("home", {}) if isinstance(g.get("home"), dict) else {}
        away_obj = g.get("away", {}) if isinstance(g.get("away"), dict) else {}
        home = norm_team(home_obj.get("name") or home_obj.get("abbr") or g.get("home_team") or g.get("home"))
        away = norm_team(away_obj.get("name") or away_obj.get("abbr") or g.get("away_team") or g.get("away"))
        if home and away:
            out.append({"date": target, "game": f"{away} @ {home}", "home_team": home, "away_team": away,
                        "status": "model_schedule", "source": "predictions"})
    return out


def quality_report(files: Dict[str, Any], normalized: Dict[str, List[Dict[str, Any]]], target: str) -> Dict[str, Any]:
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target,
              "sources": {}, "normalized_counts": {}, "checks": {}}
    for name, obj in files.items():
        raw = json.dumps(obj, allow_nan=False) if obj is not None else ""
        report["sources"][name] = {"exists": os.path.exists(os.path.join(RAW_WNBA, name)), "bytes": len(raw),
                                   "populated": bool(obj), "top_level_type": type(obj).__name__}
    for name, rows in normalized.items(): report["normalized_counts"][name] = len(rows)

    wehoop_status = load_json(os.path.join(RAW_DIR, "wehoop_stats_status.json"), {})
    box_rows = csv_count(os.path.join(RAW_DIR, "boxscores_wehoop.csv"))
    player_file = load_json(os.path.join(RAW_DIR, "wnba_players_live.json"), {})
    report["checks"] = {
        "games_available": len(normalized.get("games", [])) > 0,
        "standings_available": len(normalized.get("standings", [])) >= 12,
        "injury_feed_valid": isinstance(files.get("injuries.json"), (dict, list)),
        "wehoop_status_ok": wehoop_status.get("status") == "ok",
        "wehoop_boxscore_rows": box_rows,
        "player_profiles": len(player_file) if isinstance(player_file, dict) else 0,
        "stats_fresh_for_target": str(wehoop_status.get("target_date", ""))[:10] == target,
    }
    required = ["games_available", "standings_available", "wehoop_status_ok"]
    report["ready_for_model"] = all(bool(report["checks"].get(k)) for k in required) and box_rows > 0 and report["checks"]["player_profiles"] > 0
    report["health"] = "ok" if report["ready_for_model"] else "degraded"
    report["warnings"] = []
    if not report["checks"]["injury_feed_valid"]: report["warnings"].append("injury feed invalid")
    if not report["checks"]["stats_fresh_for_target"]: report["warnings"].append("wehoop target date differs from active slate")
    return report


def build(target: str) -> Dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True); os.makedirs(DASH_DIR, exist_ok=True)
    raw_files = {name: load_json(os.path.join(RAW_WNBA, name), {}) for name in ["scores.json", "injuries.json", "standings.json", "futures.json"]}
    games = normalize_scores(raw_files["scores.json"], target)
    known = {g["game"] for g in games}
    for g in predictions_games(target):
        if g["game"] not in known: games.append(g)
    normalized = {"games": games, "injuries": normalize_injuries(raw_files["injuries.json"]),
                  "standings": normalize_standings(raw_files["standings.json"]), "futures": normalize_futures(raw_files["futures.json"])}
    quality = quality_report(raw_files, normalized, target)
    outputs = {"wnba_games.json": normalized["games"], "wnba_injuries.json": normalized["injuries"],
               "wnba_standings.json": normalized["standings"], "wnba_futures.json": normalized["futures"],
               "wnba_source_quality.json": quality}
    for filename, payload in outputs.items():
        with open(os.path.join(OUT_DIR, filename), "w", encoding="utf-8") as f: json.dump(payload, f, indent=2, allow_nan=False)
    dashboard = {"generated_at_utc": quality["generated_at_utc"], "target_date": target,
                 "ready_for_model": quality["ready_for_model"], "health": quality["health"],
                 "summary": quality["normalized_counts"], "checks": quality["checks"], "warnings": quality["warnings"],
                 "source_quality": quality["sources"], "games_preview": normalized["games"][:10],
                 "injuries_preview": normalized["injuries"][:20]}
    with open(os.path.join(DASH_DIR, "wnba_data_warehouse.json"), "w", encoding="utf-8") as f: json.dump(dashboard, f, indent=2, allow_nan=False)
    return dashboard


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--date", default=str(date.today())); args = ap.parse_args()
    report = build(args.date); print(f"WNBA data warehouse built: health={report['health']} summary={report['summary']} checks={report['checks']}")


if __name__ == "__main__": main()
