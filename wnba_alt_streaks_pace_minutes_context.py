"""Prefer pace- and minutes-adjusted opponent rankings in ALT Streaks.

Fallback order remains:
1. Pace/minutes-adjusted position rank
2. Position-adjusted rank
3. Overall stat-specific rank
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ALT_PATHS = [Path("data/warehouse/wnba_alt_streaks.json"), Path("data/dashboard/wnba_alt_streaks.json")]
RANKS = Path("data/warehouse/wnba_pace_minutes_opponent_rankings.json")
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
    rankings = load(RANKS, {"rankings": []})
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

    upgraded = fallback = 0
    for path in ALT_PATHS:
        payload = load(path, {"rows": []})
        for row in payload.get("rows", []):
            if not isinstance(row, dict):
                continue
            position = player_positions.get(norm(row.get("player"))) or row.get("position_group")
            stat = str(row.get("stat") or "").upper()
            opponent = normalize_team(row.get("opponent"))
            rank = index.get((opponent, stat, str(position or "").upper()))
            if rank:
                row["position_group"] = position
                row["opponent_rank"] = rank.get("easiest_rank")
                row["opponent_rank_total_teams"] = totals.get((stat, str(position).upper()))
                row["opponent_label"] = rank.get("rank_label")
                row["opponent_average_allowed"] = rank.get("pace_minutes_adjusted_average_allowed")
                row["opponent_raw_average_allowed"] = rank.get("raw_average_allowed")
                row["opponent_per36_average_allowed"] = rank.get("per36_average_allowed")
                row["opponent_average_game_possessions"] = rank.get("average_game_possessions")
                row["opponent_average_player_minutes"] = rank.get("average_player_minutes")
                row["opponent_rank_samples"] = rank.get("samples")
                row["opponent_rank_source"] = "wnba_pace_minutes_opponent_rankings"
                row["opponent_rank_definition"] = rank.get("definition")
                row["pace_minutes_rank_available"] = True
                row["pace_minutes_rank_reason"] = None
                upgraded += 1
            else:
                row["pace_minutes_rank_available"] = False
                row["pace_minutes_rank_reason"] = "minimum minutes/pace sample not met; prior verified rank retained"
                fallback += 1
        payload.setdefault("summary", {})["pace_minutes_adjusted_rank_rows"] = sum(
            r.get("opponent_rank_source") == "wnba_pace_minutes_opponent_rankings" for r in payload.get("rows", [])
        )
        payload["pace_minutes_rank_methodology"] = rankings.get("methodology", {})
        payload["data_policy"] = (
            "L5, L10, and season records come from verified player game logs. "
            "Opponent rank prefers position, minutes, and estimated-pace adjusted averages; "
            "verified position or overall rankings remain as fallback."
        )
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
    print("ALT Streaks pace/minutes context:", {"upgraded": upgraded, "fallback": fallback})


if __name__ == "__main__":
    main()
