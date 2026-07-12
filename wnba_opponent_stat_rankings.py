"""Build documented stat-specific opponent defensive rankings.

Definition:
- Unit: average stat allowed per opposing player-game.
- Direction: rank 1 = easiest opponent (highest average allowed).
- Quarter/half markets use only records with complete quarter data.
- Rankings require a minimum number of opponent player-game samples.

This is intentionally descriptive, not causal. Position-adjusted rankings can
be layered on later without changing this contract.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")
OUTS = [Path("data/warehouse/wnba_opponent_stat_rankings.json"), Path("data/dashboard/wnba_opponent_stat_rankings.json")]

SUPPORTED_STATS = [
    "PTS","Q1 PTS","Q2 PTS","Q3 PTS","Q4 PTS","1H PTS","2H PTS",
    "FTM","FTA","FT PTS","3PM","REB","OREB","DREB","AST","STL","BLK","TOV",
    "PF","SHOOTING FOULS","OFFENSIVE FOULS","TECHNICAL FOULS","FLAGRANT FOULS",
    "PRA","PR","PA","RA",
]


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def stat_value(record: dict[str, Any], stat: str) -> float | None:
    key = stat.upper().replace("THREES", "3PM").replace(" ", "_")
    scoring = record.get("scoring", {}) if isinstance(record.get("scoring"), dict) else {}
    fouls = record.get("fouls", {}) if isinstance(record.get("fouls"), dict) else {}
    box = record.get("boxscore", {}) if isinstance(record.get("boxscore"), dict) else {}
    derived = record.get("derived", {}) if isinstance(record.get("derived"), dict) else {}
    values = {
        "PTS": scoring.get("total_pts"),
        "Q1_PTS": scoring.get("q1_pts"), "Q2_PTS": scoring.get("q2_pts"),
        "Q3_PTS": scoring.get("q3_pts"), "Q4_PTS": scoring.get("q4_pts"),
        "1H_PTS": scoring.get("first_half_pts"), "2H_PTS": scoring.get("second_half_pts"),
        "FTM": scoring.get("ftm"), "FTA": scoring.get("fta"),
        "FT_PTS": scoring.get("free_throw_points"), "3PM": scoring.get("three_pm"),
        "REB": box.get("reb"), "OREB": box.get("oreb"), "DREB": box.get("dreb"),
        "AST": box.get("ast"), "STL": box.get("stl"), "BLK": box.get("blk"), "TOV": box.get("tov"),
        "PF": fouls.get("total_committed"), "SHOOTING_FOULS": fouls.get("shooting"),
        "OFFENSIVE_FOULS": fouls.get("offensive"), "TECHNICAL_FOULS": fouls.get("technical"),
        "FLAGRANT_FOULS": fouls.get("flagrant"),
        "PRA": derived.get("pra"), "PR": derived.get("pr"), "PA": derived.get("pa"), "RA": derived.get("ra"),
    }
    return num(values.get(key))


def requires_complete_quarters(stat: str) -> bool:
    return stat.upper().replace(" ", "_") in {"Q1_PTS","Q2_PTS","Q3_PTS","Q4_PTS","1H_PTS","2H_PTS"}


def label(rank: int, teams: int) -> str:
    if teams <= 0:
        return ""
    pct = rank / teams
    if pct <= 0.25:
        return f"{rank} of {teams} easiest"
    if pct >= 0.75:
        toughest = teams - rank + 1
        return f"{toughest} of {teams} toughest"
    return f"{rank} of {teams} middle"


def build(target: str) -> dict[str, Any]:
    payload = load(WAREHOUSE, {"records": []})
    records = [r for r in payload.get("records", []) if isinstance(r, dict)]
    minimum_samples = 20
    rankings: list[dict[str, Any]] = []
    by_stat: dict[str, list[dict[str, Any]]] = {}

    for stat in SUPPORTED_STATS:
        allowed: dict[str, list[float]] = defaultdict(list)
        names: dict[str, str] = {}
        for record in records:
            opponent = str(record.get("opponent") or "").strip()
            if not opponent:
                continue
            if requires_complete_quarters(stat) and record.get("data_quality", {}).get("quarter_data_status") != "complete":
                continue
            value = stat_value(record, stat)
            if value is None:
                continue
            key = norm(opponent)
            allowed[key].append(value)
            names[key] = opponent
        rows = []
        for team_key, values in allowed.items():
            if len(values) < minimum_samples:
                continue
            rows.append({
                "team": names[team_key],
                "team_key": team_key,
                "stat": stat,
                "samples": len(values),
                "average_allowed_per_opposing_player_game": round(sum(values) / len(values), 4),
                "median_allowed": round(sorted(values)[len(values)//2], 4),
            })
        rows.sort(key=lambda r: r["average_allowed_per_opposing_player_game"], reverse=True)
        team_count = len(rows)
        for index, row in enumerate(rows, start=1):
            row["easiest_rank"] = index
            row["toughest_rank"] = team_count - index + 1
            row["rank_label"] = label(index, team_count)
            row["definition"] = "Average stat allowed per opposing player-game; rank 1 is easiest."
        by_stat[stat] = rows
        rankings.extend(rows)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "summary": {
            "warehouse_records": len(records),
            "supported_stats": len(SUPPORTED_STATS),
            "ranking_rows": len(rankings),
            "minimum_samples": minimum_samples,
        },
        "rankings": rankings,
        "by_stat": by_stat,
        "methodology": {
            "unit": "opposing player-game",
            "metric": "average stat allowed",
            "rank_direction": "1 = easiest / highest allowed",
            "quarter_policy": "complete quarter records only",
            "minimum_samples": minimum_samples,
            "limitations": "Not position-adjusted and not pace-adjusted; descriptive matchup context only.",
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    print("Opponent stat rankings:", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
