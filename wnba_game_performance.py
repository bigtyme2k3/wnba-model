"""Build game-level performance analytics from the frozen prediction ledger.

The ledger is immutable pregame evidence. This module only evaluates frozen
forecasts after final scores are attached; it does not retrain or rewrite old
predictions.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER = Path("data/history/wnba_game_predictions.jsonl")
OUTPUTS = [
    Path("data/dashboard/wnba_game_performance.json"),
    Path("data/warehouse/wnba_game_performance.json"),
]


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
            except Exception:
                pass
    return out


def rate(wins: int, losses: int) -> float | None:
    decisions = wins + losses
    return round(wins / decisions, 4) if decisions else None


def market_summary(data: list[dict[str, Any]], result_key: str, rec_key: str) -> dict[str, Any]:
    graded = [r for r in data if r.get("graded") and r.get(result_key) not in {None, "PASS", "VOID"}]
    wins = sum(r.get(result_key) == "WIN" for r in graded)
    losses = sum(r.get(result_key) == "LOSS" for r in graded)
    pushes = sum(r.get(result_key) == "PUSH" for r in graded)
    sides: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "pushes": 0})
    for row in graded:
        side = str(row.get(rec_key) or "UNKNOWN")
        result = str(row.get(result_key))
        if result == "WIN":
            sides[side]["wins"] += 1
        elif result == "LOSS":
            sides[side]["losses"] += 1
        elif result == "PUSH":
            sides[side]["pushes"] += 1
    return {
        "record": {"wins": wins, "losses": losses, "pushes": pushes},
        "hit_rate": rate(wins, losses),
        "by_side": [
            {"side": key, **value, "hit_rate": rate(value["wins"], value["losses"])}
            for key, value in sorted(sides.items())
        ],
    }


def spread_pick_outcome(row: dict[str, Any]) -> str | None:
    pick = str(row.get("spread_pick") or "").strip()
    spread = num(row.get("market_spread"))
    away = num(row.get("actual_away_score"))
    home = num(row.get("actual_home_score"))
    if not pick or pick.upper() == "PASS" or spread is None or away is None or home is None:
        return None
    home_cover = (home + spread) - away
    if abs(home_cover) < 1e-9:
        return "PUSH"
    picked_home = norm(pick) == norm(row.get("home_team"))
    return "WIN" if (home_cover > 0) == picked_home else "LOSS"


def total_pick_outcome(row: dict[str, Any]) -> str | None:
    pick = str(row.get("total_pick") or "").upper().strip()
    line = num(row.get("market_total"))
    actual = num(row.get("actual_total"))
    if pick not in {"OVER", "UNDER"} or line is None or actual is None:
        return None
    if abs(actual - line) < 1e-9:
        return "PUSH"
    return "WIN" if (pick == "OVER" and actual > line) or (pick == "UNDER" and actual < line) else "LOSS"


def calibration(data: list[dict[str, Any]], probability_key: str, outcome_fn) -> dict[str, Any]:
    observations: list[tuple[float, int]] = []
    for row in data:
        if not row.get("graded"):
            continue
        probability = num(row.get(probability_key))
        outcome = outcome_fn(row)
        if probability is None or outcome not in {"WIN", "LOSS"}:
            continue
        observations.append((max(0.0, min(1.0, probability)), 1 if outcome == "WIN" else 0))

    brier = round(sum((p - y) ** 2 for p, y in observations) / len(observations), 4) if observations else None
    buckets = []
    for low, high in ((0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.80), (0.80, 1.01)):
        values = [(p, y) for p, y in observations if low <= p < high]
        if not values:
            continue
        avg_probability = sum(p for p, _ in values) / len(values)
        hit_rate = sum(y for _, y in values) / len(values)
        buckets.append({
            "label": f"{int(low*100)}-{int(min(high,1.0)*100)}%",
            "samples": len(values),
            "avg_probability": round(avg_probability, 4),
            "hit_rate": round(hit_rate, 4),
            "calibration_gap": round(hit_rate - avg_probability, 4),
        })
    return {"samples": len(observations), "brier_score": brier, "buckets": buckets}


def edge_buckets(data: list[dict[str, Any]], edge_key: str, outcome_fn) -> list[dict[str, Any]]:
    groups = [(0, 2.5), (2.5, 5), (5, 8), (8, 12), (12, float("inf"))]
    out = []
    for low, high in groups:
        decisions = []
        for row in data:
            if not row.get("graded"):
                continue
            edge = num(row.get(edge_key))
            result = outcome_fn(row)
            if edge is None or result not in {"WIN", "LOSS", "PUSH"}:
                continue
            magnitude = abs(edge)
            if low <= magnitude < high:
                decisions.append(result)
        if not decisions:
            continue
        wins = decisions.count("WIN")
        losses = decisions.count("LOSS")
        pushes = decisions.count("PUSH")
        out.append({
            "label": f"{low:g}-{high:g}" if math.isfinite(high) else f"{low:g}+",
            "samples": len(decisions),
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "hit_rate": rate(wins, losses),
        })
    return out


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def build() -> dict[str, Any]:
    data = rows()
    graded = [r for r in data if r.get("graded")]

    margin_abs: list[float] = []
    total_abs: list[float] = []
    margin_signed: list[float] = []
    total_signed: list[float] = []
    away_score_abs: list[float] = []
    home_score_abs: list[float] = []
    winner_correct = 0
    winner_decisions = 0

    enriched = []
    for row in graded:
        item = dict(row)
        projected_margin = num(row.get("projected_margin"))
        actual_margin = num(row.get("actual_margin"))
        projected_total = num(row.get("projected_total"))
        actual_total = num(row.get("actual_total"))
        projected_away = num(row.get("projected_away_score"))
        projected_home = num(row.get("projected_home_score"))
        actual_away = num(row.get("actual_away_score"))
        actual_home = num(row.get("actual_home_score"))

        if projected_margin is not None and actual_margin is not None:
            signed = projected_margin - actual_margin
            margin_signed.append(signed)
            margin_abs.append(abs(signed))
            item["margin_bias"] = round(signed, 2)
        if projected_total is not None and actual_total is not None:
            signed = projected_total - actual_total
            total_signed.append(signed)
            total_abs.append(abs(signed))
            item["total_bias"] = round(signed, 2)
        if projected_away is not None and actual_away is not None:
            away_score_abs.append(abs(projected_away - actual_away))
        if projected_home is not None and actual_home is not None:
            home_score_abs.append(abs(projected_home - actual_home))

        predicted_winner = None
        actual_winner = None
        if projected_margin is not None and abs(projected_margin) > 1e-9:
            predicted_winner = row.get("home_team") if projected_margin > 0 else row.get("away_team")
        if actual_margin is not None and abs(actual_margin) > 1e-9:
            actual_winner = row.get("home_team") if actual_margin > 0 else row.get("away_team")
        if predicted_winner and actual_winner:
            winner_decisions += 1
            correct = norm(predicted_winner) == norm(actual_winner)
            winner_correct += int(correct)
            item["predicted_winner"] = predicted_winner
            item["actual_winner"] = actual_winner
            item["winner_result"] = "WIN" if correct else "LOSS"

        item["spread_pick_result"] = spread_pick_outcome(row)
        item["total_pick_result"] = total_pick_outcome(row)
        enriched.append(item)

    spread = market_summary(data, "spread_result", "spread_recommendation")
    total = market_summary(data, "total_result", "total_recommendation")
    spread_cal = calibration(data, "spread_probability", spread_pick_outcome)
    total_cal = calibration(data, "total_probability", total_pick_outcome)

    over_games = 0
    under_games = 0
    for row in graded:
        actual = num(row.get("actual_total"))
        market = num(row.get("market_total"))
        if actual is None or market is None:
            continue
        over_games += actual > market
        under_games += actual < market

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "summary": {
            "archived_games": len(data),
            "graded_games": len(graded),
            "pending_games": sum(not r.get("graded") for r in data),
            "grade_coverage": round(len(graded) / len(data), 4) if data else None,
            "winner_accuracy": round(winner_correct / winner_decisions, 4) if winner_decisions else None,
            "winner_correct": winner_correct,
            "winner_decisions": winner_decisions,
            "avg_margin_error": mean(margin_abs),
            "avg_total_error": mean(total_abs),
            "margin_bias": mean(margin_signed),
            "total_bias": mean(total_signed),
            "away_score_mae": mean(away_score_abs),
            "home_score_mae": mean(home_score_abs),
            "market_totals_over": over_games,
            "market_totals_under": under_games,
        },
        "spread": {**spread, "calibration": spread_cal, "edge_buckets": edge_buckets(data, "spread_edge", spread_pick_outcome)},
        "total": {**total, "calibration": total_cal, "edge_buckets": edge_buckets(data, "total_edge", total_pick_outcome)},
        "recent_games": sorted(enriched, key=lambda r: str(r.get("target_date") or ""), reverse=True)[:100],
        "largest_total_misses": sorted(enriched, key=lambda r: num(r.get("total_error")) or -1, reverse=True)[:20],
        "largest_margin_misses": sorted(enriched, key=lambda r: num(r.get("margin_error")) or -1, reverse=True)[:20],
        "policy": {
            "source": "frozen pregame game prediction ledger",
            "grading": "final score versus frozen score, spread and total forecasts",
            "pass_rows_retained": True,
            "pass_rows_not_counted_as_betting_wins": True,
            "calibration_uses_frozen_pick_probability": True,
            "closing_line_value": "not reported because verified closing lines are not frozen in this ledger",
            "auto_model_changes": False,
        },
    }
    for path in OUTPUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print(json.dumps(report["summary"], indent=2))
    return report


if __name__ == "__main__":
    build()
