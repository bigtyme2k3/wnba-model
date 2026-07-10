from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

MASTER_PATHS = [Path("data/dashboard/wnba_master.json"), Path("data/master/wnba_master.json")]
PLAYERS = Path("data/raw/wnba_players_live.json")
RAW = Path("data/raw")

TEAM_ABBR = {
    "Golden State Valkyries": "GSV",
    "Toronto Tempo": "TOR",
    "Minnesota Lynx": "MIN",
    "Connecticut Sun": "CON",
    "Indiana Fever": "IND",
    "Los Angeles Sparks": "LAS",
    "Washington Mystics": "WAS",
    "Seattle Storm": "SEA",
    "Las Vegas Aces": "LVA",
    "Dallas Wings": "DAL",
    "New York Liberty": "NYL",
    "Chicago Sky": "CHI",
    "Phoenix Mercury": "PHX",
    "Atlanta Dream": "ATL",
    "Portland Fire": "POR",
}


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.load(path.open(encoding="utf-8"))
    except Exception:
        pass
    return default


def to_num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(float(value), 2)


def abbr(team: str) -> str:
    if not team:
        return ""
    return TEAM_ABBR.get(team, "".join(x[:1] for x in team.split()).upper()[:3])


def game_parts(game: str) -> tuple[str, str]:
    if " @ " in game:
        away, home = game.split(" @ ", 1)
        return away.strip(), home.strip()
    return "", ""


def build_team_logos(master: dict[str, Any]) -> dict[str, str]:
    logos: dict[str, str] = {}
    for g in master.get("games", []) or []:
        if g.get("away_team") and g.get("away_logo"):
            logos[g["away_team"]] = g["away_logo"]
        if g.get("home_team") and g.get("home_logo"):
            logos[g["home_team"]] = g["home_logo"]
    return logos


def load_game_opponents() -> dict[tuple[str, str], str]:
    opponents: dict[tuple[str, str], str] = {}
    for path in sorted(RAW.glob("scores_*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    gid = str(row.get("game_id") or "").strip()
                    home = str(row.get("home_team") or "").strip()
                    away = str(row.get("away_team") or "").strip()
                    if gid and home and away:
                        opponents[(gid, home)] = away
                        opponents[(gid, away)] = home
        except Exception:
            continue
    return opponents


def load_player_game_logs(target_date: str) -> dict[str, list[dict[str, Any]]]:
    opponents = load_game_opponents()
    logs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for path in sorted(RAW.glob("boxscores_*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    player = str(row.get("player") or "").strip()
                    game_date = str(row.get("game_date") or "")[:10]
                    game_id = str(row.get("game_id") or "").strip()
                    team = str(row.get("team") or "").strip()
                    if not player or not game_date or game_date >= target_date:
                        continue
                    key = (player.lower(), game_id or game_date)
                    if key in seen:
                        continue
                    seen.add(key)
                    logs[player.lower()].append(
                        {
                            "game_date": game_date,
                            "game_id": game_id,
                            "team": team,
                            "opponent": opponents.get((game_id, team), ""),
                            "pts": to_num(row.get("pts")),
                            "reb": to_num(row.get("reb")),
                            "ast": to_num(row.get("ast")),
                            "threes": to_num(row.get("threes")),
                            "stl": to_num(row.get("stl")),
                            "blk": to_num(row.get("blk")),
                            "tov": to_num(row.get("tov")),
                            "minutes": to_num(row.get("minutes")),
                        }
                    )
        except Exception:
            continue
    for rows in logs.values():
        rows.sort(key=lambda item: (item.get("game_date", ""), item.get("game_id", "")), reverse=True)
    return logs


def stat_value(row: dict[str, Any], stat: str) -> float | None:
    key = str(stat or "").upper().replace(" ", "").replace("THREES", "3PM")
    pts, reb, ast = row["pts"], row["reb"], row["ast"]
    values = {
        "PTS": pts,
        "REB": reb,
        "AST": ast,
        "3PM": row["threes"],
        "STL": row["stl"],
        "BLK": row["blk"],
        "TOV": row["tov"],
        "PR": pts + reb,
        "PA": pts + ast,
        "RA": reb + ast,
        "PRA": pts + reb + ast,
        "PTS+REB": pts + reb,
        "PTS+AST": pts + ast,
        "REB+AST": reb + ast,
        "PTS+REB+AST": pts + reb + ast,
    }
    return values.get(key)


def history_for(logs: list[dict[str, Any]], stat: str, limit: int) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for row in logs:
        value = stat_value(row, stat)
        if value is None:
            continue
        opponent = str(row.get("opponent") or "")
        history.append(
            {
                "value": clean_number(value),
                "opponent": opponent,
                "opponent_abbr": abbr(opponent),
                "game_date": row.get("game_date"),
                "game_id": row.get("game_id"),
            }
        )
        if len(history) >= limit:
            break
    return history


def main() -> None:
    players_raw = load_json(PLAYERS, {})
    players: dict[str, dict[str, Any]] = {}
    if isinstance(players_raw, dict):
        for name, row in players_raw.items():
            if isinstance(row, dict):
                player = str(row.get("player") or name).strip().lower()
                players[player] = row

    for path in MASTER_PATHS:
        master = load_json(path, {})
        if not isinstance(master, dict) or not master:
            continue
        target_date = str(master.get("target_date") or date.today().isoformat())[:10]
        player_logs = load_player_game_logs(target_date)
        logos = build_team_logos(master)
        changed = 0
        history_count = 0
        for prop in master.get("props", []) or []:
            if not isinstance(prop, dict):
                continue
            player = str(prop.get("player", "")).strip().lower()
            prow = players.get(player, {})
            team = str(prow.get("team") or prop.get("team") or prop.get("player_team") or "").strip()
            away, home = game_parts(str(prop.get("game") or ""))
            if team not in (away, home) and not team:
                team = away or home
            opp = home if team == away else away if team == home else ""
            if team:
                prop["player_team"] = team
                prop["team_abbr"] = abbr(team)
                prop["team_logo"] = logos.get(team, "")
            if opp:
                prop["opponent"] = opp
                prop["opponent_abbr"] = abbr(opp)
                prop["opponent_logo"] = logos.get(opp, "")

            logs = player_logs.get(player, [])
            last10 = history_for(logs, str(prop.get("stat") or ""), 10)
            last5 = last10[:5]
            prop["last5"] = last5
            prop["last10"] = last10
            prop["last5_values"] = [item["value"] for item in last5]
            prop["last10_values"] = [item["value"] for item in last10]
            prop["last5_average"] = round(sum(prop["last5_values"]) / len(last5), 2) if last5 else None
            prop["last10_average"] = round(sum(prop["last10_values"]) / len(last10), 2) if last10 else None
            prop["history_source"] = "data/raw/boxscores_*.csv"
            prop["history_games_available"] = len(last10)
            if last5:
                history_count += 1
            changed += 1
        path.write_text(json.dumps(master, indent=2), encoding="utf-8")
        print(f"V4 prop context enriched {changed} props in {path}; {history_count} have actual last-five history")


if __name__ == "__main__":
    main()
