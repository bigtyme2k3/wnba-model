"""Strictly regrade ALT history against completed canonical player-games.

A wager grades only from a completed player-game whose canonical matchup agrees
with the archived matchup. Same-date exact matches are preferred. When a frozen
snapshot date drifted from the actual game date, a cross-date recovery is allowed
ONLY when that player's completed warehouse contains exactly one occurrence of
that matchup in the season. Repeated matchups remain unresolved rather than guessed.

Verified manual overrides and Phase 1 official-event recoveries are preserved.
The proposed regrade is built in memory and protected by a destructive-write
safety floor.
"""
from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wnba_alt_performance_tracker import stat_value, outcome, one_unit_profit

ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
REPORT = Path("data/dashboard/wnba_alt_strict_regrade.json")
WAREHOUSE_REPORT = Path("data/warehouse/wnba_alt_strict_regrade.json")
TRUSTED_SOURCES = {"manual_verified_override", "espn_schedule_event_phase1"}
FINAL = {"WIN", "LOSS", "PUSH", "VOID"}

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
    text = norm(value)
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    text = " ".join(text.split())
    return TEAM_ALIASES.get(text, text)


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
    game = str(value or "").strip()
    if "@" not in game:
        return frozenset()
    away, home = game.split("@", 1)
    parts = [team_norm(away), team_norm(home)]
    return frozenset(parts) if all(parts) and parts[0] != parts[1] else frozenset()


def team_pair(row: dict[str, Any]) -> frozenset[str]:
    pair = game_pair(row.get("game"))
    if pair:
        return pair
    pair = game_pair(row.get("opponent"))
    if pair:
        return pair
    team = team_norm(row.get("team"))
    opponent = team_norm(row.get("opponent"))
    if team and opponent and "@" not in str(row.get("opponent") or ""):
        return frozenset((team, opponent))
    return frozenset()


def record_identity(record: dict[str, Any]) -> str:
    return str(record.get("record_id") or record.get("game_id") or record.get("event_id") or record.get("game") or "")


def reset_warehouse_grade(row: dict[str, Any]) -> None:
    row["actual"] = None
    row["outcome"] = "PENDING"
    row["profit_loss"] = None
    row["graded_at_utc"] = None
    row["actual_source"] = None
    row["grading_reason"] = None
    for key in ("actual_record_id", "actual_game_id", "actual_game_date", "candidate_completed_games", "candidate_record_ids"):
        row.pop(key, None)


