"""Build pace- and minutes-adjusted opponent defensive rankings.

Uses team box scores when complete, then reconstructs team possessions and player
minutes from player box scores when ESPN team rows omit attempt fields.
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
OUTS = [Path("data/warehouse/wnba_pace_minutes_opponent_rankings.json"), Path("data/dashboard/wnba_pace_minutes_opponent_rankings.json")]
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


def game_key(value: Any) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text


def first(row: dict[str, Any], *fields: str) -> Any:
    lower = {str(k).lower(): v for k, v in row.items()}
    for field in fields:
        value = lower.get(field.lower())
        if value not in (None, "", "--", "nan", "NaN"):
            return value
    return None


def position_group(value: Any) -> str | None:
    text = str(value or "").strip().upper().replace(" ", "")
    if not text: return None
    if text in {"PG", "SG", "G", "G-F", "F-G"} or "GUARD" in text or text.startswith("G"): return "G"
    if text in {"SF", "PF", "F", "F-C", "C-F"} or "FORWARD" in text or text.startswith("F"): return "F"
    if text in {"C", "CENTER"} or "CENTER" in text or text.startswith("C"): return "C"
    return None


def stat_value(record: dict[str, Any], stat: str) -> float | None:
    key = stat.upper().replace("THREES", "3PM").replace(" ", "_")
    scoring = record.get("scoring", {}) if isinstance(record.get("scoring"), dict) else {}
    fouls = record.get("fouls", {}) if isinstance(record.get("fouls"), dict) else {}
    box = record.get("boxscore", {}) if isinstance(record.get("boxscore"), dict) else {}
    derived = record.get("derived", {}) if isinstance(record.get("derived"), dict) else {}
    values = {
        "PTS": scoring.get("total_pts"), "Q1_PTS": scoring.get("q1_pts"), "Q2_PTS": scoring.get("q2_pts"),
        "Q3_PTS": scoring.get("q3_pts"), "Q4_PTS": scoring.get("q4_pts"), "1H_PTS": scoring.get("first_half_pts"),
        "2H_PTS": scoring.get("second_half_pts"), "FTM": scoring.get("ftm"), "FTA": scoring.get("fta"),
        "FT_PTS": scoring.get("free_throw_points"), "3PM": scoring.get("three_pm"), "REB": box.get("reb"),
        "OREB": box.get("oreb"), "DREB": box.get("dreb"), "AST": box.get("ast"), "STL": box.get("stl"),
        "BLK": box.get("blk"), "TOV": box.get("tov"), "PF": fouls.get("total_committed"),
        "SHOOTING_FOULS": fouls.get("shooting"), "OFFENSIVE_FOULS": fouls.get("offensive"),
        "TECHNICAL_FOULS": fouls.get("technical"), "FLAGRANT_FOULS": fouls.get("flagrant"),
        "PRA": derived.get("pra"), "PR": derived.get("pr"), "PA": derived.get("pa"), "RA": derived.get("ra"),
    }
    return num(values.get(key))


def requires_complete_quarters(stat: str) -> bool:
    return stat.upper().replace(" ", "_") in {"Q1_PTS", "Q2_PTS", "Q3_PTS", "Q4_PTS", "1H_PTS", "2H_PTS"}


def possession_estimate(row: dict[str, Any]) -> float | None:
    fga = num(first(row, "field_goals_attempted", "fg_att", "fga"))
    oreb = num(first(row, "offensive_rebounds", "oreb"))
    tov = num(first(row, "turnovers", "tov", "to"))
    fta = num(first(row, "free_throws_attempted", "ft_att", "fta"))
    if None in (fga, oreb, tov, fta): return None
    value = fga - oreb + tov + 0.44 * fta
    return value if value > 0 else None


def load_context() -> tuple[dict[str, float], dict[tuple[str, str], float], list[str], dict[str, int]]:
    """Return game possessions and player minutes with robust current-season fallbacks."""
    team_estimates: dict[str, list[float]] = defaultdict(list)
    player_minutes: dict[tuple[str, str], float] = {}
    used: list[str] = []
    diagnostics = {"team_rows": 0, "player_rows": 0, "team_direct_estimates": 0, "team_derived_estimates": 0}

    for path in sorted(Path("data/raw").glob("wehoop_team_box_*.csv")):
        try:
            rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
            for row in rows:
                diagnostics["team_rows"] += 1
                gid = game_key(first(row, "game_id", "event_id"))
                est = possession_estimate(row)
                if gid and est is not None:
                    team_estimates[gid].append(est); diagnostics["team_direct_estimates"] += 1
            if rows: used.append(str(path))
        except Exception:
            pass

    # ESPN current-season team rows can omit FGA/FTA. Aggregate player rows by game/team.
    aggregates: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"fga": 0, "oreb": 0, "tov": 0, "fta": 0})
    for path in sorted(Path("data/raw").glob("wehoop_player_box_*.csv")):
        try:
            rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
            for row in rows:
                diagnostics["player_rows"] += 1
                gid = game_key(first(row, "game_id", "event_id"))
                player = norm(first(row, "player", "player_name", "athlete_display_name"))
                mins = num(first(row, "minutes", "min"))
                if gid and player and mins is not None and mins > 0:
                    player_minutes[(gid, player)] = mins
                team = norm(first(row, "team_id", "team_abbreviation", "team_abbr", "team_name"))
                if not gid or not team: continue
                vals = {
                    "fga": num(first(row, "field_goals_attempted", "fg_att", "fga")),
                    "oreb": num(first(row, "offensive_rebounds", "oreb")),
                    "tov": num(first(row, "turnovers", "tov", "to")),
                    "fta": num(first(row, "free_throws_attempted", "ft_att", "fta")),
                }
                if all(v is not None for v in vals.values()):
                    for k, v in vals.items(): aggregates[(gid, team)][k] += float(v)
            if rows: used.append(str(path))
        except Exception:
            pass

    for (gid, _team), values in aggregates.items():
        est = values["fga"] - values["oreb"] + values["tov"] + 0.44 * values["fta"]
        if est > 0 and len(team_estimates.get(gid, [])) < 2:
            team_estimates[gid].append(est); diagnostics["team_derived_estimates"] += 1

    game_possessions = {gid: sum(vals) / len(vals) for gid, vals in team_estimates.items() if vals}
    return game_possessions, player_minutes, sorted(set(used)), diagnostics


def record_minutes(record: dict[str, Any], lookup: dict[tuple[str, str], float]) -> float | None:
    box = record.get("boxscore", {}) if isinstance(record.get("boxscore"), dict) else {}
    value = first(record, "minutes", "min", "minutes_played")
    if value is None: value = first(box, "minutes", "min", "minutes_played")
    parsed = num(value)
    if parsed is not None and parsed > 0: return parsed
    return lookup.get((game_key(record.get("game_id")), norm(record.get("player"))))


def rank_label(rank: int, teams: int, position: str) -> str:
    if teams <= 0: return ""
    fraction = rank / teams
    if fraction <= 0.25: return f"{rank} of {teams} easiest vs {position}, pace/min adjusted"
    if fraction >= 0.75: return f"{teams-rank+1} of {teams} toughest vs {position}, pace/min adjusted"
    return f"{rank} of {teams} middle vs {position}, pace/min adjusted"


def build(target: str) -> dict[str, Any]:
    payload = load(WAREHOUSE, {"records": []})
    records = [r for r in payload.get("records", []) if isinstance(r, dict)]
    game_possessions, minute_lookup, source_files, diagnostics = load_context()
    minimum_samples = 12
    rows_out: list[dict[str, Any]] = []
    by_stat_position: dict[str, dict[str, list[dict[str, Any]]]] = {}
    skipped_missing_minutes = skipped_missing_pace = 0

    for stat in SUPPORTED_STATS:
        by_stat_position[stat] = {}
        for position in ("G", "F", "C"):
            allowed: dict[str, list[dict[str, float]]] = defaultdict(list); names: dict[str, str] = {}
            for record in records:
                if position_group(record.get("position")) != position: continue
                opponent = str(record.get("opponent") or "").strip()
                if not opponent: continue
                if requires_complete_quarters(stat) and record.get("data_quality", {}).get("quarter_data_status") != "complete": continue
                value = stat_value(record, stat)
                if value is None: continue
                minutes = record_minutes(record, minute_lookup)
                pace = game_possessions.get(game_key(record.get("game_id")))
                if minutes is None or minutes <= 0: skipped_missing_minutes += 1; continue
                if pace is None or pace <= 0: skipped_missing_pace += 1; continue
                per36 = value / minutes * 36.0
                adjusted = per36 * (TARGET_POSSESSIONS / pace)
                key = norm(opponent)
                allowed[key].append({"raw": value, "per36": per36, "pace": pace, "adjusted": adjusted, "minutes": minutes})
                names[key] = opponent
            ranked = []
            for team_key, values in allowed.items():
                if len(values) < minimum_samples: continue
                ranked.append({
                    "team": names[team_key], "team_key": team_key, "stat": stat, "position_group": position,
                    "samples": len(values), "raw_average_allowed": round(sum(v["raw"] for v in values)/len(values),4),
                    "per36_average_allowed": round(sum(v["per36"] for v in values)/len(values),4),
                    "pace_minutes_adjusted_average_allowed": round(sum(v["adjusted"] for v in values)/len(values),4),
                    "average_game_possessions": round(sum(v["pace"] for v in values)/len(values),4),
                    "average_player_minutes": round(sum(v["minutes"] for v in values)/len(values),4),
                    "target_possessions": TARGET_POSSESSIONS,
                })
            ranked.sort(key=lambda r: r["pace_minutes_adjusted_average_allowed"], reverse=True)
            for index, row in enumerate(ranked, 1):
                row["easiest_rank"] = index; row["toughest_rank"] = len(ranked)-index+1
                row["rank_label"] = rank_label(index, len(ranked), position)
                row["definition"] = f"Average {stat} allowed per 36 player minutes, scaled to {TARGET_POSSESSIONS:.0f} possessions, for opposing {position} players; rank 1 is easiest."
            by_stat_position[stat][position] = ranked; rows_out.extend(ranked)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target,
        "status": "ok" if rows_out else "warning", "summary": {
            "warehouse_records": len(records), "games_with_possession_estimate": len(game_possessions),
            "player_minutes_lookup": len(minute_lookup), "ranking_rows": len(rows_out), "minimum_samples": minimum_samples,
            "skipped_missing_minutes": skipped_missing_minutes, "skipped_missing_pace": skipped_missing_pace, **diagnostics,
        }, "rankings": rows_out, "by_stat_position": by_stat_position,
        "methodology": {"workload_adjustment": "stat per 36 player minutes", "pace_adjustment": f"scaled to {TARGET_POSSESSIONS:.0f} possessions", "possession_formula": "FGA - OREB + TOV + 0.44 * FTA; game estimate averages available team estimates", "fallback": "Incomplete team box rows are reconstructed from player box attempts and player minutes", "rank_direction": "1 = easiest / highest adjusted allowed", "position_groups": {"G":"guards","F":"forwards","C":"centers"}, "minimum_samples": minimum_samples, "source_files": source_files},
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print("Pace/minutes opponent rankings:", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args()
    build(args.date)


if __name__ == "__main__": main()
