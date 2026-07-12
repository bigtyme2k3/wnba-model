"""Attach documented stat-specific opponent rankings to ALT Streaks rows."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ALT_PATHS = [Path("data/warehouse/wnba_alt_streaks.json"), Path("data/dashboard/wnba_alt_streaks.json")]
RANKINGS = Path("data/warehouse/wnba_opponent_stat_rankings.json")

TEAM_ALIASES = {
    "las vegas aces": "las vegas aces", "aces": "las vegas aces", "lv": "las vegas aces",
    "new york liberty": "new york liberty", "liberty": "new york liberty", "ny": "new york liberty",
    "connecticut sun": "connecticut sun", "sun": "connecticut sun", "con": "connecticut sun",
    "atlanta dream": "atlanta dream", "dream": "atlanta dream", "atl": "atlanta dream",
    "chicago sky": "chicago sky", "sky": "chicago sky", "chi": "chicago sky",
    "dallas wings": "dallas wings", "wings": "dallas wings", "dal": "dallas wings",
    "indiana fever": "indiana fever", "fever": "indiana fever", "ind": "indiana fever",
    "los angeles sparks": "los angeles sparks", "sparks": "los angeles sparks", "la": "los angeles sparks",
    "minnesota lynx": "minnesota lynx", "lynx": "minnesota lynx", "min": "minnesota lynx",
    "phoenix mercury": "phoenix mercury", "mercury": "phoenix mercury", "phx": "phoenix mercury",
    "seattle storm": "seattle storm", "storm": "seattle storm", "sea": "seattle storm",
    "washington mystics": "washington mystics", "mystics": "washington mystics", "was": "washington mystics",
    "golden state valkyries": "golden state valkyries", "valkyries": "golden state valkyries", "gs": "golden state valkyries",
}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def normalize_team(value: Any) -> str:
    text = " ".join(str(value or "").strip().lower().replace("’", "'").split())
    return TEAM_ALIASES.get(text, text)


def main() -> None:
    ranking_payload = load(RANKINGS, {"rankings": []})
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in ranking_payload.get("rankings", []):
        if not isinstance(row, dict):
            continue
        key = (normalize_team(row.get("team")), str(row.get("stat") or "").upper())
        index[key] = row
    updated = missing = 0
    for path in ALT_PATHS:
        payload = load(path, {"rows": []})
        for row in payload.get("rows", []):
            if not isinstance(row, dict):
                continue
            opponent = normalize_team(row.get("opponent"))
            stat = str(row.get("stat") or "").upper()
            ranking = index.get((opponent, stat))
            if ranking:
                row["opponent_rank"] = ranking.get("easiest_rank")
                row["opponent_rank_total_teams"] = len(ranking_payload.get("by_stat", {}).get(stat, []))
                row["opponent_label"] = ranking.get("rank_label")
                row["opponent_average_allowed"] = ranking.get("average_allowed_per_opposing_player_game")
                row["opponent_rank_samples"] = ranking.get("samples")
                row["opponent_rank_source"] = "wnba_opponent_stat_rankings"
                row["opponent_rank_definition"] = ranking.get("definition")
                updated += 1
            else:
                row["opponent_rank"] = None
                row["opponent_rank_total_teams"] = None
                row["opponent_label"] = None
                row["opponent_average_allowed"] = None
                row["opponent_rank_samples"] = None
                row["opponent_rank_source"] = None
                row["opponent_rank_definition"] = None
                missing += 1
        payload.setdefault("summary", {})["opponent_rank_rows"] = sum(r.get("opponent_rank") is not None for r in payload.get("rows", []))
        payload["opponent_rank_methodology"] = ranking_payload.get("methodology", {})
        payload["data_policy"] = (
            "L5, L10, and season records come from verified player game logs. "
            "Opponent rank is stat-specific: average allowed per opposing player-game, where rank 1 is easiest."
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
    print("ALT Streaks opponent context:", {"updated": updated, "missing": missing})


if __name__ == "__main__":
    main()
