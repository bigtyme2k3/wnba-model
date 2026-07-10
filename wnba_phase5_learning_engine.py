"""WNBA Phase 5 learning engine.

Builds the permanent graded-results dataset, calibration report, CLV analytics,
feature contribution summaries, and an automatic quality-controlled betting card.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

HISTORY_PATH = "data/history/wnba_model_history.jsonl"
BOX_PATH = "data/raw/boxscores_wehoop.csv"
DECISIONS_PATH = "data/warehouse/wnba_decision_engine_final.json"
PORTFOLIO_PATH = "data/warehouse/wnba_portfolio_optimizer_v2.json"
OUT_WAREHOUSE = "data/warehouse/wnba_phase5_learning.json"
OUT_DASHBOARD = "data/dashboard/wnba_phase5_learning.json"
GRADED_CSV = "data/history/wnba_graded_bets.csv"

SUPPORTED_STATS = {"PTS", "REB", "AST", "PRA", "PR", "PA", "RA", "3PM", "STL", "BLK", "TOV"}


def sf(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("’", "'").split())


def load_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except Exception:
                continue
    return rows


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(sanitize(row), separators=(",", ":"), allow_nan=False) + "\n")


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def load_boxscores() -> Dict[Tuple[str, str], Dict[str, Any]]:
    result: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if not os.path.exists(BOX_PATH):
        return result
    with open(BOX_PATH, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            game_date = str(row.get("game_date") or "")[:10]
            player = norm(row.get("player"))
            if game_date and player:
                result[(game_date, player)] = row
    return result


def actual_value(row: Dict[str, Any], stat: str) -> float | None:
    stat = str(stat or "").upper().replace("THREES", "3PM")
    if stat not in SUPPORTED_STATS:
        return None
    pts = sf(row.get("pts")); reb = sf(row.get("reb")); ast = sf(row.get("ast"))
    mapping = {
        "PTS": pts, "REB": reb, "AST": ast, "3PM": sf(row.get("threes")),
        "STL": sf(row.get("stl")), "BLK": sf(row.get("blk")), "TOV": sf(row.get("tov")),
        "PRA": pts + reb + ast, "PR": pts + reb, "PA": pts + ast, "RA": reb + ast,
    }
    return mapping.get(stat)


def grade(signal: str, actual: float, line: float) -> str:
    side = str(signal or "").upper()
    if actual == line:
        return "PUSH"
    if side in {"OVER", "YES"}:
        return "WIN" if actual > line else "LOSS"
    if side in {"UNDER", "NO"}:
        return "WIN" if actual < line else "LOSS"
    return "UNRESOLVED"


def american_profit(odds: float, stake: float = 1.0) -> float:
    if odds == 0:
        odds = -110
    return stake * (100 / abs(odds)) if odds < 0 else stake * (odds / 100)


def enrich_history(history: List[Dict[str, Any]], actuals: Dict[Tuple[str, str], Dict[str, Any]]) -> int:
    changed = 0
    for row in history:
        if row.get("outcome") in {"WIN", "LOSS", "PUSH"}:
            continue
        game_date = str(row.get("date") or "")[:10]
        actual_row = actuals.get((game_date, norm(row.get("player"))))
        if not actual_row:
            continue
        actual = actual_value(actual_row, row.get("stat"))
        if actual is None:
            continue
        line = sf(row.get("line"), float("nan"))
        if not math.isfinite(line):
            continue
        outcome = grade(row.get("signal"), actual, line)
        if outcome == "UNRESOLVED":
            continue
        row["actual"] = actual
        row["outcome"] = outcome
        row["graded_at_utc"] = datetime.now(timezone.utc).isoformat()
        row["opponent"] = actual_row.get("opponent")
        row["opponent_abbr"] = actual_row.get("opponent_abbr")
        changed += 1
    return changed


def decision_lookup() -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    payload = load_json(DECISIONS_PATH, {})
    result = {}
    for row in payload.get("top_decisions", []) or []:
        key = (norm(row.get("player")), str(row.get("stat") or "").upper(), str(row.get("line") or ""))
        result[key] = row
    return result


def merge_decision_fields(history: List[Dict[str, Any]]) -> None:
    lookup = decision_lookup()
    for row in history:
        key = (norm(row.get("player")), str(row.get("stat") or "").upper(), str(row.get("line") or ""))
        source = lookup.get(key)
        if not source:
            continue
        for field in ["confidence", "final_score", "simulation_probability", "american_odds", "sportsbook", "ev_pct", "edge_pct", "final_action", "book_count", "history_games"]:
            if row.get(field) in [None, ""] and source.get(field) not in [None, ""]:
                row[field] = source.get(field)


def calibration(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    bins = [(50, 55), (55, 60), (60, 65), (65, 70), (70, 75), (75, 80), (80, 85), (85, 90), (90, 95), (95, 101)]
    output = []
    brier_parts = []
    for low, high in bins:
        rows = []
        for row in history:
            if row.get("outcome") not in {"WIN", "LOSS"}:
                continue
            score = sf(row.get("confidence", row.get("final_score", row.get("consensus_score"))), -1)
            if low <= score < high:
                rows.append(row)
        wins = sum(1 for row in rows if row.get("outcome") == "WIN")
        n = len(rows)
        predicted = ((low + min(high, 100)) / 2) / 100
        actual = wins / n if n else None
        if n:
            brier_parts.extend((predicted - (1 if row.get("outcome") == "WIN" else 0)) ** 2 for row in rows)
        output.append({"bin": f"{low}-{min(high-1,100)}", "n": n, "predicted_rate": round(predicted, 3), "actual_rate": round(actual, 3) if actual is not None else None, "wins": wins, "losses": n - wins})
    return {"bins": output, "brier_score": round(sum(brier_parts) / len(brier_parts), 4) if brier_parts else None, "graded_binary_rows": len(brier_parts)}


def performance(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    graded = [row for row in history if row.get("outcome") in {"WIN", "LOSS", "PUSH"}]
    wins = sum(row.get("outcome") == "WIN" for row in graded)
    losses = sum(row.get("outcome") == "LOSS" for row in graded)
    pushes = sum(row.get("outcome") == "PUSH" for row in graded)
    profit = 0.0
    for row in graded:
        odds = sf(row.get("american_odds"), -110)
        if row.get("outcome") == "WIN":
            profit += american_profit(odds)
        elif row.get("outcome") == "LOSS":
            profit -= 1
    risked = wins + losses
    clv_rows = [sf(row.get("clv")) for row in graded if row.get("clv") not in [None, ""]]
    return {
        "graded": len(graded), "wins": wins, "losses": losses, "pushes": pushes,
        "win_rate": round(wins / risked, 4) if risked else None,
        "units_profit": round(profit, 3), "roi": round(profit / risked, 4) if risked else None,
        "clv_samples": len(clv_rows), "average_clv": round(sum(clv_rows) / len(clv_rows), 3) if clv_rows else None,
        "positive_clv_rate": round(sum(v > 0 for v in clv_rows) / len(clv_rows), 4) if clv_rows else None,
    }


def grouped_performance(history: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in history:
        if row.get("outcome") in {"WIN", "LOSS", "PUSH"}:
            groups[str(row.get(field) or "UNKNOWN")].append(row)
    rows = []
    for name, items in groups.items():
        stats = performance(items)
        rows.append({field: name, **stats})
    rows.sort(key=lambda item: (item.get("graded", 0), item.get("roi") or -999), reverse=True)
    return rows


def feature_importance(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    features = ["simulation_probability", "consensus_score", "edge_pct", "ev_pct", "book_count", "history_games"]
    binary = [row for row in history if row.get("outcome") in {"WIN", "LOSS"}]
    result = []
    for feature in features:
        pairs = [(sf(row.get(feature), float("nan")), 1 if row.get("outcome") == "WIN" else 0) for row in binary]
        pairs = [(x, y) for x, y in pairs if math.isfinite(x)]
        if len(pairs) < 5:
            result.append({"feature": feature, "samples": len(pairs), "importance": None, "direction": "insufficient_data"})
            continue
        xs = [x for x, _ in pairs]; ys = [y for _, y in pairs]
        mx = sum(xs)/len(xs); my = sum(ys)/len(ys)
        cov = sum((x-mx)*(y-my) for x,y in pairs)
        vx = math.sqrt(sum((x-mx)**2 for x in xs)); vy = math.sqrt(sum((y-my)**2 for y in ys))
        corr = cov/(vx*vy) if vx and vy else 0
        result.append({"feature": feature, "samples": len(pairs), "importance": round(abs(corr), 4), "direction": "positive" if corr > 0 else "negative" if corr < 0 else "neutral"})
    result.sort(key=lambda item: item.get("importance") or -1, reverse=True)
    return result


def write_graded_csv(history: List[Dict[str, Any]]) -> None:
    fields = ["date", "player", "team", "game", "stat", "signal", "line", "pred", "actual", "outcome", "american_odds", "sportsbook", "confidence", "final_score", "simulation_probability", "ev_pct", "edge_pct", "closing_line", "clv", "opponent", "opponent_abbr"]
    os.makedirs(os.path.dirname(GRADED_CSV), exist_ok=True)
    with open(GRADED_CSV, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in history:
            if row.get("outcome") in {"WIN", "LOSS", "PUSH"}:
                writer.writerow({field: row.get(field) for field in fields})


def build(target: str) -> Dict[str, Any]:
    history = read_jsonl(HISTORY_PATH)
    merge_decision_fields(history)
    changed = enrich_history(history, load_boxscores())
    write_jsonl(HISTORY_PATH, history)
    write_graded_csv(history)

    perf = performance(history)
    cal = calibration(history)
    portfolio = load_json(PORTFOLIO_PATH, {})
    card = portfolio.get("recommended_card", []) or []
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "learning" if perf["graded"] < 50 else "active",
        "newly_graded": changed,
        "history_rows": len(history),
        "performance": perf,
        "calibration": cal,
        "feature_importance": feature_importance(history),
        "performance_by_stat": grouped_performance(history, "stat")[:20],
        "performance_by_action": grouped_performance(history, "final_action")[:10],
        "performance_by_book": grouped_performance(history, "sportsbook")[:15],
        "automatic_card": card,
        "card_summary": portfolio.get("summary", {}),
        "learning_readiness": {
            "minimum_for_basic_calibration": 50,
            "minimum_for_feature_weight_updates": 200,
            "graded_rows": perf["graded"],
            "calibration_ready": perf["graded"] >= 50,
            "feature_learning_ready": perf["graded"] >= 200,
        },
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in [OUT_WAREHOUSE, OUT_DASHBOARD]:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(sanitize(report), handle, indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    report = build(args.date)
    print(json.dumps({"status": report["status"], "newly_graded": report["newly_graded"], "performance": report["performance"], "learning_readiness": report["learning_readiness"]}, indent=2))


if __name__ == "__main__":
    main()
