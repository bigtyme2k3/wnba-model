"""Build pace- and minutes-adjusted opponent defensive rankings.

Adjustment contract:
- Workload normalization: stat per 36 player minutes.
- Pace normalization: per-36 rate scaled to an 80-possession game.
- Game possessions estimate: average of both teams using
  FGA - OREB + TOV + 0.44 * FTA.
- Position groups: G, F, C.
- Rank 1 = easiest opponent (highest adjusted average allowed).
- Minimum 12 verified player-game samples per team/stat/position.
- Quarter and half markets require complete quarter data.

The output is descriptive matchup context. Possessions are estimates and are
reported transparently for every row.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")
OUTS = [
    Path("data/warehouse/wnba_pace_minutes_opponent_rankings.json"),
    Path("data/dashboard/wnba_pace_minutes_opponent_rankings.json"),
]
TARGET_POSSESSIONS = 80.0
SUPPORTED_STATS = [
    "PTS", "Q1 PTS", "Q2 PTS", "Q3 PTS", "Q4 PTS", "1H PTS", "2H PTS",
    "FTM", "FTA", "FT PTS", "3PM", "REB", "OREB", "DREB", "AST", "STL", "BLK", "TOV",
    "PF", "SHOOTING FOULS", "OFFENSIVE FOULS", "TECHNICAL FOULS", "FLAGRANT FOULS",
    "PRA", "PR", "PA", "RA",
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


def first(row: dict[str, Any], *fields: str) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, "", "--", "nan", "NaN"):
            return value
    return None


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
        "FTM": scoring.get("ftm"), "FTA": scoring.get("fta"), "FT_PTS": scoring.get("free_throw_points"),
        "3PM": scoring.get("three_pm"),
        "REB": box.get("reb"), "OREB": box.get("oreb"), "DREB": box.get("dreb"),
        "AST": box.get("ast"), "STL": box.get("stl"), "BLK": box.get("blk"), "TOV": box.get("tov"),
        "PF": fouls.get("total_committed"), "SHOOTING_FOULS": fouls.get("shooting"),
        "OFFENSIVE_FOULS": fouls.get("offensive"), "TECHNICAL_FOULS": fouls.get("technical"),
        "FLAGRANT_FOULS": fouls.get("flagrant"),
        "PRA": derived.get("pra"), "PR": derived.get("pr"), "PA": derived.get("pa"), "RA": derived.get("ra"),
    }
    return num(values.get(key))


def requires_complete_quarters(stat: str) -> bool:
    return stat.upper().replace(" ", "_") in {
        "Q1_PTS", "Q2_PTS", "Q3_PTS", "Q4_PTS", "1H_PTS", "2H_PTS"
    }


def possession_estimate(row: dict[str, Any]) -> float | None:
    fga = num(first(row, "field_goals_attempted", "fga", "FGA"))
    oreb = num(first(row, "offensive_rebounds", "oreb", "OREB"))
    tov = num(first(row, "turnovers", "tov", "TOV", "TO"))
    fta = num(first(row, "free_throws_attempted", "fta", "FTA"))
    if None in (fga, oreb, tov, fta):
        return None
    value = fga - oreb + tov + 0.44 * fta
    return value if value > 0 else None


def load_game_possessions() -> tuple[dict[str, float], list[str]]:
    files = sorted(Path("data/raw").glob("wehoop_team_box_*.csv"))
    team_rows: dict[str, list[float]] = defaultdict(list)
    used: list[str] = []
    for path in files:
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows = [dict(row) for row in csv.DictReader(handle)]
            for row in rows:
                game_id = str(first(row, "game_id", "event_id") or "").strip()
                estimate = possession_estimate(row)
                if game_id and estimate is not None:
                    team_rows[game_id].append(estimate)
            if rows:
                used.append(str(path))
        except Exception:
            continue
    game_possessions = {
        game_id: sum(values) / len(values)
        for game_id, values in team_rows.items()
        if values
    }
    return game_possessions, used


def rank_label(rank: int, teams: int, position: str) -> str:
    if teams <= 0:
        return ""
    fraction = rank / teams
    if fraction <= 0.25:
        return f"{rank} of {teams} easiest vs {position}, pace/min adjusted"
    if fraction >= 0.75:
        toughest = teams - rank + 1
        return f"{toughest} of {teams} toughest vs {position}, pace/min adjusted"
    return f"{rank} of {teams} middle vs {position}, pace/min adjusted"


def build(target: str) -> dict[str, Any]:
    payload = load(WAREHOUSE, {"records": []})
    records = [r for r in payload.get("records", []) if isinstance(r, dict)]
    game_possessions, possession_files = load_game_possessions()
    minimum_samples = 12
    rows_out: list[dict[str, Any]] = []
    by_stat_position: dict[str, dict[str, list[dict[str, Any]]]] = {}
    skipped_missing_minutes = 0
    skipped_missing_pace = 0

    for stat in SUPPORTED_STATS:
        by_stat_position[stat] = {}
        for position in ("G", "F", "C"):
            allowed: dict[str, list[dict[str, float]]] = defaultdict(list)
            names: dict[str, str] = {}
            for record in records:
                if position_group(record.get("position")) != position:
                    continue
                opponent = str(record.get("opponent") or "").strip()
                if not opponent:
                    continue
                if requires_complete_quarters(stat) and record.get("data_quality", {}).get("quarter_data_status") != "complete":
                    continue
                value = stat_value(record, stat)
                minutes = num(record.get("minutes"))
                game_id = str(record.get("game_id") or "").strip()
                pace = game_possessions.get(game_id)
                if value is None:
                    continue
                if minutes is None or minutes <= 0:
                    skipped_missing_minutes += 1
                    continue
                if pace is None or pace <= 0:
                    skipped_missing_pace += 1
                    continue
                per36 = value / minutes * 36.0
                adjusted = per36 * (TARGET_POSSESSIONS / pace)
                key = norm(opponent)
                allowed[key].append({"raw": value, "per36": per36, "pace": pace, "adjusted": adjusted, "minutes": minutes})
                names[key] = opponent
            ranked: list[dict[str, Any]] = []
            for team_key, values in allowed.items():
                if len(values) < minimum_samples:
                    continue
                adjusted_values = [v["adjusted"] for v in values]
                raw_values = [v["raw"] for v in values]
                per36_values = [v["per36"] for v in values]
                paces = [v["pace"] for v in values]
                minutes_values = [v["minutes"] for v in values]
                ranked.append({
                    "team": names[team_key],
                    "team_key": team_key,
                    "stat": stat,
                    "position_group": position,
                    "samples": len(values),
                    "raw_average_allowed": round(sum(raw_values) / len(raw_values), 4),
                    "per36_average_allowed": round(sum(per36_values) / len(per36_values), 4),
                    "pace_minutes_adjusted_average_allowed": round(sum(adjusted_values) / len(adjusted_values), 4),
                    "average_game_possessions": round(sum(paces) / len(paces), 4),
                    "average_player_minutes": round(sum(minutes_values) / len(minutes_values), 4),
                    "target_possessions": TARGET_POSSESSIONS,
                })
            ranked.sort(key=lambda r: r["pace_minutes_adjusted_average_allowed"], reverse=True)
            team_count = len(ranked)
            for index, row in enumerate(ranked, start=1):
                row["easiest_rank"] = index
                row["toughest_rank"] = team_count - index + 1
                row["rank_label"] = rank_label(index, team_count, position)
                row["definition"] = (
                    f"Average {stat} allowed per 36 player minutes, scaled to {TARGET_POSSESSIONS:.0f} possessions, "
                    f"for opposing {position} players; rank 1 is easiest."
                )
            by_stat_position[stat][position] = ranked
            rows_out.extend(ranked)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "summary": {
            "warehouse_records": len(records),
            "games_with_possession_estimate": len(game_possessions),
            "ranking_rows": len(rows_out),
            "minimum_samples": minimum_samples,
            "skipped_missing_minutes": skipped_missing_minutes,
            "skipped_missing_pace": skipped_missing_pace,
        },
        "rankings": rows_out,
        "by_stat_position": by_stat_position,
        "methodology": {
            "workload_adjustment": "stat per 36 player minutes",
            "pace_adjustment": f"scaled to {TARGET_POSSESSIONS:.0f} possessions",
            "possession_formula": "FGA - OREB + TOV + 0.44 * FTA; game estimate is average of both teams",
            "rank_direction": "1 = easiest / highest adjusted allowed",
            "position_groups": {"G": "guards", "F": "forwards", "C": "centers"},
            "quarter_policy": "complete quarter records only",
            "minimum_samples": minimum_samples,
            "limitations": "Possessions are estimates; hybrid positions map to one broad group.",
            "possession_source_files": possession_files,
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    print("Pace/minutes opponent rankings:", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
