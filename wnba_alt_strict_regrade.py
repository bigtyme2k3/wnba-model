"""Strictly regrade ALT history against completed canonical player-games.

This repair removes the legacy grader behavior that selected the first player
record found for a snapshot date. A wager may only grade from the player-game
warehouse when the archived matchup and completed warehouse matchup agree.
Verified manual overrides and Phase 1 official-event recoveries are preserved.

Important: frozen ALT rows often have ``team`` unset and ``opponent`` containing
the full ``Away @ Home`` label. Therefore the canonical matchup is parsed from
``game`` first. ``team`` + ``opponent`` is only a fallback when both are actual
team names. Warehouse matchup labels may use either full franchise names or
mascot-only labels (for example ``Fever @ Aces``), so both forms normalize to
the same canonical franchise identity. The script builds the proposed regrade
in memory and refuses to replace the archive when strict matching would
catastrophically reduce the number of final grades.
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
    # Full/city shorthand.
    "la sparks": "los angeles sparks",
    "los angeles": "los angeles sparks",
    "ny liberty": "new york liberty",
    "new york": "new york liberty",
    "gs valkyries": "golden state valkyries",
    "golden state": "golden state valkyries",
    "lv aces": "las vegas aces",
    "las vegas": "las vegas aces",
    "washington": "washington mystics",
    "connecticut": "connecticut sun",
    "phoenix": "phoenix mercury",
    "atlanta": "atlanta dream",
    "dallas": "dallas wings",
    "seattle": "seattle storm",
    "chicago": "chicago sky",
    "minnesota": "minnesota lynx",
    "indiana": "indiana fever",
    "portland": "portland fire",
    "toronto": "toronto tempo",

    # Mascot-only labels emitted by portions of the historical warehouse.
    "sparks": "los angeles sparks",
    "liberty": "new york liberty",
    "valkyries": "golden state valkyries",
    "aces": "las vegas aces",
    "mystics": "washington mystics",
    "sun": "connecticut sun",
    "mercury": "phoenix mercury",
    "dream": "atlanta dream",
    "wings": "dallas wings",
    "storm": "seattle storm",
    "sky": "chicago sky",
    "lynx": "minnesota lynx",
    "fever": "indiana fever",
    "fire": "portland fire",
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
    # Canonical source first. ALT rows can have team=None and opponent=<full game>,
    # or a stale/mixed opponent field, so never let those override a valid game.
    pair = game_pair(row.get("game"))
    if pair:
        return pair

    # Some warehouse variants expose a matchup label under opponent.
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
    row.pop("actual_record_id", None)
    row.pop("actual_game_id", None)
    row.pop("actual_game_date", None)
    row.pop("candidate_completed_games", None)
    row.pop("candidate_record_ids", None)


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
    for record in records:
        player = norm(record.get("player"))
        game_date = str(record.get("game_date") or "")[:10]
        if player and game_date:
            by_player_date[(player, game_date)].append(record)

    now = datetime.now(timezone.utc).isoformat()
    stats = {
        "rows": len(history),
        "baseline_final": baseline_final,
        "trusted_preserved": 0,
        "strictly_graded": 0,
        "no_player_game": 0,
        "archive_matchup_missing": 0,
        "warehouse_matchup_missing": 0,
        "matchup_mismatch": 0,
        "multiple_exact_matches": 0,
        "unique_player_date_fallback": 0,
        "stat_unavailable": 0,
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
        candidates = by_player_date.get((player, snapshot_date), [])
        if not candidates:
            row["grading_reason"] = "no completed player-game on snapshot date"
            stats["no_player_game"] += 1
            continue

        wanted_pair = team_pair(row)
        candidate_pairs = [(r, team_pair(r)) for r in candidates]

        if wanted_pair:
            exact = [r for r, pair in candidate_pairs if pair and pair == wanted_pair]
            if not exact:
                missing_pairs = sum(not pair for _, pair in candidate_pairs)
                if missing_pairs == len(candidate_pairs):
                    stats["warehouse_matchup_missing"] += 1
                    row["grading_reason"] = "warehouse player-game has no canonical matchup label"
                else:
                    stats["matchup_mismatch"] += 1
                    row["grading_reason"] = "completed player-game exists but matchup does not match archived wager"
                row["candidate_completed_games"] = [str(r.get("game") or "") for r in candidates]
                if len(mismatch_samples) < 25:
                    mismatch_samples.append({
                        "date": snapshot_date,
                        "player": row.get("player"),
                        "archive_game": row.get("game"),
                        "archive_team": row.get("team"),
                        "archive_opponent": row.get("opponent"),
                        "wanted_pair": sorted(wanted_pair),
                        "candidate_games": [str(r.get("game") or "") for r in candidates],
                        "candidate_pairs": [sorted(pair) for _, pair in candidate_pairs],
                    })
                continue
        else:
            stats["archive_matchup_missing"] += 1
            if len(candidates) == 1:
                exact = candidates
                stats["unique_player_date_fallback"] += 1
            else:
                row["grading_reason"] = "archive matchup missing and player has multiple games on snapshot date"
                row["candidate_record_ids"] = [record_identity(r) for r in candidates]
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
        "identity_rule": "player + snapshot_date + canonical Away@Home team pair; mascot/city/full-name labels normalize to franchise identity; unique player/date only when archive matchup is absent",
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
