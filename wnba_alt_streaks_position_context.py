"""Attach position-adjusted opponent context to ALT Streaks.

Position-adjusted rankings are preferred when the player's warehouse position
and sufficient samples are available. Otherwise the existing overall
stat-specific ranking remains in place.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ALT_PATHS = [Path("data/warehouse/wnba_alt_streaks.json"), Path("data/dashboard/wnba_alt_streaks.json")]
POSITION_RANKS = Path("data/warehouse/wnba_position_opponent_rankings.json")
WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")

TEAM_ALIASES = {
    "aces": "las vegas aces", "lv": "las vegas aces",
    "liberty": "new york liberty", "ny": "new york liberty",
    "sun": "connecticut sun", "con": "connecticut sun",
    "dream": "atlanta dream", "atl": "atlanta dream",
    "sky": "chicago sky", "chi": "chicago sky",
    "wings": "dallas wings", "dal": "dallas wings",
    "fever": "indiana fever", "ind": "indiana fever",
    "sparks": "los angeles sparks", "la": "los angeles sparks",
    "lynx": "minnesota lynx", "min": "minnesota lynx",
    "mercury": "phoenix mercury", "phx": "phoenix mercury",
    "storm": "seattle storm", "sea": "seattle storm",
    "mystics": "washington mystics", "was": "washington mystics",
    "valkyries": "golden state valkyries", "gs": "golden state valkyries",
}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def normalize_team(value: Any) -> str:
    text = norm(value)
    return TEAM_ALIASES.get(text, text)


def position_group(value: Any) -> str | None:
    text = str(value or "").strip().upper().replace(" ", "")
    if not text:
        return None
    if text in {"PG", "SG", "G", "G-F", "F-G"} or "GUARD" in text or text.startswith("G"):
        return "G"
    if text in {"SF", "PF", "F", "F-C", "C-F"} or "FORWARD" in text or text.startswith("F"):
        return "F"
    if text in {"C", "CENTER"} or "CENTER" in text or text.startswith("C"):
        return "C"
    return None


def main() -> None:
    rankings = load(POSITION_RANKS, {"rankings": []})
    warehouse = load(WAREHOUSE, {"records": []})
    player_positions: dict[str, str] = {}
    records = [r for r in warehouse.get("records", []) if isinstance(r, dict)]
    records.sort(key=lambda r: str(r.get("game_date") or ""), reverse=True)
    for record in records:
        player = norm(record.get("player"))
        group = position_group(record.get("position"))
        if player and group and player not in player_positions:
            player_positions[player] = group

    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    totals: dict[tuple[str, str], int] = {}
    for row in rankings.get("rankings", []):
        if not isinstance(row, dict):
            continue
        stat = str(row.get("stat") or "").upper()
        position = str(row.get("position_group") or "").upper()
        team = normalize_team(row.get("team"))
        index[(team, stat, position)] = row
    for stat, groups in rankings.get("by_stat_position", {}).items():
        if not isinstance(groups, dict):
            continue
        for position, rows in groups.items():
            totals[(str(stat).upper(), str(position).upper())] = len(rows) if isinstance(rows, list) else 0

    upgraded = fallback = missing_position = 0
    for path in ALT_PATHS:
        payload = load(path, {"rows": []})
        for row in payload.get("rows", []):
            if not isinstance(row, dict):
                continue
            player = norm(row.get("player"))
            position = player_positions.get(player)
            row["position_group"] = position
            if not position:
                row["position_rank_available"] = False
                row["position_rank_reason"] = "player position unavailable"
                missing_position += 1
                continue
            stat = str(row.get("stat") or "").upper()
            opponent = normalize_team(row.get("opponent"))
            rank = index.get((opponent, stat, position))
            if rank:
                row["opponent_rank"] = rank.get("easiest_rank")
                row["opponent_rank_total_teams"] = totals.get((stat, position))
                row["opponent_label"] = rank.get("rank_label")
                row["opponent_average_allowed"] = rank.get("average_allowed_per_opposing_player_game")
                row["opponent_rank_samples"] = rank.get("samples")
                row["opponent_rank_source"] = "wnba_position_opponent_rankings"
                row["opponent_rank_definition"] = rank.get("definition")
                row["position_rank_available"] = True
                row["position_rank_reason"] = None
                upgraded += 1
            else:
                row["position_rank_available"] = False
                row["position_rank_reason"] = "minimum position sample not met; overall stat rank retained"
                fallback += 1
        payload.setdefault("summary", {})["position_adjusted_rank_rows"] = sum(
            r.get("opponent_rank_source") == "wnba_position_opponent_rankings" for r in payload.get("rows", [])
        )
        payload["position_rank_methodology"] = rankings.get("methodology", {})
        payload["data_policy"] = (
            "L5, L10, and season records come from verified player game logs. "
            "Opponent rank prefers position-adjusted average allowed per opposing player-game; "
            "overall stat rank is retained when position samples are insufficient."
        )
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
    print("ALT Streaks position context:", {"upgraded": upgraded, "fallback": fallback, "missing_position": missing_position})


if __name__ == "__main__":
    main()
