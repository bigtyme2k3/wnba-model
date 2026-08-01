"""Reconcile every archived ALT prediction into exactly one grading category.

Produces machine-readable warehouse/dashboard reports plus a CSV of every archive
row and its reconciliation status. This step is diagnostic only; it does not
change grading outcomes or archive history.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
JSON_OUTPUTS = [
    Path("data/warehouse/wnba_alt_archive_reconciliation.json"),
    Path("data/dashboard/wnba_alt_archive_reconciliation.json"),
]
CSV_OUTPUT = Path("data/warehouse/wnba_alt_archive_reconciliation.csv")
SUPPORTED_STATS = {
    "PTS", "Q1_PTS", "Q2_PTS", "Q3_PTS", "Q4_PTS", "1H_PTS", "2H_PTS",
    "FTM", "FTA", "FT_PTS", "3PM", "REB", "OREB", "DREB", "AST", "STL",
    "BLK", "TOV", "PF", "SHOOTING_FOULS", "OFFENSIVE_FOULS",
    "TECHNICAL_FOULS", "FLAGRANT_FOULS", "PRA", "PR", "PA", "RA",
}
FINAL_OUTCOMES = {"WIN", "LOSS", "PUSH", "VOID"}


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    malformed = 0
    if not path.exists():
        return rows, malformed
    for line in path.open(encoding="utf-8"):
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
            else:
                malformed += 1
        except Exception:
            malformed += 1
    return rows, malformed


def stat_key(value: Any) -> str:
    return str(value or "").upper().replace("THREES", "3PM").replace(" ", "_")


def record_has_stat(record: dict[str, Any], stat: str) -> bool:
    scoring = record.get("scoring") if isinstance(record.get("scoring"), dict) else {}
    box = record.get("boxscore") if isinstance(record.get("boxscore"), dict) else {}
    fouls = record.get("fouls") if isinstance(record.get("fouls"), dict) else {}
    derived = record.get("derived") if isinstance(record.get("derived"), dict) else {}
    source = {
        "PTS": scoring.get("total_pts"), "Q1_PTS": scoring.get("q1_pts"),
        "Q2_PTS": scoring.get("q2_pts"), "Q3_PTS": scoring.get("q3_pts"),
        "Q4_PTS": scoring.get("q4_pts"), "1H_PTS": scoring.get("first_half_pts"),
        "2H_PTS": scoring.get("second_half_pts"), "FTM": scoring.get("ftm"),
        "FTA": scoring.get("fta"), "FT_PTS": scoring.get("free_throw_points"),
        "3PM": scoring.get("three_pm"), "REB": box.get("reb"),
        "OREB": box.get("oreb"), "DREB": box.get("dreb"), "AST": box.get("ast"),
        "STL": box.get("stl"), "BLK": box.get("blk"), "TOV": box.get("tov"),
        "PF": fouls.get("total_committed"), "SHOOTING_FOULS": fouls.get("shooting"),
        "OFFENSIVE_FOULS": fouls.get("offensive"), "TECHNICAL_FOULS": fouls.get("technical"),
        "FLAGRANT_FOULS": fouls.get("flagrant"), "PRA": derived.get("pra"),
        "PR": derived.get("pr"), "PA": derived.get("pa"), "RA": derived.get("ra"),
    }
    return source.get(stat) is not None


def classify(
    row: dict[str, Any],
    duplicate_ids: set[str],
    exact_index: dict[tuple[str, str], list[dict[str, Any]]],
    player_dates: dict[str, set[str]],
    dates: set[str],
) -> tuple[str, str]:
    candidate_id = str(row.get("candidate_id") or "")
    if candidate_id and candidate_id in duplicate_ids:
        return "duplicate_prediction", "candidate_id appears more than once"

    required = ("player", "date", "stat", "side", "alt_line")
    missing = [field for field in required if row.get(field) in (None, "")]
    if missing:
        return "data_error", "missing required fields: " + ", ".join(missing)

    outcome = str(row.get("outcome") or "PENDING").upper()
    if outcome in FINAL_OUTCOMES:
        return "graded", f"final outcome {outcome}"

    stat = stat_key(row.get("stat"))
    if stat not in SUPPORTED_STATS:
        return "stat_mapping_failed", f"unsupported stat {stat or 'blank'}"

    player = norm(row.get("player"))
    target_date = str(row.get("date") or "")[:10]
    candidates = exact_index.get((player, target_date), [])
    if candidates:
        if any(record_has_stat(record, stat) for record in candidates):
            return "awaiting_actuals", "matching player-game row exists; grading rerun required"
        return "stat_mapping_failed", "matching player-game row lacks requested stat"

    if player in player_dates:
        return "game_mapping_failed", "player exists in actuals warehouse but not on archive date"
    if target_date in dates:
        return "player_mapping_failed", "actual rows exist for archive date but player was not matched"
    return "awaiting_actuals", "no actual rows loaded for archive date"


def main() -> None:
    archive, malformed_lines = read_jsonl(ARCHIVE)
    logs = load_json(LOGS, {"records": []})
    records = [r for r in logs.get("records", []) if isinstance(r, dict)]

    exact_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    player_dates: dict[str, set[str]] = defaultdict(set)
    dates: set[str] = set()
    for record in records:
        player = norm(record.get("player"))
        game_date = str(record.get("game_date") or "")[:10]
        if not player or not game_date:
            continue
        exact_index[(player, game_date)].append(record)
        player_dates[player].add(game_date)
        dates.add(game_date)

    id_counts = Counter(str(row.get("candidate_id") or "") for row in archive if row.get("candidate_id"))
    duplicate_ids = {cid for cid, count in id_counts.items() if count > 1}

    detail: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row_number, row in enumerate(archive, start=1):
        category, reason = classify(row, duplicate_ids, exact_index, player_dates, dates)
        counts[category] += 1
        detail.append({
            "row_number": row_number,
            "candidate_id": row.get("candidate_id"),
            "date": row.get("date"),
            "player": row.get("player"),
            "game": row.get("game"),
            "stat": row.get("stat"),
            "side": row.get("side"),
            "line": row.get("alt_line"),
            "outcome": row.get("outcome"),
            "category": category,
            "reason": reason,
            "existing_grading_reason": row.get("grading_reason"),
        })

    ordered_categories = [
        "graded", "awaiting_actuals", "player_mapping_failed", "game_mapping_failed",
        "stat_mapping_failed", "postponed_cancelled", "duplicate_prediction", "data_error",
    ]
    summary_counts = {key: int(counts.get(key, 0)) for key in ordered_categories}
    accounted = sum(summary_counts.values())
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if accounted == len(archive) and malformed_lines == 0 else "review",
        "summary": {
            "total_archived": len(archive),
            **summary_counts,
            "malformed_archive_lines": malformed_lines,
            "total_accounted_for": accounted,
            "fully_accounted": accounted == len(archive),
            "immediately_gradable": summary_counts["awaiting_actuals"] if summary_counts["awaiting_actuals"] else 0,
        },
        "definitions": {
            "graded": "Archive row already has WIN, LOSS, PUSH, or VOID.",
            "awaiting_actuals": "No usable actual is currently available, or a matching row now exists and grading should be rerun.",
            "player_mapping_failed": "Actual rows exist for the date, but the archived player did not match.",
            "game_mapping_failed": "Player exists in the warehouse, but not on the archived date.",
            "stat_mapping_failed": "The stat is unsupported or absent from a matched player-game row.",
            "postponed_cancelled": "Reserved for explicit schedule status when available.",
            "duplicate_prediction": "The same candidate_id occurs more than once.",
            "data_error": "Required archive fields are missing or malformed.",
        },
        "records": detail,
    }

    for output in JSON_OUTPUTS:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")

    CSV_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail[0].keys()) if detail else ["row_number", "category", "reason"])
        writer.writeheader()
        writer.writerows(detail)

    print(json.dumps(report["summary"], indent=2))
    if accounted != len(archive):
        raise SystemExit("Archive reconciliation did not account for every parsed row")


if __name__ == "__main__":
    main()
