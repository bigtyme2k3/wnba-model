"""Strictly promote unresolved ALT history against completed player-games.

This pass is monotonic by design: every existing WIN/LOSS/PUSH/VOID row is
immutable. Only PENDING rows may be promoted. Matching prefers an exact archived
date, then the frozen sportsbook game-time date, then a matchup that occurs only
once in the player's completed season. Repeated matchups are never guessed.
"""
from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from wnba_alt_performance_tracker import stat_value, outcome, one_unit_profit

ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
REPORT = Path("data/dashboard/wnba_alt_strict_regrade.json")
WAREHOUSE_REPORT = Path("data/warehouse/wnba_alt_strict_regrade.json")
STRICT_SOURCE = "player_game_log_warehouse_strict_match"
FINAL = {"WIN", "LOSS", "PUSH", "VOID"}
ET = ZoneInfo("America/New_York")

TEAM_ALIASES = {
    "la sparks": "los angeles sparks", "los angeles": "los angeles sparks",
    "ny liberty": "new york liberty", "new york": "new york liberty",
    "gs valkyries": "golden state valkyries", "golden state": "golden state valkyries",
    "lv aces": "las vegas aces", "las vegas": "las vegas aces",
    "washington": "washington mystics", "connecticut": "connecticut sun",
    "phoenix": "phoenix mercury", "atlanta": "atlanta dream",
    "dallas": "dallas wings", "seattle": "seattle storm",
    "chicago": "chicago sky", "minnesota": "minnesota lynx",
    "indiana": "indiana fever", "portland": "portland fire", "toronto": "toronto tempo",
    "sparks": "los angeles sparks", "liberty": "new york liberty",
    "valkyries": "golden state valkyries", "aces": "las vegas aces",
    "mystics": "washington mystics", "sun": "connecticut sun",
    "mercury": "phoenix mercury", "dream": "atlanta dream",
    "wings": "dallas wings", "storm": "seattle storm", "sky": "chicago sky",
    "lynx": "minnesota lynx", "fever": "indiana fever", "fire": "portland fire",
    "tempo": "toronto tempo",
}


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def team_norm(value: Any) -> str:
    text = re.sub(r"[^a-z0-9' ]+", " ", norm(value))
    text = " ".join(text.split())
    return TEAM_ALIASES.get(text, text)


def parse_time(value: Any) -> datetime | None:
    try:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            return None
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def frozen_game_date(row: dict[str, Any]) -> str:
    start = parse_time(row.get("game_time"))
    return start.astimezone(ET).date().isoformat() if start else ""


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


def game_pair(value: Any) -> frozenset[str]:
    text = str(value or "").strip()
    if "@" not in text:
        return frozenset()
    away, home = text.split("@", 1)
    parts = [team_norm(away), team_norm(home)]
    return frozenset(parts) if all(parts) and parts[0] != parts[1] else frozenset()


def team_pair(row: dict[str, Any]) -> frozenset[str]:
    for key in ("game", "opponent"):
        pair = game_pair(row.get(key))
        if pair:
            return pair
    team = team_norm(row.get("team"))
    opponent = team_norm(row.get("opponent"))
    if team and opponent and "@" not in str(row.get("opponent") or ""):
        return frozenset((team, opponent))
    return frozenset()


def record_identity(record: dict[str, Any]) -> str:
    return str(record.get("record_id") or record.get("game_id") or record.get("event_id") or record.get("game") or "")


