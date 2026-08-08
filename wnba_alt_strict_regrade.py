"""Strictly regrade ALT history against completed canonical player-games.

This repair removes the legacy grader behavior that selected the first player
record found for a snapshot date. A wager may only grade from the player-game
warehouse when the archived matchup and completed warehouse matchup agree.
Verified manual overrides and Phase 1 official-event recoveries are preserved.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wnba_alt_performance_tracker import stat_value, outcome, one_unit_profit

ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
TRUSTED_SOURCES = {"manual_verified_override", "espn_schedule_event_phase1"}


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def team_pair(row: dict[str, Any]) -> frozenset[str]:
    team = norm(row.get("team"))
    opponent = norm(row.get("opponent"))
    if team and opponent:
        return frozenset((team, opponent))
    game = str(row.get("game") or "")
    if "@" in game:
        parts = [norm(x) for x in game.split("@", 1)]
        if all(parts):
            return frozenset(parts)
    return frozenset()


def record_identity(record: dict[str, Any]) -> str:
    return str(record.get("record_id") or record.get("game_id") or record.get("game") or "")


def reset_warehouse_grade(row: dict[str, Any]) -> None:
    row["actual"] = None
    row["outcome"] = "PENDING"
    row["profit_loss"] = None
    row["graded_at_utc"] = None
    row["actual_source"] = None
    row["grading_reason"] = None
    row.pop("actual_record_id", None)
    row.pop("actual_game_id", None)
    row.pop("actual_game_date", None)


def main() -> None:
    history = read_jsonl(ARCHIVE)
    logs = load(LOGS, {"records": []})
    records = [r for r in logs.get("records", []) if isinstance(r, dict)]

    by_player_date: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        player = norm(record.get("player"))
        game_date = str(record.get("game_date") or "")[:10]
        if player and game_date:
            by_player_date[(player, game_date)].append(record)

    now = datetime.now(timezone.utc).isoformat()
    stats = {
        "rows": len(history),
        "trusted_preserved": 0,
        "strictly_graded": 0,
        "no_player_game": 0,
        "matchup_mismatch": 0,
        "multiple_exact_matches": 0,
        "stat_unavailable": 0,
    }

    for row in history:
        source = str(row.get("actual_source") or "")
        if source in TRUSTED_SOURCES and str(row.get("outcome") or "") in {"WIN", "LOSS", "PUSH", "VOID"}:
            stats["trusted_preserved"] += 1
            continue

        reset_warehouse_grade(row)
        player = norm(row.get("player"))
        snapshot_date = str(row.get("date") or "")[:10]
        candidates = by_player_date.get((player, snapshot_date), [])
        if not candidates:
            row["grading_reason"] = "no completed player-game on snapshot date"
            stats["no_player_game"] += 1
            continue

        wanted_pair = team_pair(row)
        exact = [r for r in candidates if wanted_pair and team_pair(r) == wanted_pair]
        if not exact:
            row["grading_reason"] = "completed player-game exists but matchup does not match archived wager"
            row["candidate_completed_games"] = [str(r.get("game") or "") for r in candidates]
            stats["matchup_mismatch"] += 1
            continue
        if len(exact) != 1:
            row["grading_reason"] = "multiple completed player-games match archived wager"
            row["candidate_record_ids"] = [record_identity(r) for r in exact]
            stats["multiple_exact_matches"] += 1
            continue

        record = exact[0]
        actual = stat_value(record, str(row.get("stat") or ""))
        if actual is None:
            row["grading_reason"] = "actual stat unavailable in matched completed player-game"
            row["actual_record_id"] = record_identity(record)
            stats["stat_unavailable"] += 1
            continue

        result = outcome(str(row.get("side") or ""), actual, row.get("alt_line"))
        row["actual"] = actual
        row["outcome"] = result
        row["profit_loss"] = one_unit_profit(result, row.get("best_odds"))
        row["graded_at_utc"] = now
        row["actual_source"] = "player_game_log_warehouse_strict_match"
        row["actual_record_id"] = record_identity(record)
        row["actual_game_id"] = record.get("game_id") or record.get("event_id")
        row["actual_game_date"] = str(record.get("game_date") or "")[:10]
        row["grading_reason"] = None if result != "PENDING" else "could not derive final outcome"
        if result != "PENDING":
            stats["strictly_graded"] += 1

    write_jsonl(ARCHIVE, history)
    pending = sum(str(r.get("outcome") or "PENDING") == "PENDING" for r in history)
    final = sum(str(r.get("outcome") or "") in {"WIN", "LOSS", "PUSH", "VOID"} for r in history)
    stats.update({"final": final, "pending": pending})
    print("Strict ALT regrade:", stats)


if __name__ == "__main__":
    main()
