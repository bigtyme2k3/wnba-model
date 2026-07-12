"""Snapshot, grade, and analyze ALT Streak candidates.

Snapshots preserve the pregame score, market, line, odds, components, and
matchup source. Grading uses only verified player game-log warehouse records.
Profit/loss is calculated at a flat one-unit stake from the snapshotted odds.
Closing-line value remains null unless a verified closing snapshot exists.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ALT = Path("data/dashboard/wnba_alt_streaks.json")
WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")
HISTORY = Path("data/history/wnba_alt_streak_history.jsonl")
OUTS = [Path("data/warehouse/wnba_alt_streak_performance.json"), Path("data/dashboard/wnba_alt_streak_performance.json")]


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def read_history() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if HISTORY.exists():
        for line in HISTORY.open(encoding="utf-8"):
            try:
                row = json.loads(line)
                if isinstance(row, dict): rows.append(row)
            except Exception:
                pass
    return rows


def write_history(rows: list[dict[str, Any]]) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def snapshot_key(row: dict[str, Any], target: str) -> str:
    return "|".join([
        target, norm(row.get("player")), str(row.get("stat") or "").upper(),
        str(row.get("side") or "").upper(), str(row.get("alt_line")), norm(row.get("best_book")),
    ])


def snapshot(target: str) -> dict[str, Any]:
    payload = load(ALT, {"rows": []})
    history = read_history()
    existing = {str(r.get("snapshot_id")) for r in history}
    added = duplicates = 0
    now = datetime.now(timezone.utc).isoformat()
    for row in payload.get("rows", []):
        if not isinstance(row, dict): continue
        snapshot_id = snapshot_key(row, target)
        if snapshot_id in existing:
            duplicates += 1; continue
        record = {
            "snapshot_id": snapshot_id, "date": target, "snapshotted_at_utc": now,
            "player": row.get("player"), "team": row.get("team"), "game": row.get("game"),
            "opponent": row.get("opponent"), "stat": row.get("stat"), "side": row.get("side"),
            "line": row.get("alt_line"), "line_type": row.get("line_type"),
            "american_odds": row.get("best_odds"), "sportsbook": row.get("best_book"),
            "streak_score": row.get("streak_score"), "streak_grade": row.get("streak_grade"),
            "streak_confidence": row.get("streak_confidence"), "streak_action": row.get("streak_action"),
            "risk_level": row.get("risk_level"), "expected_edge": row.get("expected_edge"),
            "l5_hits": row.get("l5_hits"), "l5_games": row.get("l5_games"),
            "l10_hits": row.get("l10_hits"), "l10_games": row.get("l10_games"),
            "season_hits": row.get("season_hits"), "season_games": row.get("season_games"),
            "opponent_rank": row.get("opponent_rank"), "opponent_rank_source": row.get("opponent_rank_source"),
            "score_components": row.get("score_components"), "score_weights": row.get("score_weights"),
            "closing_line": None, "closing_odds": None, "clv": None,
            "actual": None, "outcome": "PENDING", "profit_loss": 0.0, "graded_at_utc": None,
        }
        history.append(record); existing.add(snapshot_id); added += 1
    write_history(history)
    return {"added": added, "duplicates": duplicates, "total_history": len(history)}


def stat_value(record: dict[str, Any], stat: str) -> float | None:
    key = str(stat or "").upper().replace("THREES", "3PM").replace(" ", "_")
    scoring = record.get("scoring", {}) if isinstance(record.get("scoring"), dict) else {}
    fouls = record.get("fouls", {}) if isinstance(record.get("fouls"), dict) else {}
    box = record.get("boxscore", {}) if isinstance(record.get("boxscore"), dict) else {}
    derived = record.get("derived", {}) if isinstance(record.get("derived"), dict) else {}
    values = {
        "PTS": scoring.get("total_pts"), "Q1_PTS": scoring.get("q1_pts"), "Q2_PTS": scoring.get("q2_pts"),
        "Q3_PTS": scoring.get("q3_pts"), "Q4_PTS": scoring.get("q4_pts"),
        "1H_PTS": scoring.get("first_half_pts"), "2H_PTS": scoring.get("second_half_pts"),
        "FTM": scoring.get("ftm"), "FTA": scoring.get("fta"), "FT_PTS": scoring.get("free_throw_points"),
        "3PM": scoring.get("three_pm"), "REB": box.get("reb"), "OREB": box.get("oreb"),
        "DREB": box.get("dreb"), "AST": box.get("ast"), "STL": box.get("stl"),
        "BLK": box.get("blk"), "TOV": box.get("tov"), "PF": fouls.get("total_committed"),
        "SHOOTING_FOULS": fouls.get("shooting"), "OFFENSIVE_FOULS": fouls.get("offensive"),
        "TECHNICAL_FOULS": fouls.get("technical"), "FLAGRANT_FOULS": fouls.get("flagrant"),
        "PRA": derived.get("pra"), "PR": derived.get("pr"), "PA": derived.get("pa"), "RA": derived.get("ra"),
    }
    return num(values.get(key))


def outcome(side: str, actual: float | None, line: float | None) -> str:
    if actual is None or line is None: return "PENDING"
    if actual == line: return "PUSH"
    return "WIN" if (actual > line if side.upper() == "OVER" else actual < line) else "LOSS"


def unit_profit(result: str, odds: Any) -> float:
    price = num(odds)
    if result == "LOSS": return -1.0
    if result != "WIN" or price is None: return 0.0
    return 100.0 / abs(price) if price < 0 else price / 100.0


def grade() -> dict[str, Any]:
    history = read_history(); warehouse = load(WAREHOUSE, {"records": []})
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in warehouse.get("records", []):
        if not isinstance(record, dict): continue
        game_date = str(record.get("game_date") or "")[:10]
        if game_date and record.get("player"): index[(game_date, norm(record.get("player")))].append(record)
    graded = pending = 0
    for row in history:
        if row.get("outcome") in {"WIN", "LOSS", "PUSH", "VOID"}: continue
        matches = index.get((str(row.get("date")), norm(row.get("player"))), [])
        actual = None
        for record in matches:
            actual = stat_value(record, str(row.get("stat") or ""))
            if actual is not None: break
        result = outcome(str(row.get("side") or "OVER"), actual, num(row.get("line")))
        if result == "PENDING": pending += 1; continue
        row["actual"] = actual; row["outcome"] = result
        row["profit_loss"] = round(unit_profit(result, row.get("american_odds")), 4)
        row["graded_at_utc"] = datetime.now(timezone.utc).isoformat(); graded += 1
    write_history(history)
    return {"graded": graded, "pending": pending}


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    final = [r for r in rows if r.get("outcome") in {"WIN", "LOSS", "PUSH"}]
    wins = sum(r.get("outcome") == "WIN" for r in final); losses = sum(r.get("outcome") == "LOSS" for r in final)
    pushes = sum(r.get("outcome") == "PUSH" for r in final); decisions = wins + losses
    pnl = sum(num(r.get("profit_loss")) or 0 for r in final)
    return {"graded": len(final), "wins": wins, "losses": losses, "pushes": pushes,
            "win_rate": round(wins / decisions, 4) if decisions else None,
            "profit_loss_units": round(pnl, 4), "roi": round(pnl / decisions, 4) if decisions else None}


def grouped(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: groups[str(row.get(field) or "Unknown")].append(row)
    output = [{field: key, **summarize_group(values)} for key, values in groups.items()]
    output.sort(key=lambda r: (r.get("roi") is not None, r.get("roi") or -999, r.get("graded") or 0), reverse=True)
    return output


def score_band(score: Any) -> str:
    n = num(score) or 0
    if n >= 90: return "90-100"
    if n >= 85: return "85-89.9"
    if n >= 80: return "80-84.9"
    if n >= 75: return "75-79.9"
    if n >= 70: return "70-74.9"
    if n >= 60: return "60-69.9"
    return "Below 60"


def report(target: str) -> dict[str, Any]:
    rows = read_history()
    for row in rows: row["score_band"] = score_band(row.get("streak_score"))
    today = date.fromisoformat(target)
    windows = {}
    for days in (7, 14, 30):
        start = str(today - timedelta(days=days - 1))
        windows[f"last_{days}_days"] = summarize_group([r for r in rows if start <= str(r.get("date")) <= target])
    overall = summarize_group(rows)
    score_groups = grouped(rows, "score_band")
    profitable = [g for g in score_groups if (g.get("graded") or 0) >= 20 and (g.get("roi") or 0) > 0]
    threshold = profitable[0].get("score_band") if profitable else None
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target,
        "status": "ok", "summary": {**overall, "snapshots": len(rows), "pending": sum(r.get("outcome") == "PENDING" for r in rows), "recommended_threshold": threshold},
        "windows": windows, "by_grade": grouped(rows, "streak_grade"), "by_action": grouped(rows, "streak_action"),
        "by_score_band": score_groups, "by_stat": grouped(rows, "stat"), "by_side": grouped(rows, "side"),
        "by_sportsbook": grouped(rows, "sportsbook"), "by_matchup_source": grouped(rows, "opponent_rank_source"),
        "recent_results": sorted(rows, key=lambda r: (str(r.get("date")), str(r.get("graded_at_utc") or "")), reverse=True)[:100],
        "methodology": {"stake": "flat 1 unit", "grading_source": "verified player game-log warehouse", "clv_policy": "null until verified closing snapshot", "minimum_threshold_sample": 20},
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle: json.dump(payload, handle, indent=2, allow_nan=False)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("snapshot", "grade", "report", "all")); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args()
    if args.mode in {"snapshot", "all"}: print("ALT snapshot:", snapshot(args.date))
    if args.mode in {"grade", "all"}: print("ALT grading:", grade())
    if args.mode in {"report", "all"}: print("ALT performance:", report(args.date)["summary"])


if __name__ == "__main__": main()
