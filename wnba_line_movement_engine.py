"""Sprint 15 Commit 2: derive line-movement intelligence from canonical timelines.

No API calls are made. Inputs are produced by wnba_market_timeline.py.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

TIMELINE_IN = Path("data/market/market_timeline.json")
OUT_DIR = Path("data/market")
MOVEMENTS_OUT = OUT_DIR / "line_movements.json"
BOOKS_OUT = OUT_DIR / "sportsbook_movements.json"
VOLATILITY_OUT = OUT_DIR / "market_volatility.json"
SUMMARY_OUT = Path("data/dashboard/wnba_line_movement_summary.json")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def numeric_delta(a: Any, b: Any) -> float | None:
    if a is None or b is None:
        return None
    try:
        return round(float(b) - float(a), 6)
    except (TypeError, ValueError):
        return None


def direction(delta: float | None) -> str:
    if delta is None or abs(delta) < 1e-9:
        return "NEUTRAL"
    magnitude = abs(delta)
    if delta > 0:
        return "STRONG_UP" if magnitude >= 2 else "UP"
    return "STRONG_DOWN" if magnitude >= 2 else "DOWN"


def volatility_score(observations: list[dict[str, Any]]) -> float:
    if len(observations) <= 1:
        return 0.0
    point_moves, price_moves, gaps = [], [], []
    for prev, curr in zip(observations, observations[1:]):
        pd = numeric_delta(prev.get("point"), curr.get("point"))
        od = numeric_delta(prev.get("american_price"), curr.get("american_price"))
        if pd is not None:
            point_moves.append(abs(pd))
        if od is not None:
            price_moves.append(abs(od) / 25.0)
        gaps.append(max(0.0, (parse_time(curr["snapshot_time_utc"]) - parse_time(prev["snapshot_time_utc"])).total_seconds() / 3600))
    move_component = sum(point_moves) * 12 + sum(price_moves) * 5
    count_component = min(25, (len(observations) - 1) * 4)
    dispersion = (pstdev(point_moves) * 8 if len(point_moves) > 1 else 0) + (pstdev(price_moves) * 3 if len(price_moves) > 1 else 0)
    speed = 0 if not gaps else max(0, 20 - min(20, mean(gaps) * 2))
    return round(min(100.0, move_component + count_component + dispersion + speed), 2)


def market_metrics(timeline: dict[str, Any]) -> dict[str, Any]:
    obs = timeline.get("observations") or []
    first, last = obs[0], obs[-1]
    point_changes, price_changes = [], []
    change_times = []
    for prev, curr in zip(obs, obs[1:]):
        pd = numeric_delta(prev.get("point"), curr.get("point"))
        od = numeric_delta(prev.get("american_price"), curr.get("american_price"))
        if pd is not None and abs(pd) > 1e-9:
            point_changes.append(pd)
        if od is not None and abs(od) > 1e-9:
            price_changes.append(od)
        if (pd is not None and abs(pd) > 1e-9) or (od is not None and abs(od) > 1e-9):
            change_times.append(curr["snapshot_time_utc"])
    point_delta = numeric_delta(first.get("point"), last.get("point"))
    price_delta = numeric_delta(first.get("american_price"), last.get("american_price"))
    elapsed_hours = round(max(0.0, (parse_time(last["snapshot_time_utc"]) - parse_time(first["snapshot_time_utc"])).total_seconds() / 3600), 3)
    result = {
        "market_id": timeline["market_id"], "event_id": timeline["event_id"],
        "commence_time_utc": timeline["commence_time_utc"], "home_team": timeline["home_team"],
        "away_team": timeline["away_team"], "bookmaker": timeline["bookmaker"],
        "market": timeline["market"], "participant": timeline["participant"],
        "selection": timeline["selection"], "outcome_key": timeline["outcome_key"],
        "opening_point": first.get("point"), "current_point": last.get("point"),
        "opening_price": first.get("american_price"), "current_price": last.get("american_price"),
        "point_movement": point_delta, "price_movement": price_delta,
        "direction": direction(point_delta if point_delta is not None else price_delta),
        "observation_count": len(obs), "movement_count": len(change_times),
        "point_change_count": len(point_changes), "price_change_count": len(price_changes),
        "largest_point_move": round(max((abs(x) for x in point_changes), default=0.0), 6),
        "largest_price_move": round(max((abs(x) for x in price_changes), default=0.0), 6),
        "average_point_move": round(mean(abs(x) for x in point_changes), 6) if point_changes else 0.0,
        "average_price_move": round(mean(abs(x) for x in price_changes), 6) if price_changes else 0.0,
        "first_movement_time_utc": change_times[0] if change_times else None,
        "last_movement_time_utc": change_times[-1] if change_times else None,
        "tracking_hours": elapsed_hours,
        "volatility_score": volatility_score(obs),
    }
    return result


def comparison_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row["event_id"], row["market"], row["outcome_key"]


def build_book_comparisons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[comparison_key(row)].append(row)
    output = []
    for key, group in grouped.items():
        books = {r["bookmaker"]: r for r in group}
        if not {"draftkings", "fanduel"}.issubset(books):
            continue
        dk, fd = books["draftkings"], books["fanduel"]
        first_candidates = [(r.get("first_movement_time_utc"), r["bookmaker"]) for r in (dk, fd) if r.get("first_movement_time_utc")]
        leader = min(first_candidates)[1] if first_candidates else None
        lag_minutes = None
        if len(first_candidates) == 2:
            lag_minutes = round(abs((parse_time(first_candidates[0][0]) - parse_time(first_candidates[1][0])).total_seconds()) / 60, 2)
        point_gap = numeric_delta(dk.get("current_point"), fd.get("current_point"))
        price_gap = numeric_delta(dk.get("current_price"), fd.get("current_price"))
        output.append({
            "event_id": key[0], "market": key[1], "outcome_key": key[2],
            "home_team": dk["home_team"], "away_team": dk["away_team"],
            "participant": dk["participant"], "selection": dk["selection"],
            "first_book_to_move": leader, "movement_lag_minutes": lag_minutes,
            "draftkings": {"current_point": dk["current_point"], "current_price": dk["current_price"], "volatility_score": dk["volatility_score"]},
            "fanduel": {"current_point": fd["current_point"], "current_price": fd["current_price"], "volatility_score": fd["volatility_score"]},
            "current_point_disagreement": point_gap,
            "current_price_disagreement": price_gap,
            "books_agree_on_point": point_gap is not None and abs(point_gap) < 1e-9,
        })
    return sorted(output, key=lambda x: (x["event_id"], x["market"], x["outcome_key"]))


def load_timelines() -> list[dict[str, Any]]:
    if not TIMELINE_IN.exists():
        raise FileNotFoundError(f"Timeline input missing: {TIMELINE_IN}")
    payload = json.loads(TIMELINE_IN.read_text(encoding="utf-8"))
    rows = payload.get("markets", [])
    if not isinstance(rows, list):
        raise RuntimeError("market_timeline.json has invalid markets payload")
    return rows


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run() -> dict[str, Any]:
    timelines = load_timelines()
    movements = [market_metrics(t) for t in timelines if t.get("observations")]
    movements.sort(key=lambda x: (x["commence_time_utc"], x["market_id"]))
    comparisons = build_book_comparisons(movements)
    volatility = sorted(movements, key=lambda x: (-x["volatility_score"], x["market_id"]))
    generated = now_utc()
    write(MOVEMENTS_OUT, {"generated_at_utc": generated, "movements": movements})
    write(BOOKS_OUT, {"generated_at_utc": generated, "comparisons": comparisons})
    write(VOLATILITY_OUT, {"generated_at_utc": generated, "markets": volatility})
    summary = {
        "generated_at_utc": generated,
        "status": "READY" if movements else "STANDBY",
        "markets_analyzed": len(movements),
        "markets_with_movement": sum(1 for x in movements if x["movement_count"] > 0),
        "sportsbook_comparisons": len(comparisons),
        "average_volatility": round(mean(x["volatility_score"] for x in movements), 2) if movements else 0.0,
        "high_volatility_markets": sum(1 for x in movements if x["volatility_score"] >= 70),
        "biggest_movers": sorted(movements, key=lambda x: (-(abs(x["point_movement"]) if x["point_movement"] is not None else 0), -abs(x["price_movement"] or 0)))[:25],
        "most_volatile": volatility[:25],
        "largest_book_disagreements": sorted(comparisons, key=lambda x: (-(abs(x["current_point_disagreement"]) if x["current_point_disagreement"] is not None else 0), -abs(x["current_price_disagreement"] or 0)))[:25],
    }
    write(SUMMARY_OUT, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
