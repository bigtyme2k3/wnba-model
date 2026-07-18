"""Archive and grade WNBA spread/totals predictions.

Every pregame model forecast is stored, including PASS decisions. Grading is
idempotent and uses final scores from current master/live result payloads when
available.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

LEDGER = Path("data/history/wnba_game_predictions.jsonl")
DASH = Path("data/dashboard/wnba_game_predictions_ledger.json")
WAREHOUSE = Path("data/warehouse/wnba_game_predictions_ledger.json")


def load(path: str | Path, default: Any) -> Any:
    try:
        p = Path(path)
        return json.load(p.open(encoding="utf-8")) if p.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def read_ledger() -> list[dict[str, Any]]:
    out = []
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict): out.append(row)
            except Exception:
                pass
    return out


def write_ledger(rows: list[dict[str, Any]]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def game_name(row: dict[str, Any]) -> str:
    if row.get("game"): return str(row["game"])
    away = row.get("away_team") or row.get("away"); home = row.get("home_team") or row.get("home")
    return f"{away} @ {home}" if away and home else ""


def archive(target: str) -> dict[str, Any]:
    model = load("data/dashboard/wnba_game_market_model.json", {})
    games = model.get("games", []) if isinstance(model, dict) else []
    ledger = read_ledger(); existing = {(r.get("target_date"), norm(r.get("game"))) for r in ledger}
    captured = datetime.now(timezone.utc).isoformat(); added = 0
    for game in games:
        key = (target, norm(game.get("game")))
        if not key[1] or key in existing: continue
        ledger.append({
            "prediction_id": f"{target}|{key[1]}", "target_date": target, "game": game.get("game"),
            "start_time": game.get("start_time"), "captured_at_utc": captured,
            "away_team": game.get("away_team"), "home_team": game.get("home_team"),
            "projected_away_score": game.get("projected_away_score"), "projected_home_score": game.get("projected_home_score"),
            "projected_margin": game.get("projected_margin"), "projected_total": game.get("projected_total"),
            "market_spread": game.get("market_spread"), "market_total": game.get("market_total"),
            "spread_edge": game.get("spread_edge"), "total_edge": game.get("total_edge"),
            "spread_pick": game.get("spread_pick"), "spread_recommendation": game.get("spread_recommendation"),
            "total_pick": game.get("total_pick"), "total_recommendation": game.get("total_recommendation"),
            "spread_probability": game.get("spread_probability"), "total_probability": game.get("total_probability"),
            "spread_source": game.get("spread_source"), "total_source": game.get("total_source"),
            "status": "PENDING", "graded": False,
        }); existing.add(key); added += 1
    write_ledger(ledger); return build_report(ledger, target, {"archived_this_run": added})


def possible_result_rows() -> list[dict[str, Any]]:
    candidates = [
        "data/dashboard/wnba_master.json", "data/dashboard/wnba_live_games.json",
        "data/dashboard/wnba_results.json", "data/raw/wnba_live_games.json",
        "data/raw/wnba_scores.json", "data/raw/games_today.json",
    ]
    out = []
    for path in candidates:
        payload = load(path, {})
        if isinstance(payload, list): out.extend(x for x in payload if isinstance(x, dict))
        elif isinstance(payload, dict):
            for key in ("games", "results", "recent_results", "scores"):
                value = payload.get(key)
                if isinstance(value, list): out.extend(x for x in value if isinstance(x, dict))
    return out


def final_score(row: dict[str, Any]) -> tuple[float, float] | None:
    status = str(row.get("status") or row.get("state") or row.get("game_status") or "").upper()
    finalish = status in {"FINAL", "FINAL/OT", "COMPLETED", "POST"} or bool(row.get("final"))
    away = num(row.get("away_score", row.get("away_points"))); home = num(row.get("home_score", row.get("home_points")))
    if away is None and isinstance(row.get("away"), dict): away = num(row["away"].get("score"))
    if home is None and isinstance(row.get("home"), dict): home = num(row["home"].get("score"))
    if away is None or home is None or not finalish: return None
    return away, home


def grade_spread(pred: dict[str, Any], away_score: float, home_score: float) -> str:
    rec = str(pred.get("spread_recommendation") or "PASS").upper()
    if rec == "PASS": return "PASS"
    spread = num(pred.get("market_spread"))
    if spread is None: return "VOID"
    home_cover_margin = (home_score + spread) - away_score
    if home_cover_margin == 0: return "PUSH"
    home = norm(pred.get("home_team")); picked_home = norm(rec) == home
    return "WIN" if (home_cover_margin > 0) == picked_home else "LOSS"


def grade_total(pred: dict[str, Any], away_score: float, home_score: float) -> str:
    rec = str(pred.get("total_recommendation") or "PASS").upper(); line = num(pred.get("market_total"))
    if rec == "PASS": return "PASS"
    if line is None: return "VOID"
    actual = away_score + home_score
    if actual == line: return "PUSH"
    return "WIN" if (actual > line and rec == "OVER") or (actual < line and rec == "UNDER") else "LOSS"


def grade(target: str) -> dict[str, Any]:
    ledger = read_ledger(); results = possible_result_rows(); by_game = {norm(game_name(r)): r for r in results if game_name(r)}; graded = 0
    for row in ledger:
        if row.get("target_date") != target or row.get("graded"): continue
        actual_row = by_game.get(norm(row.get("game"))); score = final_score(actual_row or {})
        if not score: continue
        away, home = score; row.update({
            "actual_away_score": away, "actual_home_score": home,
            "actual_margin": round(home-away, 2), "actual_total": round(home+away, 2),
            "margin_error": round(abs((num(row.get("projected_margin")) or 0) - (home-away)), 2),
            "total_error": round(abs((num(row.get("projected_total")) or 0) - (home+away)), 2),
            "spread_result": grade_spread(row, away, home), "total_result": grade_total(row, away, home),
            "graded": True, "status": "GRADED", "graded_at_utc": datetime.now(timezone.utc).isoformat(),
        }); graded += 1
    write_ledger(ledger); return build_report(ledger, target, {"graded_this_run": graded})


def build_report(ledger: list[dict[str, Any]], target: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = [r for r in ledger if r.get("target_date") == target]
    graded = [r for r in ledger if r.get("graded")]
    def record(field: str) -> dict[str, int]:
        vals = [str(r.get(field)) for r in graded if r.get(field) not in {None, "PASS", "VOID"}]
        return {k.lower(): vals.count(k) for k in ("WIN", "LOSS", "PUSH")}
    spread = record("spread_result"); total = record("total_result")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target, "status": "ok",
        "summary": {"today_predictions": len(rows), "all_predictions": len(ledger), "graded_games": len(graded),
                    "pending_today": sum(not r.get("graded") for r in rows), "spread_record": spread, "total_record": total,
                    "avg_margin_error": round(sum(num(r.get("margin_error")) or 0 for r in graded)/len(graded), 2) if graded else None,
                    "avg_total_error": round(sum(num(r.get("total_error")) or 0 for r in graded)/len(graded), 2) if graded else None,
                    **(extra or {})},
        "today": rows, "recent_graded": sorted(graded, key=lambda r: str(r.get("graded_at_utc") or ""), reverse=True)[:25],
    }
    for path in (WAREHOUSE, DASH):
        path.parent.mkdir(parents=True, exist_ok=True); json.dump(report, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("action", choices=["archive", "grade", "report"]); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args()
    ledger = read_ledger()
    report = archive(args.date) if args.action == "archive" else grade(args.date) if args.action == "grade" else build_report(ledger, args.date)
    print("Game predictions ledger:", report["summary"])


if __name__ == "__main__": main()
