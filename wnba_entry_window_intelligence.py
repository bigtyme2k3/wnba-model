"""Sprint 15 Commit 5: historical entry-window and timing recommendations.

This engine learns which stored pregame timing buckets most often beat the closing
market, then scores the latest observation for each market as BET_NOW, WAIT, WATCH,
or PASS. It does not claim a wager was placed and does not guarantee profitability.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

CLV_IN = Path("data/market/clv_results.json")
MOVEMENT_IN = Path("data/market/line_movements.json")
SIGNALS_IN = Path("data/market/movement_classifications.json")
OUT_DIR = Path("data/market")
WINDOWS_OUT = OUT_DIR / "entry_window_history.json"
RECOMMENDATIONS_OUT = OUT_DIR / "entry_window_recommendations.json"
SUMMARY_OUT = Path("data/dashboard/wnba_entry_window_summary.json")

WINDOWS = [
    (1440, 10**9, "24H_PLUS"),
    (720, 1440, "12_TO_24H"),
    (360, 720, "6_TO_12H"),
    (180, 360, "3_TO_6H"),
    (60, 180, "1_TO_3H"),
    (0, 60, "FINAL_HOUR"),
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing input: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get(key, [])
    if not isinstance(rows, list):
        raise RuntimeError(f"Invalid payload in {path}: expected list at {key}")
    return rows


def bucket(minutes: Any) -> str:
    try:
        value = float(minutes)
    except (TypeError, ValueError):
        return "UNKNOWN"
    for low, high, name in WINDOWS:
        if low <= value < high:
            return name
    return "POST_TIP" if value < 0 else "UNKNOWN"


def quality_value(row: dict[str, Any]) -> float:
    point = row.get("point_clv")
    prob = row.get("implied_probability_clv")
    if point is not None:
        return float(point)
    if prob is not None:
        return float(prob) * 10.0
    return 0.0


def build_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("is_closing_observation"):
            continue
        grouped[(str(row.get("bookmaker")), str(row.get("market")), bucket(row.get("minutes_to_tip")))].append(row)
    output = []
    for (book, market, window), group in grouped.items():
        values = [quality_value(x) for x in group]
        positive = sum(1 for x in group if x.get("clv_class") == "POSITIVE")
        negative = sum(1 for x in group if x.get("clv_class") == "NEGATIVE")
        rate = positive / len(group) if group else 0.0
        sample_score = min(30.0, len(group) / 2.0)
        edge_score = max(0.0, min(40.0, (rate - 0.40) * 100.0))
        avg_score = max(0.0, min(30.0, mean(values) * 8.0 + 15.0)) if values else 0.0
        score = round(min(100.0, sample_score + edge_score + avg_score), 2)
        output.append({
            "bookmaker": book,
            "market": market,
            "window": window,
            "observations": len(group),
            "positive_clv": positive,
            "negative_clv": negative,
            "neutral_clv": len(group) - positive - negative,
            "positive_clv_rate": round(rate, 6),
            "average_quality_clv": round(mean(values), 6) if values else 0.0,
            "window_score": score,
            "sample_reliable": len(group) >= 20,
        })
    return sorted(output, key=lambda x: (-x["window_score"], -x["observations"], x["bookmaker"], x["market"], x["window"]))


def recommendation(score: float, signal: str, volatility: float, movement_count: int) -> str:
    strong_signal = signal in {"STEAM", "SHARP", "LATE_MONEY", "POSSIBLE_INJURY"}
    if score >= 72 and signal not in {"POSSIBLE_INJURY"}:
        return "BET_NOW"
    if strong_signal or volatility >= 70:
        return "WATCH"
    if score >= 55 and movement_count > 0:
        return "WAIT"
    return "PASS"


def build_recommendations(
    clv_rows: list[dict[str, Any]], history: list[dict[str, Any]],
    movements: list[dict[str, Any]], signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hist = {(x["bookmaker"], x["market"], x["window"]): x for x in history}
    move_map = {x.get("market_id"): x for x in movements}
    signal_map = {x.get("market_id"): x for x in signals}
    latest: dict[str, dict[str, Any]] = {}
    for row in clv_rows:
        mid = str(row.get("market_id"))
        current = latest.get(mid)
        if current is None or int(row.get("observation_index", 0)) > int(current.get("observation_index", 0)):
            latest[mid] = row
    output = []
    for mid, row in latest.items():
        window = bucket(row.get("minutes_to_tip"))
        historical = hist.get((str(row.get("bookmaker")), str(row.get("market")), window), {})
        movement = move_map.get(mid, {})
        signal = signal_map.get(mid, {})
        window_score = float(historical.get("window_score", 0.0))
        volatility = float(movement.get("volatility_score", 0.0) or 0.0)
        movement_count = int(movement.get("movement_count", 0) or 0)
        classification = str(signal.get("classification") or "NORMAL")
        action = recommendation(window_score, classification, volatility, movement_count)
        confidence = round(min(100.0, window_score * 0.65 + min(25.0, volatility * 0.25) + (10.0 if classification in {"STEAM", "SHARP"} else 0.0)), 2)
        reasons = [f"Historical {window} score {window_score:.1f}"]
        if movement_count:
            reasons.append(f"{movement_count} market movements")
        if classification != "NORMAL":
            reasons.append(f"Signal: {classification}")
        if not historical.get("sample_reliable", False):
            reasons.append("Limited historical sample")
        output.append({
            "market_id": mid,
            "event_id": row.get("event_id"),
            "commence_time_utc": row.get("commence_time_utc"),
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "bookmaker": row.get("bookmaker"),
            "market": row.get("market"),
            "participant": row.get("participant"),
            "selection": row.get("selection"),
            "minutes_to_tip": row.get("minutes_to_tip"),
            "entry_window": window,
            "historical_window_score": window_score,
            "historical_positive_clv_rate": historical.get("positive_clv_rate"),
            "historical_observations": historical.get("observations", 0),
            "volatility_score": volatility,
            "movement_count": movement_count,
            "market_signal": classification,
            "action": action,
            "confidence": confidence,
            "reasons": reasons,
            "methodology_note": "Timing recommendation from historical market CLV and movement behavior; not a guarantee or executed wager.",
        })
    return sorted(output, key=lambda x: (-x["confidence"], x["commence_time_utc"] or "", x["market_id"]))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run() -> dict[str, Any]:
    clv = load(CLV_IN, "records")
    movements = load(MOVEMENT_IN, "movements")
    signals = load(SIGNALS_IN, "classifications")
    history = build_history(clv)
    recommendations = build_recommendations(clv, history, movements, signals)
    generated = now_utc()
    write(WINDOWS_OUT, {"generated_at_utc": generated, "windows": history})
    write(RECOMMENDATIONS_OUT, {"generated_at_utc": generated, "recommendations": recommendations})
    counts = {name: sum(1 for x in recommendations if x["action"] == name) for name in ("BET_NOW", "WAIT", "WATCH", "PASS")}
    summary = {
        "generated_at_utc": generated,
        "status": "READY" if recommendations else "STANDBY",
        "historical_windows": len(history),
        "markets_scored": len(recommendations),
        "actions": counts,
        "reliable_windows": sum(1 for x in history if x["sample_reliable"]),
        "top_windows": history[:25],
        "top_recommendations": recommendations[:50],
        "methodology_note": "Recommendations rank timing quality from stored CLV, movement, volatility and market signals. They are research outputs, not guarantees.",
    }
    write(SUMMARY_OUT, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
