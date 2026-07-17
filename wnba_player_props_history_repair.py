"""Replace synthetic Player Props history with verified warehouse game logs.

This is a targeted repair for the existing V4/V5 pipeline. It keeps the current
Player Props layout and odds rows, but removes fabricated recent values/opponents,
filters DD/TD, and attaches only completed player games from the canonical
warehouse. Missing history remains missing rather than being represented as zero.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")
RAW = Path("data/raw")
REMOVED_STATS = {"DD", "TD", "DOUBLE_DOUBLE", "TRIPLE_DOUBLE"}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def stat_value(record: dict[str, Any], stat: str) -> float | None:
    scoring = record.get("scoring") or {}
    box = record.get("boxscore") or {}
    derived = record.get("derived") or {}
    mapping = {
        "PTS": scoring.get("total_pts"),
        "REB": box.get("reb"),
        "AST": box.get("ast"),
        "3PM": scoring.get("three_pm"),
        "PRA": derived.get("pra"),
        "PR": derived.get("pr"),
        "PA": derived.get("pa"),
        "RA": derived.get("ra"),
        "STL": box.get("stl"),
        "BLK": box.get("blk"),
    }
    return num(mapping.get(stat))


def completed(record: dict[str, Any]) -> bool:
    minutes = num(record.get("minutes"))
    if minutes is None or minutes <= 0:
        return False
    if not record.get("game_date"):
        return False
    quality = record.get("data_quality") or {}
    if quality.get("boxscore_data_status") == "unavailable" and quality.get("event_data_status") == "unavailable":
        return False
    return True


def history_index() -> dict[str, list[dict[str, Any]]]:
    payload = load_json(WAREHOUSE, {"records": []})
    records = payload.get("records", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict) or not completed(record):
            continue
        player = norm(record.get("player"))
        game_key = str(record.get("game_id") or record.get("record_id") or record.get("game") or "")
        key = (player, game_key)
        if not player or not game_key or key in seen:
            continue
        seen.add(key)
        grouped.setdefault(player, []).append(record)
    for player_records in grouped.values():
        player_records.sort(key=lambda r: (str(r.get("game_date") or ""), str(r.get("game_id") or r.get("record_id") or "")), reverse=True)
    return grouped


def hit_rate(values: list[float], line: float | None, side: str) -> float | None:
    if not values or line is None or side not in {"OVER", "UNDER"}:
        return None
    hits = sum(value > line if side == "OVER" else value < line for value in values)
    return round(hits / len(values), 4)


def repair_file(path: Path, histories: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    if not path.exists():
        return {"rows": 0, "repaired": 0, "missing": 0, "removed": 0}
    frame = pd.read_csv(path)
    if frame.empty:
        return {"rows": 0, "repaired": 0, "missing": 0, "removed": 0}
    stat_series = frame.get("stat", pd.Series(index=frame.index, dtype=str)).astype(str).str.upper()
    removed = int(stat_series.isin(REMOVED_STATS).sum())
    frame = frame.loc[~stat_series.isin(REMOVED_STATS)].copy()
    repaired = missing = 0
    for index, row in frame.iterrows():
        player_records = histories.get(norm(row.get("player")), [])
        stat = str(row.get("stat") or "").upper()
        recent: list[dict[str, Any]] = []
        for record in player_records:
            value = stat_value(record, stat)
            if value is None:
                continue
            recent.append({
                "value": value,
                "opponent": record.get("opponent"),
                "game_date": record.get("game_date"),
                "game_id": record.get("game_id") or record.get("record_id"),
            })
            if len(recent) >= 10:
                break
        values10 = [entry["value"] for entry in recent]
        values5 = values10[:5]
        opponents5 = [entry.get("opponent") or "-" for entry in recent[:5]]
        line = num(row.get("line"))
        side = str(row.get("signal") or "").upper()
        frame.at[index, "last5_vals"] = json.dumps(values5)
        frame.at[index, "last5_opps"] = json.dumps(opponents5)
        frame.at[index, "last5_hit"] = hit_rate(values5, line, side)
        frame.at[index, "last10_hit"] = hit_rate(values10, line, side)
        frame.at[index, "history_games"] = len(values10)
        frame.at[index, "history_latest_date"] = recent[0]["game_date"] if recent else ""
        frame.at[index, "history_source"] = "wnba_player_game_logs" if recent else "missing"
        if recent:
            repaired += 1
        else:
            missing += 1
    frame.to_csv(path, index=False)
    return {"rows": len(frame), "repaired": repaired, "missing": missing, "removed": removed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    histories = history_index()
    totals = {"rows": 0, "repaired": 0, "missing": 0, "removed": 0}
    for path in (RAW / "player_points_today.csv", RAW / f"player_points_{args.date}.csv"):
        result = repair_file(path, histories)
        for key, value in result.items():
            totals[key] += value
    report = {
        "target_date": args.date,
        "warehouse_players": len(histories),
        "summary": totals,
        "policy": {
            "synthetic_history_allowed": False,
            "zero_placeholders_allowed": False,
            "dd_td_removed": True,
            "source": str(WAREHOUSE),
        },
    }
    out = Path("data/dashboard/wnba_player_props_history_repair.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, out.open("w", encoding="utf-8"), indent=2)
    print("Player Props history repair:", report)


if __name__ == "__main__":
    main()
