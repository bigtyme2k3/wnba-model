"""
wnba_data_warehouse.py
----------------------
Normalizes multi-source WNBA data into one model-ready warehouse layer.

Current sources:
- sports-skills JSON: data/wnba/*.json
- existing raw model data: data/raw/*
- predictions schedule: predictions/predictions_YYYY-MM-DD.json

Outputs:
- data/warehouse/wnba_source_quality.json
- data/warehouse/wnba_games.json
- data/warehouse/wnba_injuries.json
- data/warehouse/wnba_standings.json
- data/warehouse/wnba_futures.json
- data/dashboard/wnba_data_warehouse.json
"""

from __future__ import annotations

import argparse
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
        "NYL": "New York Liberty", "PHO": "Phoenix Mercury", "LVA": "Las Vegas Aces"
    }.get(v.upper(), v)


def normalize_scores(scores: Any, target: str) -> List[Dict[str, Any]]:
    games = []
    for g in as_list(scores):
        if not isinstance(g, dict):
            continue
        home = first(g, ["home_team", "home", "homeTeam", "home_name", "homeName"])
        away = first(g, ["away_team", "away", "awayTeam", "away_name", "awayName"])
        if isinstance(home, dict):
            home = first(home, ["name", "displayName", "abbreviation", "abbr"])
        if isinstance(away, dict):
            away = first(away, ["name", "displayName", "abbreviation", "abbr"])
        home = norm_team(home)
        away = norm_team(away)
        if not home or not away:
            continue
        games.append({
            "date": first(g, ["date", "game_date", "commence_time", "start_time"], target),
            "game": f"{away} @ {home}",
            "home_team": home,
            "away_team": away,
            "home_score": first(g, ["home_score", "homeScore", "home_points", "homePoints"]),
            "away_score": first(g, ["away_score", "awayScore", "away_points", "awayPoints"]),
            "status": first(g, ["status", "game_status", "state", "phase"], "scheduled"),
            "source": "sports-skills",
            "raw_keys": sorted(list(g.keys()))[:25],
        })
    return games


def normalize_injuries(injuries: Any) -> List[Dict[str, Any]]:
    rows = []
    for r in as_list(injuries):
        if not isinstance(r, dict):
            continue
        player = first(r, ["player", "player_name", "name", "athlete"])
        if isinstance(player, dict):
            player = first(player, ["name", "displayName", "fullName"])
        if not player:
            continue
        rows.append({
            "player": str(player),
            "team": norm_team(first(r, ["team", "team_name", "teamName", "abbr", "team_abbr"])),
            "status": str(first(r, ["status", "injury_status", "designation"], "UNKNOWN")).upper(),
            "detail": first(r, ["detail", "description", "note", "comment", "injury"]),
            "source": "sports-skills",
            "raw_keys": sorted(list(r.keys()))[:25],
        })
    return rows


def normalize_standings(standings: Any) -> List[Dict[str, Any]]:
    rows = []
    for r in as_list(standings):
        if not isinstance(r, dict):
            continue
        team = first(r, ["team", "team_name", "name", "displayName", "abbr"])
        if isinstance(team, dict):
            team = first(team, ["name", "displayName", "abbreviation", "abbr"])
        if not team:
            continue
        rows.append({
            "team": norm_team(team),
            "wins": first(r, ["wins", "w", "W"]),
            "losses": first(r, ["losses", "l", "L"]),
            "win_pct": first(r, ["win_pct", "winPercentage", "pct"]),
            "rank": first(r, ["rank", "seed", "conference_rank"]),
            "source": "sports-skills",
            "raw_keys": sorted(list(r.keys()))[:25],
        })
    return rows


def normalize_futures(futures: Any) -> List[Dict[str, Any]]:
    rows = []
    for r in as_list(futures):
        if not isinstance(r, dict):
            continue
        market = first(r, ["market", "title", "type", "name"], "future")
        team = first(r, ["team", "team_name", "participant", "selection", "outcome"])
        price = first(r, ["price", "odds", "american_odds", "americanOdds"])
        rows.append({
            "market": market,
            "selection": norm_team(team),
            "price": price,
            "book": first(r, ["book", "sportsbook", "bookmaker"]),
            "source": "sports-skills",
            "raw_keys": sorted(list(r.keys()))[:25],
        })
    return rows


def predictions_games(target: str) -> List[Dict[str, Any]]:
    p = os.path.join(PRED_DIR, f"predictions_{target}.json")
    data = load_json(p, {})
    out = []
    for g in data.get("games", []) or []:
        home_obj = g.get("home", {}) if isinstance(g.get("home"), dict) else {}
        away_obj = g.get("away", {}) if isinstance(g.get("away"), dict) else {}
        home = norm_team(home_obj.get("name") or home_obj.get("abbr") or g.get("home_team") or g.get("home"))
        away = norm_team(away_obj.get("name") or away_obj.get("abbr") or g.get("away_team") or g.get("away"))
        if home and away:
            out.append({"date": target, "game": f"{away} @ {home}", "home_team": home, "away_team": away, "status": "model_schedule", "source": "predictions"})
    return out


def quality_report(files: Dict[str, Any], normalized: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "sources": {}, "normalized_counts": {}}
    for name, obj in files.items():
        raw = json.dumps(obj) if obj is not None else ""
        report["sources"][name] = {
            "exists": os.path.exists(os.path.join(RAW_WNBA, name)),
            "bytes": len(raw),
            "populated": bool(obj),
            "top_level_type": type(obj).__name__,
        }
    for name, rows in normalized.items():
        report["normalized_counts"][name] = len(rows)
    report["ready_for_model"] = all(report["normalized_counts"].get(k, 0) > 0 for k in ["games", "injuries", "standings"])
    return report


def build(target: str) -> Dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(DASH_DIR, exist_ok=True)

    raw_files = {
        "scores.json": load_json(os.path.join(RAW_WNBA, "scores.json"), {}),
        "injuries.json": load_json(os.path.join(RAW_WNBA, "injuries.json"), {}),
        "standings.json": load_json(os.path.join(RAW_WNBA, "standings.json"), {}),
        "futures.json": load_json(os.path.join(RAW_WNBA, "futures.json"), {}),
    }

    games = normalize_scores(raw_files["scores.json"], target)
    pred_games = predictions_games(target)
    known = {g["game"] for g in games}
    for g in pred_games:
        if g["game"] not in known:
            games.append(g)

    normalized = {
        "games": games,
        "injuries": normalize_injuries(raw_files["injuries.json"]),
        "standings": normalize_standings(raw_files["standings.json"]),
        "futures": normalize_futures(raw_files["futures.json"]),
    }
    quality = quality_report(raw_files, normalized)

    outputs = {
        "wnba_games.json": normalized["games"],
        "wnba_injuries.json": normalized["injuries"],
        "wnba_standings.json": normalized["standings"],
        "wnba_futures.json": normalized["futures"],
        "wnba_source_quality.json": quality,
    }
    for filename, payload in outputs.items():
        with open(os.path.join(OUT_DIR, filename), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    dashboard = {
        "generated_at_utc": quality["generated_at_utc"],
        "target_date": target,
        "ready_for_model": quality["ready_for_model"],
        "summary": quality["normalized_counts"],
        "source_quality": quality["sources"],
        "games_preview": normalized["games"][:10],
        "injuries_preview": normalized["injuries"][:20],
    }
    with open(os.path.join(DASH_DIR, "wnba_data_warehouse.json"), "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2)
    return dashboard


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    report = build(args.date)
    print(f"✅ WNBA data warehouse built: {report['summary']}")


if __name__ == "__main__":
    main()
