from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MASTER_PATHS = [Path("data/dashboard/wnba_master.json"), Path("data/master/wnba_master.json")]
PLAYERS = Path("data/raw/wnba_players_live.json")

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
        logos = build_team_logos(master)
        changed = 0
        for prop in master.get("props", []) or []:
            if not isinstance(prop, dict):
                continue
            player = str(prop.get("player", "")).strip().lower()
            prow = players.get(player, {})
            team = str(prow.get("team") or prop.get("team") or prop.get("player_team") or "").strip()
            away, home = game_parts(str(prop.get("game") or ""))
            if team not in (away, home):
                # Keep known official team if available; otherwise fall back to game side only as last resort.
                if not team:
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
            changed += 1
        path.write_text(json.dumps(master, indent=2), encoding="utf-8")
        print(f"V4 prop context enriched {changed} props in {path}")


if __name__ == "__main__":
    main()
