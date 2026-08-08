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


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def key(row: dict[str, Any]) -> str:
    """Return a true player-game identity.

    Historical daily warehouse rows used ``game|player`` as record_id. That
    collapses separate meetings between the same teams. Prefer an event/game ID
    when one exists; otherwise date + matchup + player is the canonical key.
    Only undated legacy rows may fall back to their old record_id.
    """
    game_date = str(row.get("game_date") or row.get("date") or "").strip()[:10]
    game_id = str(row.get("game_id") or row.get("event_id") or "").strip().lower()
    player_id = str(row.get("player_id") or row.get("athlete_id") or "").strip().lower()
    player = norm(row.get("player") or row.get("player_name") or row.get("athlete"))
    game = norm(row.get("game"))

    if game_id and (player_id or player):
        return f"event:{game_id}|player:{player_id or player}"
    if game_date and game and player:
        return f"date:{game_date}|game:{game}|player:{player}"

    record_id = str(row.get("record_id") or "").strip().lower()
    if record_id:
        return f"legacy:{record_id}"
    return "|".join((game_date, game, player)).strip("|")


def canonical_record_id(row: dict[str, Any]) -> str:
    """Persist the same identity used by the archive merge."""
    return key(row)


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
    identity_collisions_prevented = 0

    # Track legacy game|player IDs that now resolve to more than one dated game.
    legacy_to_canonical: dict[str, set[str]] = {}

    for row in list(old.get("records", [])) + list(new.get("records", [])):
        if not isinstance(row, dict):
            continue
        k = key(row)
        if not k:
            continue
        legacy = str(row.get("record_id") or "").strip().lower()
        if legacy:
            legacy_to_canonical.setdefault(legacy, set()).add(k)

        prior = merged.get(k)
        if prior is None:
            normalized = dict(row)
            normalized["record_id"] = canonical_record_id(normalized)
            merged[k] = normalized
            continue
        before_date = str(prior.get("game_date") or "").strip()
        combined = merge_rows(prior, row)
        combined["record_id"] = canonical_record_id(combined)
        after_date = str(combined.get("game_date") or "").strip()
        if not before_date and after_date:
            recovered_dates += 1
        merged[k] = combined

    identity_collisions_prevented = sum(max(0, len(keys) - 1) for keys in legacy_to_canonical.values())
    records = list(merged.values())
    records.sort(key=lambda r: (str(r.get("game_date") or ""), str(r.get("game") or ""), str(r.get("player") or "")), reverse=True)
    payload = dict(new)
    payload["records"] = records
    summary = payload.setdefault("summary", {})
    summary.update({
        "records": len(records),
        "players": len({str(r.get('player') or '').strip().lower() for r in records if r.get('player')}),
        "games": len({(str(r.get('game_date') or '')[:10], str(r.get('game') or '').strip().lower()) for r in records if r.get('game')}),
        "archive_previous_records": len(old.get("records", [])),
        "archive_new_records": len(new.get("records", [])),
        "archive_recovered_game_dates": recovered_dates,
        "archive_identity_version": "player-game-v2",
        "archive_identity_rule": "game_id+player_id/player; else game_date+game+player",
        "archive_legacy_collisions_prevented": identity_collisions_prevented,
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
