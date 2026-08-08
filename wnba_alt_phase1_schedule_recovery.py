"""Resolve safe pending ALT archive rows directly from completed official schedule games.

Phase 1 only handles schedule-audit rows classified as ``exact_date`` or
``unique_schedule_alias``. It uses the completed ESPN event selected by the
schedule audit, reads that event's box score, derives the frozen ALT stat actual,
and grades the existing archive row. Frozen pregame fields (date, line, side,
score, odds) are never changed.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
AUDIT = Path("data/dashboard/wnba_alt_schedule_audit.json")
REPORT = Path("data/dashboard/wnba_alt_phase1_schedule_recovery.json")
WAREHOUSE_REPORT = Path("data/warehouse/wnba_alt_phase1_schedule_recovery.json")
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"
FINAL = {"WIN", "LOSS", "PUSH", "VOID"}
SAFE = {"exact_date", "unique_schedule_alias"}


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


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


def row_key(row: dict[str, Any]) -> str:
    line = row.get("alt_line") if row.get("alt_line") is not None else row.get("line")
    return "|".join([
        str(row.get("date") or "")[:10],
        norm(row.get("player")),
        norm(row.get("stat")),
        norm(row.get("side")),
        str(line if line is not None else ""),
    ])


def fetch_summary(event_id: str) -> dict[str, Any]:
    url = f"{SUMMARY}?{urllib.parse.urlencode({'event': event_id})}"
    req = urllib.request.Request(url, headers={"User-Agent": "wnba-model/5.0 (+github-actions)"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def made(value: Any) -> float | None:
    text = str(value or "").strip()
    if "-" not in text:
        return num(text)
    return num(text.split("-", 1)[0])


def player_stats(payload: dict[str, Any], player_name: str) -> dict[str, float] | None:
    wanted = norm(player_name)
    for team_block in (payload.get("boxscore") or {}).get("players") or []:
        for stat_group in team_block.get("statistics") or []:
            labels = [str(x).strip().upper() for x in (stat_group.get("labels") or stat_group.get("names") or [])]
            for athlete_row in stat_group.get("athletes") or []:
                athlete = athlete_row.get("athlete") or {}
                name = athlete.get("displayName") or athlete.get("fullName") or ""
                if norm(name) != wanted:
                    continue
                values = athlete_row.get("stats") or []
                raw = {label: values[i] if i < len(values) else None for i, label in enumerate(labels)}
                pts = num(raw.get("PTS"))
                reb = num(raw.get("REB"))
                ast = num(raw.get("AST"))
                stl = num(raw.get("STL"))
                blk = num(raw.get("BLK"))
                fg3m = made(raw.get("3PT"))
                stats = {
                    "PTS": pts, "REB": reb, "AST": ast, "3PM": fg3m,
                    "STL": stl, "BLK": blk,
                }
                if pts is not None and ast is not None:
                    stats["PA"] = pts + ast
                if pts is not None and reb is not None:
                    stats["PR"] = pts + reb
                if reb is not None and ast is not None:
                    stats["RA"] = reb + ast
                if pts is not None and reb is not None and ast is not None:
                    stats["PRA"] = pts + reb + ast
                return {k: float(v) for k, v in stats.items() if v is not None}
    return None


def outcome(side: Any, actual: float, line: Any) -> str:
    threshold = num(line)
    if threshold is None:
        return "PENDING"
    if actual == threshold:
        return "PUSH"
    direction = str(side or "").upper()
    if direction == "OVER":
        return "WIN" if actual > threshold else "LOSS"
    if direction == "UNDER":
        return "WIN" if actual < threshold else "LOSS"
    return "VOID"


def profit(result: str, odds: Any) -> float | None:
    price = num(odds)
    if result in {"PUSH", "VOID"}:
        return 0.0
    if result == "LOSS":
        return -1.0
    if result != "WIN" or price in (None, 0):
        return None
    return round(100 / abs(price), 4) if price < 0 else round(price / 100, 4)


def completed_candidate(audit_row: dict[str, Any]) -> dict[str, Any] | None:
    classification = str(audit_row.get("classification") or "")
    candidates = [g for g in audit_row.get("candidate_games") or [] if isinstance(g, dict) and g.get("completed")]
    if classification == "exact_date":
        target = str(audit_row.get("date") or "")[:10]
        exact = [g for g in candidates if str(g.get("date") or "")[:10] == target]
        return exact[0] if len(exact) == 1 else None
    if classification == "unique_schedule_alias":
        suggested = str(audit_row.get("suggested_date") or "")[:10]
        selected = [g for g in candidates if str(g.get("date") or "")[:10] == suggested]
        return selected[0] if len(selected) == 1 else None
    return None


def main() -> None:
    history = read_jsonl(ARCHIVE)
    audit = load(AUDIT, {"rows": []})
    audit_map = {
        str(r.get("row_key")): r for r in audit.get("rows", [])
        if isinstance(r, dict) and str(r.get("classification") or "") in SAFE
    }
    pending = [r for r in history if str(r.get("outcome") or "PENDING").upper() not in FINAL]
    cache: dict[str, dict[str, Any]] = {}
    recovered: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in pending:
        key = row_key(row)
        audit_row = audit_map.get(key)
        if not audit_row:
            continue
        game = completed_candidate(audit_row)
        if not game or not game.get("event_id"):
            unresolved.append({"row_key": key, "reason": "safe schedule row has no unique completed event"})
            continue
        event_id = str(game["event_id"])
        try:
            payload = cache.setdefault(event_id, fetch_summary(event_id))
        except Exception as exc:
            unresolved.append({"row_key": key, "event_id": event_id, "reason": f"summary fetch failed: {exc}"})
            continue
        stats = player_stats(payload, str(row.get("player") or ""))
        stat = str(row.get("stat") or "").upper()
        actual = stats.get(stat) if stats else None
        if actual is None:
            unresolved.append({"row_key": key, "event_id": event_id, "reason": f"player/stat unavailable: {stat}"})
            continue
        line = row.get("alt_line") if row.get("alt_line") is not None else row.get("line")
        result = outcome(row.get("side"), actual, line)
        if result not in FINAL:
            unresolved.append({"row_key": key, "event_id": event_id, "reason": "could not derive final outcome"})
            continue
        row["actual"] = actual
        row["outcome"] = result
        row["profit_loss"] = profit(result, row.get("best_odds"))
        row["graded_at_utc"] = now
        row["actual_source"] = "espn_schedule_event_phase1"
        row["actual_event_id"] = event_id
        row["actual_game_date"] = str(game.get("date") or "")[:10]
        row["schedule_recovery_classification"] = audit_row.get("classification")
        row["grading_reason"] = None
        recovered.append({
            "row_key": key,
            "player": row.get("player"),
            "stat": stat,
            "actual": actual,
            "outcome": result,
            "archive_date": str(row.get("date") or "")[:10],
            "actual_game_date": row["actual_game_date"],
            "event_id": event_id,
            "classification": audit_row.get("classification"),
        })

    if recovered:
        write_jsonl(ARCHIVE, history)

    report = {
        "generated_at_utc": now,
        "safe_audit_rows": len(audit_map),
        "pending_before": len(pending),
        "recovered": len(recovered),
        "pending_after_direct_recovery": len(pending) - len(recovered),
        "by_classification": {
            name: sum(1 for r in recovered if r.get("classification") == name)
            for name in sorted(SAFE)
        },
        "recovered_rows": recovered,
        "unresolved_safe_rows": unresolved,
    }
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    for path in (REPORT, WAREHOUSE_REPORT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("safe_audit_rows", "pending_before", "recovered", "pending_after_direct_recovery", "by_classification")}, indent=2))


if __name__ == "__main__":
    main()