def emit_report(report: dict[str, Any]) -> None:
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    for path in (REPORT, WAREHOUSE_REPORT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def unique_games(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = str(row.get("game_id") or row.get("event_id") or f"{str(row.get('game_date') or '')[:10]}|{row.get('game')}")
        chosen[identity] = row
    return list(chosen.values())


def main() -> None:
    original = read_jsonl(ARCHIVE)
    history = copy.deepcopy(original)
    logs = load(LOGS, {"records": []})
    records = [r for r in logs.get("records", []) if isinstance(r, dict)]
    baseline_final = sum(str(r.get("outcome") or "").upper() in FINAL for r in original)

    by_player_date: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        player = norm(record.get("player"))
        game_date = str(record.get("game_date") or "")[:10]
        if player:
            by_player[player].append(record)
        if player and game_date:
            by_player_date[(player, game_date)].append(record)

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    stats = {
        "rows": len(history), "baseline_final": baseline_final,
        "verified_final_preserved": 0, "strictly_graded": 0,
        "same_date_exact": 0, "frozen_game_time_exact": 0,
        "unique_matchup_date_shift": 0, "game_not_completed_yet": 0,
        "no_player_game": 0, "archive_matchup_missing": 0,
        "matchup_mismatch": 0, "repeated_matchup_date_ambiguous": 0,
        "multiple_exact_matches": 0, "unique_player_date_fallback": 0,
        "stat_unavailable": 0,
    }
    mismatch_samples: list[dict[str, Any]] = []

    for row in history:
        current_outcome = str(row.get("outcome") or "").upper()
        if current_outcome in FINAL:
            stats["verified_final_preserved"] += 1
            continue

        player = norm(row.get("player"))
        snapshot_date = str(row.get("date") or "")[:10]
        scheduled_date = frozen_game_date(row)
        wanted_pair = team_pair(row)
        same_date = by_player_date.get((player, snapshot_date), [])
        scheduled_rows = by_player_date.get((player, scheduled_date), []) if scheduled_date else []
        all_player = by_player.get(player, [])
        exact: list[dict[str, Any]] = []
        match_mode = ""

        start = parse_time(row.get("game_time"))
        if start is not None and start > now_dt:
            row["grading_reason"] = "frozen sportsbook game has not started yet"
            row["scheduled_game_date"] = scheduled_date or None
            stats["game_not_completed_yet"] += 1
            continue

        if wanted_pair:
            same_exact = unique_games([r for r in same_date if team_pair(r) == wanted_pair])
            if len(same_exact) == 1:
                exact, match_mode = same_exact, "same_date_exact"
                stats["same_date_exact"] += 1
            elif len(same_exact) > 1:
                row["grading_reason"] = "multiple completed player-games match archived wager on snapshot date"
                row["candidate_record_ids"] = [record_identity(r) for r in same_exact]
                stats["multiple_exact_matches"] += 1
                continue
            else:
                scheduled_exact = unique_games([r for r in scheduled_rows if team_pair(r) == wanted_pair])
                if scheduled_date and scheduled_date != snapshot_date and len(scheduled_exact) == 1:
                    exact, match_mode = scheduled_exact, "frozen_game_time_exact"
                    stats["frozen_game_time_exact"] += 1
                elif scheduled_date and scheduled_date != snapshot_date and len(scheduled_exact) > 1:
                    row["grading_reason"] = "multiple completed player-games match frozen sportsbook game date"
                    row["candidate_record_ids"] = [record_identity(r) for r in scheduled_exact]
                    stats["multiple_exact_matches"] += 1
                    continue
                else:
                    season_exact = unique_games([r for r in all_player if team_pair(r) == wanted_pair])
                    if len(season_exact) == 1:
                        exact, match_mode = season_exact, "unique_matchup_date_shift"
                        stats["unique_matchup_date_shift"] += 1
                    elif len(season_exact) > 1:
                        row["grading_reason"] = "repeated matchup across season; exact date anchors do not resolve one completed game"
                        row["scheduled_game_date"] = scheduled_date or None
                        row["candidate_completed_games"] = [f"{str(r.get('game_date') or '')[:10]} {r.get('game')}" for r in season_exact]
                        row["candidate_record_ids"] = [record_identity(r) for r in season_exact]
                        stats["repeated_matchup_date_ambiguous"] += 1
                        continue
                    else:
                        if not same_date and not scheduled_rows:
                            stats["no_player_game"] += 1
                            row["grading_reason"] = "no completed player-game found for archived matchup"
                        else:
                            stats["matchup_mismatch"] += 1
                            row["grading_reason"] = "candidate-date player-game exists but archived matchup does not match"
                        if len(mismatch_samples) < 25:
                            mismatch_samples.append({"date": snapshot_date, "scheduled_game_date": scheduled_date, "player": row.get("player"), "archive_game": row.get("game")})
                        continue
        else:
            stats["archive_matchup_missing"] += 1
            candidate_rows = unique_games(scheduled_rows if scheduled_rows else same_date)
            if len(candidate_rows) == 1:
                exact, match_mode = candidate_rows, "unique_player_date_fallback"
                stats["unique_player_date_fallback"] += 1
            else:
                row["grading_reason"] = "archive matchup missing and candidate date is not uniquely resolvable"
                row["candidate_record_ids"] = [record_identity(r) for r in candidate_rows]
                continue

        if len(exact) != 1:
            row["grading_reason"] = "strict matching did not resolve exactly one completed player-game"
            continue

        record = exact[0]
        actual = stat_value(record, str(row.get("stat") or ""))
        if actual is None:
            row["grading_reason"] = "actual stat unavailable in matched completed player-game"
            row["actual_record_id"] = record_identity(record)
            stats["stat_unavailable"] += 1
            continue

        result = outcome(str(row.get("side") or ""), actual, row.get("alt_line"))
        if result == "PENDING":
            row["grading_reason"] = "could not derive final outcome"
            continue

        row["actual"] = actual
        row["outcome"] = result
        row["profit_loss"] = one_unit_profit(result, row.get("best_odds"))
        row["graded_at_utc"] = now
        row["actual_source"] = STRICT_SOURCE
        row["actual_record_id"] = record_identity(record)
        row["actual_game_id"] = record.get("game_id") or record.get("event_id")
        row["actual_game_date"] = str(record.get("game_date") or "")[:10]
        row["grading_match_mode"] = match_mode
        row["grading_reason"] = None
        stats["strictly_graded"] += 1

    final = sum(str(r.get("outcome") or "").upper() in FINAL for r in history)
    pending = sum(str(r.get("outcome") or "PENDING").upper() == "PENDING" for r in history)
    stats.update({"proposed_final": final, "proposed_pending": pending})
    safe_to_apply = final >= baseline_final
    report = {
        "generated_at_utc": now,
        "status": "PASS" if safe_to_apply else "BLOCKED",
        "safe_to_apply": safe_to_apply,
        "minimum_safe_final": baseline_final,
        "stats": stats,
        "mismatch_samples": mismatch_samples,
        "identity_rule": "player + canonical matchup; snapshot date exact, then frozen game-time date exact, then unique completed season matchup",
        "repeated_matchup_policy": "never guess among repeated completed matchups",
        "future_game_policy": "future frozen game times remain pending",
        "preservation_policy": "every pre-existing final outcome is immutable; strict recovery only promotes pending rows",
    }
    emit_report(report)
    if not safe_to_apply:
        raise SystemExit(f"Refusing destructive archive rewrite: proposed final {final} < existing final {baseline_final}")
    write_jsonl(ARCHIVE, history)
    print("Strict ALT regrade:", stats)


if __name__ == "__main__":
    main()
