"""Build the canonical WNBA player game-log warehouse.

Primary source: normalized play-by-play events from M07.
Fallback source: player boxscore rows for full-game totals only.
Quarter scoring, free-throw points, and foul details are never inferred when the
underlying event feed is unavailable.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")
DASHBOARD = Path("data/dashboard/wnba_player_game_logs.json")


def load(path: str, default: Any) -> Any:
    try:
        p = Path(path)
        return json.load(p.open(encoding="utf-8")) if p.exists() else default
    except Exception:
        return default


def rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def num(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def integer(value: Any, default: int = 0) -> int:
    value = num(value)
    return int(value) if value is not None else default


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    try:
        if hasattr(value, "item"):
            return clean(value.item())
    except Exception:
        pass
    return str(value)


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def event_points(event: dict[str, Any]) -> int:
    direct = num(event.get("points"))
    if direct is not None:
        return max(0, int(direct))
    text = str(event.get("description") or "").lower()
    if event.get("event_type") == "FREE_THROW":
        return 1 if any(token in text for token in ("makes", "made", "good")) else 0
    if event.get("event_type") == "SHOT_MADE":
        return 3 if any(token in text for token in ("3-pt", "3pt", "three point", "three-point")) else 2
    return 0


def foul_type(event: dict[str, Any]) -> str:
    text = str(event.get("description") or "").lower()
    if "technical" in text:
        return "technical"
    if "flagrant" in text:
        return "flagrant"
    if "offensive" in text or "charge" in text:
        return "offensive"
    if "shooting" in text:
        return "shooting"
    return "personal"


def player_from_description(description: str) -> str | None:
    # Conservative fallback for feeds that omit the player field.
    match = re.match(r"^([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})", description.strip())
    return match.group(1) if match else None


def blank_record(game: str, player: str, team: Any = None) -> dict[str, Any]:
    return {
        "record_id": f"{norm(game)}|{norm(player)}",
        "game": game,
        "game_date": None,
        "player": player,
        "team": team,
        "opponent": None,
        "home_away": None,
        "starter": None,
        "minutes": None,
        "minutes_by_period": {"q1": None, "q2": None, "q3": None, "q4": None, "ot": None},
        "scoring": {
            "q1_pts": 0, "q2_pts": 0, "q3_pts": 0, "q4_pts": 0, "ot_pts": 0,
            "first_half_pts": 0, "second_half_pts": 0, "total_pts": 0,
            "fgm": None, "fga": None, "two_pm": None, "two_pa": None,
            "three_pm": 0, "three_pa": None,
            "ftm": 0, "fta": 0, "free_throw_points": 0,
        },
        "fouls": {
            "personal": 0, "offensive": 0, "shooting": 0, "technical": 0,
            "flagrant": 0, "total_committed": 0, "fouls_drawn": None, "fouled_out": False,
        },
        "boxscore": {
            "reb": None, "oreb": None, "dreb": None, "ast": None, "stl": None,
            "blk": None, "tov": None, "plus_minus": None,
        },
        "derived": {
            "pra": None, "pr": None, "pa": None, "ra": None,
            "points_per_minute": None, "free_throw_points_per_minute": None,
            "fouls_per_minute": None,
        },
        "data_quality": {
            "quarter_data_status": "unavailable",
            "event_data_status": "unavailable",
            "boxscore_data_status": "unavailable",
            "quarter_points_match_total": None,
            "validation_flags": [],
            "sources": [],
        },
    }


def period_key(period: int) -> str:
    return f"q{period}" if 1 <= period <= 4 else "ot"


def build_from_events(events: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        game = str(event.get("game") or "").strip()
        player = str(event.get("player") or "").strip() or player_from_description(str(event.get("description") or ""))
        if not game or not player:
            continue
        key = (norm(game), norm(player))
        record = records.setdefault(key, blank_record(game, player, event.get("team")))
        record["data_quality"]["event_data_status"] = "observed"
        if "play_by_play_layer" not in record["data_quality"]["sources"]:
            record["data_quality"]["sources"].append("play_by_play_layer")
        period = integer(event.get("period"))
        pkey = period_key(period)
        etype = str(event.get("event_type") or "").upper()
        points = event_points(event)
        if etype in {"SHOT_MADE", "FREE_THROW"} and points:
            field = f"{pkey}_pts"
            record["scoring"][field] += points
            record["scoring"]["total_pts"] += points
            if etype == "FREE_THROW":
                record["scoring"]["ftm"] += 1
                record["scoring"]["fta"] += 1
                record["scoring"]["free_throw_points"] += 1
            elif points == 3:
                record["scoring"]["three_pm"] += 1
        elif etype == "FREE_THROW":
            record["scoring"]["fta"] += 1
        elif etype == "FOUL":
            kind = foul_type(event)
            record["fouls"][kind] += 1
            record["fouls"]["total_committed"] += 1
        elif etype == "SUBSTITUTION":
            pass
    for record in records.values():
        s = record["scoring"]
        s["first_half_pts"] = s["q1_pts"] + s["q2_pts"]
        s["second_half_pts"] = s["q3_pts"] + s["q4_pts"] + s["ot_pts"]
        record["data_quality"]["quarter_data_status"] = "complete"
        record["data_quality"]["quarter_points_match_total"] = (
            s["q1_pts"] + s["q2_pts"] + s["q3_pts"] + s["q4_pts"] + s["ot_pts"] == s["total_pts"]
        )
    return records


def boxscore_player(row: dict[str, Any]) -> str:
    return str(row.get("player") or row.get("player_name") or row.get("athlete") or "").strip()


def merge_boxscores(records: dict[tuple[str, str], dict[str, Any]], boxscores: list[dict[str, Any]]) -> None:
    for row in boxscores:
        game = str(row.get("game") or "").strip()
        player = boxscore_player(row)
        if not game or not player:
            continue
        key = (norm(game), norm(player))
        record = records.setdefault(key, blank_record(game, player, row.get("team")))
        record["game_date"] = row.get("date") or row.get("game_date") or record.get("game_date")
        record["team"] = row.get("team") or record.get("team")
        record["opponent"] = row.get("opponent") or row.get("opp") or record.get("opponent")
        record["home_away"] = row.get("home_away") or record.get("home_away")
        record["starter"] = row.get("starter") if row.get("starter") is not None else record.get("starter")
        record["minutes"] = num(row.get("minutes", row.get("min")))
        s = record["scoring"]
        total = num(row.get("pts", row.get("PTS")))
        if total is not None:
            if record["data_quality"]["event_data_status"] != "observed":
                s["total_pts"] = int(total)
            elif int(total) != s["total_pts"]:
                record["data_quality"]["validation_flags"].append("PBP_POINTS_DO_NOT_MATCH_BOXSCORE")
        mappings = {
            "fgm": ("fgm", "FGM"), "fga": ("fga", "FGA"), "three_pm": ("fg3m", "3PM", "three_pm"),
            "three_pa": ("fg3a", "3PA", "three_pa"), "ftm": ("ftm", "FTM"), "fta": ("fta", "FTA"),
        }
        for target, fields in mappings.items():
            for field in fields:
                value = num(row.get(field))
                if value is not None:
                    if target in {"ftm", "fta", "three_pm"} and record["data_quality"]["event_data_status"] == "observed":
                        if int(value) != int(s[target]):
                            record["data_quality"]["validation_flags"].append(f"PBP_{target.upper()}_DOES_NOT_MATCH_BOXSCORE")
                    else:
                        s[target] = int(value)
                    break
        if s["ftm"] is not None:
            s["free_throw_points"] = s["ftm"]
        box = record["boxscore"]
        for target, fields in {
            "reb": ("reb", "REB"), "oreb": ("oreb", "OREB"), "dreb": ("dreb", "DREB"),
            "ast": ("ast", "AST"), "stl": ("stl", "STL"), "blk": ("blk", "BLK"),
            "tov": ("tov", "TOV"), "plus_minus": ("plus_minus", "+/-"),
        }.items():
            for field in fields:
                value = num(row.get(field))
                if value is not None:
                    box[target] = value
                    break
        fouls_total = num(row.get("pf", row.get("PF")))
        if fouls_total is not None:
            if record["data_quality"]["event_data_status"] == "observed":
                if int(fouls_total) != record["fouls"]["total_committed"]:
                    record["data_quality"]["validation_flags"].append("PBP_FOULS_DO_NOT_MATCH_BOXSCORE")
            else:
                record["fouls"]["personal"] = int(fouls_total)
                record["fouls"]["total_committed"] = int(fouls_total)
        record["fouls"]["fouled_out"] = record["fouls"]["total_committed"] >= 6
        record["data_quality"]["boxscore_data_status"] = "observed"
        if "boxscores" not in record["data_quality"]["sources"]:
            record["data_quality"]["sources"].append("boxscores")


def finalize(record: dict[str, Any]) -> None:
    s = record["scoring"]
    if record["data_quality"]["event_data_status"] != "observed":
        record["data_quality"]["quarter_data_status"] = "unavailable"
        record["data_quality"]["quarter_points_match_total"] = None
        for key in ("q1_pts", "q2_pts", "q3_pts", "q4_pts", "ot_pts", "first_half_pts", "second_half_pts"):
            s[key] = None
    elif not record["data_quality"]["quarter_points_match_total"]:
        record["data_quality"]["quarter_data_status"] = "partial"
        record["data_quality"]["validation_flags"].append("QUARTER_POINTS_DO_NOT_MATCH_EVENT_TOTAL")
    box = record["boxscore"]
    pts = s.get("total_pts")
    reb, ast = box.get("reb"), box.get("ast")
    if pts is not None and reb is not None:
        record["derived"]["pr"] = pts + reb
    if pts is not None and ast is not None:
        record["derived"]["pa"] = pts + ast
    if reb is not None and ast is not None:
        record["derived"]["ra"] = reb + ast
    if pts is not None and reb is not None and ast is not None:
        record["derived"]["pra"] = pts + reb + ast
    minutes = record.get("minutes")
    if minutes and minutes > 0:
        record["derived"]["points_per_minute"] = round(pts / minutes, 4) if pts is not None else None
        record["derived"]["free_throw_points_per_minute"] = round((s.get("free_throw_points") or 0) / minutes, 4)
        record["derived"]["fouls_per_minute"] = round(record["fouls"]["total_committed"] / minutes, 4)


def build(target: str) -> dict[str, Any]:
    pbp = load("data/warehouse/wnba_play_by_play_layer.json", {})
    events = rows(pbp, "events")
    boxscores = []
    for path in (
        "data/warehouse/wnba_boxscores.json",
        f"data/raw/boxscore_player_stats_{target}.json",
        f"data/raw/wnba_boxscores_{target}.json",
    ):
        payload = load(path, {})
        candidate = rows(payload, "players", "player_stats", "boxscores", "rows", "games")
        if candidate:
            boxscores.extend(candidate)
    records = build_from_events(events)
    merge_boxscores(records, boxscores)
    output = list(records.values())
    for record in output:
        finalize(record)
    output.sort(key=lambda r: (str(r.get("game_date") or ""), r.get("game") or "", r.get("player") or ""), reverse=True)
    summary = {
        "records": len(output),
        "players": len({norm(r.get("player")) for r in output}),
        "games": len({norm(r.get("game")) for r in output}),
        "quarter_complete": sum(r["data_quality"]["quarter_data_status"] == "complete" for r in output),
        "quarter_partial": sum(r["data_quality"]["quarter_data_status"] == "partial" for r in output),
        "quarter_unavailable": sum(r["data_quality"]["quarter_data_status"] == "unavailable" for r in output),
        "records_with_free_throw_points": sum((r["scoring"].get("free_throw_points") or 0) > 0 for r in output),
        "records_with_fouls": sum(r["fouls"].get("total_committed", 0) > 0 for r in output),
        "validation_flags": sum(len(r["data_quality"].get("validation_flags", [])) for r in output),
    }
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "schema_version": "1.0",
        "summary": summary,
        "records": clean(output),
        "data_contract": {
            "quarter_scoring_source": "normalized play-by-play only",
            "full_game_totals_source": "play-by-play with boxscore reconciliation",
            "free_throw_points_definition": "made free throws; equal to FTM",
            "foul_detail_source": "play-by-play description; full-game PF fallback from boxscore",
            "validation_rule": "Q1 + Q2 + Q3 + Q4 + OT must equal event-derived total points",
        },
    }
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    for path in (WAREHOUSE, DASHBOARD):
        with path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    print("Player game-log warehouse:", build(args.date)["summary"])


if __name__ == "__main__":
    main()
