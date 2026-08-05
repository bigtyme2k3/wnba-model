"""Bridge verified player logs across a one-day slate/date boundary.

Some archived ALT candidates use the dashboard slate date while the verified
box score is stored under the local completed-game date. This script creates a
clearly marked canonical alias only when the pending player has exactly one
verified record within +/- 1 day and the matchup is compatible when team data
is available. Original verified records are never modified or removed.
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
    return {token for token in text.split() if len(token) >= 4 and token not in stop}


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    target = date.fromisoformat(args.date)

    warehouse = load(WAREHOUSE, {"records": []})
    diagnostics = load(DIAGNOSTICS, {"inspector": []})
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

    for item in pending:
        player = norm(item.get("player"))
        if not player or (player, args.date) in existing:
            continue
        candidate_dates = {
            (target - timedelta(days=1)).isoformat(),
            (target + timedelta(days=1)).isoformat(),
        }
        candidates = [
            row for row in records
            if norm(row.get("player") or row.get("player_name")) == player
            and record_date(row) in candidate_dates
            and compatible(item, row)
        ]
        # Deduplicate equivalent source records before deciding uniqueness.
        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in candidates:
            key = (
                record_date(row),
                norm(row.get("team") or row.get("team_name")),
                norm(row.get("opponent") or row.get("opponent_name")),
            )
            unique.setdefault(key, row)
        candidates = list(unique.values())
        if len(candidates) != 1:
            unresolved.append({
                "player": item.get("player"),
                "target_date": args.date,
                "candidate_dates": sorted({record_date(row) for row in candidates}),
                "candidate_count": len(candidates),
            })
            continue

        source = candidates[0]
        alias = copy.deepcopy(source)
        alias["source_game_date"] = record_date(source)
        alias["game_date"] = args.date
        alias["date"] = args.date
        alias["date_alias_for_alt_grading"] = True
        alias["date_alias_reason"] = "dashboard slate date differs from verified completed-game date by one day"
        aliases.append(alias)
        existing.add((player, args.date))

    if aliases:
        records.extend(aliases)
        warehouse["records"] = records
        warehouse["alt_date_aliases_added"] = int(warehouse.get("alt_date_aliases_added") or 0) + len(aliases)
        warehouse["alt_date_alias_last_target"] = args.date
        for path in (WAREHOUSE, DASHBOARD):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                json.dump(warehouse, handle, indent=2, allow_nan=False)

    print({
        "target_date": args.date,
        "pending_rows": len(pending),
        "aliases_added": len(aliases),
        "unresolved": unresolved,
    })


if __name__ == "__main__":
    main()