def emit_report(report: dict[str, Any]) -> None:
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    for path in (REPORT, WAREHOUSE_REPORT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


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

    now = datetime.now(timezone.utc).isoformat()
    stats = {
        "rows": len(history), "baseline_final": baseline_final, "trusted_preserved": 0,
        "strictly_graded": 0, "same_date_exact": 0, "unique_matchup_date_shift": 0,
        "no_player_game": 0, "archive_matchup_missing": 0, "warehouse_matchup_missing": 0,
        "matchup_mismatch": 0, "repeated_matchup_date_ambiguous": 0,
        "multiple_exact_matches": 0, "unique_player_date_fallback": 0, "stat_unavailable": 0,
    }
    mismatch_samples: list[dict[str, Any]] = []

    for row in history:
        source = str(row.get("actual_source") or "")
        if source in TRUSTED_SOURCES and str(row.get("outcome") or "").upper() in FINAL:
            stats["trusted_preserved"] += 1
            continue

        reset_warehouse_grade(row)
        player = norm(row.get("player"))
        snapshot_date = str(row.get("date") or "")[:10]
        wanted_pair = team_pair(row)
        same_date = by_player_date.get((player, snapshot_date), [])
        all_player = by_player.get(player, [])
        exact: list[dict[str, Any]] = []
        match_mode = ""

        if wanted_pair:
            same_exact = [r for r in same_date if team_pair(r) == wanted_pair]
            if len(same_exact) == 1:
                exact = same_exact
                match_mode = "same_date_exact"
                stats["same_date_exact"] += 1
            elif len(same_exact) > 1:
                row["grading_reason"] = "multiple completed player-games match archived wager on snapshot date"
                row["candidate_record_ids"] = [record_identity(r) for r in same_exact]
                stats["multiple_exact_matches"] += 1
                continue
            else:
                season_exact = [r for r in all_player if team_pair(r) == wanted_pair]
                unique_games: dict[str, dict[str, Any]] = {}
                for r in season_exact:
                    identity = str(r.get("game_id") or r.get("event_id") or f"{str(r.get('game_date') or '')[:10]}|{r.get('game')}")
                    unique_games[identity] = r
                season_exact = list(unique_games.values())
                if len(season_exact) == 1:
                    exact = season_exact
                    match_mode = "unique_matchup_date_shift"
                    stats["unique_matchup_date_shift"] += 1
                elif len(season_exact) > 1:
                    row["grading_reason"] = "repeated matchup across season; archive date cannot be shifted safely"
                    row["candidate_completed_games"] = [f"{str(r.get('game_date') or '')[:10]} {r.get('game')}" for r in season_exact]
                    row["candidate_record_ids"] = [record_identity(r) for r in season_exact]
                    stats["repeated_matchup_date_ambiguous"] += 1
                    continue
                else:
                    if not same_date:
                        stats["no_player_game"] += 1
                        row["grading_reason"] = "no completed player-game on snapshot date or elsewhere for archived matchup"
                    else:
                        stats["matchup_mismatch"] += 1
                        row["grading_reason"] = "completed player-game exists on snapshot date but no completed archived matchup found"
                        row["candidate_completed_games"] = [str(r.get("game") or "") for r in same_date]
                    if len(mismatch_samples) < 25:
                        mismatch_samples.append({
                            "date": snapshot_date, "player": row.get("player"), "archive_game": row.get("game"),
                            "wanted_pair": sorted(wanted_pair),
                            "same_date_candidates": [str(r.get("game") or "") for r in same_date],
                            "season_player_games": [f"{str(r.get('game_date') or '')[:10]} {r.get('game')}" for r in all_player[:30]],
                        })
                    continue
        else:
            stats["archive_matchup_missing"] += 1
            if len(same_date) == 1:
                exact = same_date
                match_mode = "unique_player_date_fallback"
                stats["unique_player_date_fallback"] += 1
            else:
                row["grading_reason"] = "archive matchup missing and player does not have exactly one completed game on snapshot date"
                row["candidate_record_ids"] = [record_identity(r) for r in same_date]
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
        row["actual"] = actual
        row["outcome"] = result
        row["profit_loss"] = one_unit_profit(result, row.get("best_odds"))
        row["graded_at_utc"] = now
        row["actual_source"] = "player_game_log_warehouse_strict_match"
        row["actual_record_id"] = record_identity(record)
        row["actual_game_id"] = record.get("game_id") or record.get("event_id")
        row["actual_game_date"] = str(record.get("game_date") or "")[:10]
        row["grading_match_mode"] = match_mode
        row["grading_reason"] = None if result != "PENDING" else "could not derive final outcome"
        if result != "PENDING":
            stats["strictly_graded"] += 1

    pending = sum(str(r.get("outcome") or "PENDING").upper() == "PENDING" for r in history)
    final = sum(str(r.get("outcome") or "").upper() in FINAL for r in history)
    stats.update({"proposed_final": final, "proposed_pending": pending})

    minimum_safe_final = int(baseline_final * 0.90)
    safe_to_apply = final >= minimum_safe_final
    report = {
        "generated_at_utc": now,
        "status": "PASS" if safe_to_apply else "BLOCKED",
        "safe_to_apply": safe_to_apply,
        "minimum_safe_final": minimum_safe_final,
        "stats": stats,
        "mismatch_samples": mismatch_samples,
        "identity_rule": "player + canonical matchup; prefer snapshot-date exact, otherwise allow only a single unique completed occurrence of that matchup across the player's season",
        "repeated_matchup_policy": "never guess among repeated completed matchups; leave pending for explicit game-id/date resolution",
        "odds_snapshot_policy": "raw odds schedule/game IDs are never accepted as completed-game truth",
    }
    emit_report(report)

    if not safe_to_apply:
        print("Strict ALT regrade blocked by safety guard:", stats)
        raise SystemExit(
            f"Refusing destructive archive rewrite: proposed final {final} < safety floor {minimum_safe_final} "
            f"from baseline {baseline_final}. See {REPORT}."
        )

    write_jsonl(ARCHIVE, history)
    print("Strict ALT regrade:", stats)


if __name__ == "__main__":
    main()
