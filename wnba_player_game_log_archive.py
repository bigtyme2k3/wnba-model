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


def quality(row: dict[str, Any]) -> tuple[int, int, int]:
    data = row.get("data_quality", {}) if isinstance(row.get("data_quality"), dict) else {}
    quarter = {"complete": 3, "partial": 2, "unavailable": 1}.get(data.get("quarter_data_status"), 0)
    event = 1 if data.get("event_data_status") == "observed" else 0
    box = 1 if data.get("boxscore_data_status") == "observed" else 0
    return quarter, event, box


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
    for row in list(old.get("records", [])) + list(new.get("records", [])):
        if not isinstance(row, dict):
            continue
        k = key(row)
        if not k:
            continue
        prior = merged.get(k)
        if prior is None or quality(row) >= quality(prior):
            merged[k] = row
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
