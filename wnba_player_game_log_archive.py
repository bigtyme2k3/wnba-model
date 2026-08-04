"""Preserve and merge the cumulative player game-log warehouse across runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CURRENT = Path("data/warehouse/wnba_player_game_logs.json")
STAGING = Path("data/history/wnba_player_game_logs_before_build.json")
DASHBOARD = Path("data/dashboard/wnba_player_game_logs.json")


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def key(row: dict[str, Any]) -> str:
    record_id = str(row.get("record_id") or "").strip().lower()
    if record_id:
        return record_id
    return "|".join(str(row.get(field) or "").strip().lower() for field in ("game_date", "game", "player"))


def quality(row: dict[str, Any]) -> tuple[int, int, int, int]:
    data = row.get("data_quality", {}) if isinstance(row.get("data_quality"), dict) else {}
    quarter = {"complete": 3, "partial": 2, "unavailable": 1}.get(data.get("quarter_data_status"), 0)
    event = 1 if data.get("event_data_status") == "observed" else 0
    box = 1 if data.get("boxscore_data_status") == "observed" else 0
    dated = 1 if str(row.get("game_date") or "").strip() else 0
    return quarter, event, box, dated


def missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def combine(preferred: Any, fallback: Any) -> Any:
    """Keep the higher-quality row while filling fields it does not contain.

    Recovery feeds often provide a verified game date and box-score totals while
    the play-by-play record has richer event detail. Replacing either entire row
    loses useful information, so merge complementary nested fields recursively.
    """
    if isinstance(preferred, dict) and isinstance(fallback, dict):
        merged = dict(preferred)
        for field, value in fallback.items():
            if field not in merged or missing(merged[field]):
                merged[field] = value
            elif isinstance(merged[field], dict) and isinstance(value, dict):
                merged[field] = combine(merged[field], value)
            elif isinstance(merged[field], list) and isinstance(value, list):
                # Preserve unique provenance/validation entries.
                merged[field] = list(dict.fromkeys([*merged[field], *value]))
        return merged
    return fallback if missing(preferred) else preferred


def merge_rows(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if quality(right) > quality(left):
        return combine(right, left)
    return combine(left, right)


def snapshot() -> None:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    payload = load(CURRENT, {"records": []})
    with STAGING.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
    print("Player game-log archive snapshot:", len(payload.get("records", [])))


def merge() -> None:
    old = load(STAGING, {"records": []})
    new = load(CURRENT, {"records": []})
    merged: dict[str, dict[str, Any]] = {}
    recovered_dates = 0
    for row in list(old.get("records", [])) + list(new.get("records", [])):
        if not isinstance(row, dict):
            continue
        k = key(row)
        if not k:
            continue
        prior = merged.get(k)
        if prior is None:
            merged[k] = row
            continue
        before_date = str(prior.get("game_date") or "").strip()
        combined = merge_rows(prior, row)
        after_date = str(combined.get("game_date") or "").strip()
        if not before_date and after_date:
            recovered_dates += 1
        merged[k] = combined
    records = list(merged.values())
    records.sort(key=lambda r: (str(r.get("game_date") or ""), str(r.get("game") or ""), str(r.get("player") or "")), reverse=True)
    payload = dict(new)
    payload["records"] = records
    summary = payload.setdefault("summary", {})
    summary.update({
        "records": len(records),
        "players": len({str(r.get('player') or '').strip().lower() for r in records if r.get('player')}),
        "games": len({str(r.get('game') or '').strip().lower() for r in records if r.get('game')}),
        "archive_previous_records": len(old.get("records", [])),
        "archive_new_records": len(new.get("records", [])),
        "archive_recovered_game_dates": recovered_dates,
        "archive_cumulative": True,
    })
    for path in (CURRENT, DASHBOARD):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
    print("Player game-log archive merged:", summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("snapshot", "merge"))
    args = parser.parse_args()
    snapshot() if args.mode == "snapshot" else merge()


if __name__ == "__main__":
    main()
