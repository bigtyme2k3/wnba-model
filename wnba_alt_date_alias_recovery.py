"""Bridge verified player logs across archive/slate date drift.

Archived ALT candidates can carry a dashboard slate date that differs from the
verified completed-game date. Recovery is deliberately conservative and now
consults an official-schedule audit before creating aliases:

1. Never alias a row when the official schedule says the archive date is exact.
2. If the schedule identifies exactly one same-orientation matchup in +/-7 days,
   only that official date may be used as the alias source.
3. If teams met more than once in the window, or only a reversed home/away game
   exists, leave the row unresolved for manual review.
4. If schedule data is unavailable, retain the older conservative record-based
   logic: adjacent-date match first, then unique exact-matchup within +/-7 days.

Original verified records are never modified or removed.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")
DASHBOARD = Path("data/dashboard/wnba_player_game_logs.json")
DIAGNOSTICS = Path("data/dashboard/wnba_alt_pending_diagnostics.json")
SCHEDULE_AUDIT = Path("data/dashboard/wnba_alt_schedule_audit.json")


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def record_date(row: dict[str, Any]) -> str:
    return str(row.get("game_date") or row.get("date") or row.get("event_date") or "")[:10]


def matchup_tokens(value: Any) -> set[str]:
    text = norm(value).replace(" at ", " ").replace(" vs ", " ")
    stop = {"new", "york", "los", "angeles", "golden", "state"}
    return {token for token in text.split() if len(token) >= 3 and token not in stop}


def record_matchup_tokens(row: dict[str, Any]) -> set[str]:
    values = [
        row.get("game"), row.get("matchup"), row.get("team"), row.get("team_name"),
        row.get("opponent"), row.get("opponent_name"), row.get("home_team"), row.get("away_team"),
    ]
    out: set[str] = set()
    for value in values:
        out |= matchup_tokens(value)
    return out


def compatible(pending: dict[str, Any], record: dict[str, Any]) -> bool:
    expected = matchup_tokens(pending.get("game"))
    actual = record_matchup_tokens(record)
    if not expected or not actual:
        return True
    return len(expected & actual) >= 1


def exact_matchup_compatible(pending: dict[str, Any], record: dict[str, Any]) -> bool:
    expected = matchup_tokens(pending.get("game"))
    actual = record_matchup_tokens(record)
    if len(expected) < 2 or len(actual) < 2:
        return False
    return len(expected & actual) >= 2


def quality(row: dict[str, Any]) -> tuple[int, int, int]:
    identity = int(bool(row.get("game_id") or row.get("event_id") or row.get("espn_event_id")))
    matchup = int(bool(row.get("opponent") or row.get("opponent_name"))) + int(bool(row.get("game") or row.get("matchup")))
    stats = sum(
        value not in (None, "")
        for key, value in row.items()
        if key.lower() in {
            "pts", "points", "reb", "rebounds", "ast", "assists", "stl", "steals",
            "blk", "blocks", "tov", "turnovers", "fg3m", "three_pointers_made", "minutes",
        }
    )
    return identity, matchup, stats


def collapse_by_date(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_date.setdefault(record_date(row), []).append(row)
    return by_date


def row_key(row: dict[str, Any]) -> str:
    line = row.get("line") if row.get("line") is not None else row.get("alt_line")
    return "|".join([
        str(row.get("date") or "")[:10],
        norm(row.get("player")),
        norm(row.get("stat")),
        norm(row.get("side")),
        str(line if line is not None else ""),
    ])


def schedule_guard_map() -> dict[str, dict[str, Any]]:
    payload = load(SCHEDULE_AUDIT, {"rows": []})
    return {
        str(row.get("row_key")): row
        for row in payload.get("rows", [])
        if isinstance(row, dict) and row.get("row_key")
    }


def choose_source(
    item: dict[str, Any],
    player: str,
    target: date,
    records: list[dict[str, Any]],
    schedule_guard: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str, dict[str, list[dict[str, Any]]]]:
    if schedule_guard:
        classification = str(schedule_guard.get("classification") or "")
        if classification == "exact_date":
            return None, "official_schedule_exact_date", {}
        if classification in {"repeated_matchup_ambiguous", "home_away_mismatch"}:
            return None, classification, {
                str(day): [] for day in (schedule_guard.get("candidate_dates") or schedule_guard.get("reversed_candidate_dates") or [])
            }
        if classification == "unique_schedule_alias":
            suggested = str(schedule_guard.get("suggested_date") or "")[:10]
            exact = [
                row for row in records
                if norm(row.get("player") or row.get("player_name")) == player
                and record_date(row) == suggested
                and exact_matchup_compatible(item, row)
            ]
            by_date = collapse_by_date(exact)
            if suggested and suggested in by_date:
                return max(by_date[suggested], key=quality), "official_unique_schedule_alias", by_date
            return None, "official_alias_log_missing", by_date

    # Schedule unavailable/not found: preserve conservative legacy fallback.
    near_dates = {
        (target - timedelta(days=1)).isoformat(),
        (target + timedelta(days=1)).isoformat(),
    }
    near = [
        row for row in records
        if norm(row.get("player") or row.get("player_name")) == player
        and record_date(row) in near_dates
        and compatible(item, row)
    ]
    near_by_date = collapse_by_date(near)
    near_collapsed = [max(rows, key=quality) for rows in near_by_date.values()]
    if len(near_collapsed) == 1:
        return near_collapsed[0], "adjacent_date", near_by_date

    wide_dates = {
        (target + timedelta(days=delta)).isoformat()
        for delta in range(-7, 8)
        if delta != 0
    }
    exact = [
        row for row in records
        if norm(row.get("player") or row.get("player_name")) == player
        and record_date(row) in wide_dates
        and exact_matchup_compatible(item, row)
    ]
    exact_by_date = collapse_by_date(exact)
    exact_collapsed = [max(rows, key=quality) for rows in exact_by_date.values()]
    if len(exact_collapsed) == 1:
        return exact_collapsed[0], "exact_matchup_wide_date", exact_by_date

    combined = exact_by_date if exact_by_date else near_by_date
    return None, "unresolved", combined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    target = date.fromisoformat(args.date)

    warehouse = load(WAREHOUSE, {"records": []})
    diagnostics = load(DIAGNOSTICS, {"inspector": []})
    guards = schedule_guard_map()
    records = [row for row in warehouse.get("records", []) if isinstance(row, dict)]
    pending = [
        row for row in diagnostics.get("inspector", [])
        if isinstance(row, dict) and str(row.get("date") or "")[:10] == args.date
    ]

    existing = {
        (norm(row.get("player") or row.get("player_name")), record_date(row))
        for row in records
    }
    aliases: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    methods: dict[str, int] = {
        "official_unique_schedule_alias": 0,
        "adjacent_date": 0,
        "exact_matchup_wide_date": 0,
    }

    for item in pending:
        player = norm(item.get("player"))
        if not player or (player, args.date) in existing:
            continue

        guard = guards.get(row_key(item))
        source, method, candidates_by_date = choose_source(item, player, target, records, guard)
        if source is None:
            unresolved.append({
                "player": item.get("player"),
                "target_date": args.date,
                "game": item.get("game"),
                "schedule_classification": guard.get("classification") if guard else None,
                "suggested_date": guard.get("suggested_date") if guard else None,
                "candidate_dates": sorted(candidates_by_date),
                "collapsed_candidate_count": len(candidates_by_date),
                "resolution": method,
            })
            continue

        alias = copy.deepcopy(source)
        alias["source_game_date"] = record_date(source)
        alias["game_date"] = args.date
        alias["date"] = args.date
        alias["date_alias_for_alt_grading"] = True
        alias["date_alias_reason"] = {
            "official_unique_schedule_alias": "official schedule identifies one unique same-orientation matchup within seven days",
            "adjacent_date": "dashboard slate date differs from verified completed-game date; adjacent-date recovery",
            "exact_matchup_wide_date": "dashboard slate date differs from verified completed-game date; unique exact-matchup recovery within seven days",
        }.get(method, method)
        alias["date_alias_method"] = method
        alias["date_alias_duplicate_sources_collapsed"] = len(candidates_by_date.get(record_date(source), []))
        if guard:
            alias["official_schedule_guard"] = guard.get("classification")
            alias["official_schedule_suggested_date"] = guard.get("suggested_date")
        aliases.append(alias)
        methods[method] = methods.get(method, 0) + 1
        existing.add((player, args.date))

    if aliases:
        records.extend(aliases)
        warehouse["records"] = records
        warehouse["alt_date_aliases_added"] = int(warehouse.get("alt_date_aliases_added") or 0) + len(aliases)
        warehouse["alt_date_alias_last_target"] = args.date
        warehouse["alt_date_alias_last_methods"] = methods
        for path in (WAREHOUSE, DASHBOARD):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                json.dump(warehouse, handle, indent=2, allow_nan=False)

    print({
        "target_date": args.date,
        "pending_rows": len(pending),
        "schedule_guards": sum(1 for item in pending if row_key(item) in guards),
        "aliases_added": len(aliases),
        "methods": methods,
        "unresolved": unresolved,
    })


if __name__ == "__main__":
    main()
