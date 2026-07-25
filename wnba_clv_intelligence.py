"""Sprint 15 Commit 4: closing-line-value intelligence.

This engine measures each stored pregame observation against the final pregame
observation for the same sportsbook market. It does not claim a wager was made.
The output is market-timing CLV intelligence that can later be joined to frozen
recommendations or actual wagers.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable

TIMELINE_IN = Path("data/market/market_timeline.json")
OUT_DIR = Path("data/market")
RESULTS_OUT = OUT_DIR / "clv_results.json"
BOOK_OUT = OUT_DIR / "sportsbook_clv.json"
PLAYER_OUT = OUT_DIR / "player_clv.json"
TEAM_OUT = OUT_DIR / "team_clv.json"
MARKET_OUT = OUT_DIR / "market_clv.json"
LEADERBOARD_OUT = OUT_DIR / "clv_leaderboard.json"
SUMMARY_OUT = Path("data/dashboard/wnba_clv_summary.json")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def implied_probability(price: Any) -> float | None:
    try:
        p = int(price)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    value = (-p) / ((-p) + 100) if p < 0 else 100 / (p + 100)
    return round(value, 8)


def decimal_price(price: Any) -> float | None:
    try:
        p = int(price)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    return round(1 + (100 / abs(p) if p < 0 else p / 100), 8)


def safe_delta(a: Any, b: Any) -> float | None:
    if a is None or b is None:
        return None
    try:
        return round(float(a) - float(b), 8)
    except (TypeError, ValueError):
        return None


def orientation(selection: str) -> int:
    """Return sign that makes favorable point movement positive.

    Over and favorite-side observations benefit from lower points; under and
    underdog/opposing-side observations benefit from higher points. For market
    types where direction is ambiguous, raw point movement is retained.
    """
    value = (selection or "").strip().lower()
    if value == "over":
        return -1
    if value == "under":
        return 1
    return 1


def classify(point_clv: float | None, probability_clv: float | None) -> str:
    signal = point_clv if point_clv is not None and abs(point_clv) > 1e-9 else probability_clv
    if signal is None or abs(signal) < 1e-9:
        return "NEUTRAL"
    return "POSITIVE" if signal > 0 else "NEGATIVE"


def load_timelines() -> list[dict[str, Any]]:
    if not TIMELINE_IN.exists():
        raise FileNotFoundError(f"Missing timeline input: {TIMELINE_IN}")
    payload = json.loads(TIMELINE_IN.read_text(encoding="utf-8"))
    rows = payload.get("markets", [])
    if not isinstance(rows, list):
        raise RuntimeError("market_timeline.json has invalid markets payload")
    return rows


def build_results(timelines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for timeline in timelines:
        obs = timeline.get("observations") or []
        if not obs:
            continue
        closing = obs[-1]
        close_point = closing.get("point")
        close_price = closing.get("american_price")
        close_prob = implied_probability(close_price)
        close_decimal = decimal_price(close_price)
        for index, row in enumerate(obs):
            captured_point = row.get("point")
            captured_price = row.get("american_price")
            captured_prob = implied_probability(captured_price)
            captured_decimal = decimal_price(captured_price)
            raw_point = safe_delta(close_point, captured_point)
            point_clv = round(raw_point * orientation(str(timeline.get("selection") or "")), 8) if raw_point is not None else None
            probability_clv = safe_delta(close_prob, captured_prob)
            decimal_clv = safe_delta(captured_decimal, close_decimal)
            minutes_to_tip = round((parse_time(timeline["commence_time_utc"]) - parse_time(row["snapshot_time_utc"])).total_seconds() / 60, 2)
            output.append({
                "market_id": timeline["market_id"],
                "event_id": timeline["event_id"],
                "commence_time_utc": timeline["commence_time_utc"],
                "home_team": timeline["home_team"],
                "away_team": timeline["away_team"],
                "bookmaker": timeline["bookmaker"],
                "market": timeline["market"],
                "participant": timeline.get("participant"),
                "selection": timeline.get("selection"),
                "observation_index": index,
                "captured_at_utc": row["snapshot_time_utc"],
                "minutes_to_tip": minutes_to_tip,
                "captured_point": captured_point,
                "closing_point": close_point,
                "captured_price": captured_price,
                "closing_price": close_price,
                "point_clv": point_clv,
                "implied_probability_clv": probability_clv,
                "decimal_odds_clv": decimal_clv,
                "clv_class": classify(point_clv, probability_clv),
                "is_closing_observation": index == len(obs) - 1,
            })
    return sorted(output, key=lambda x: (x["commence_time_utc"], x["market_id"], x["observation_index"]))


def aggregate(rows: list[dict[str, Any]], key_fn: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["is_closing_observation"]:
            continue
        grouped[key_fn(row)].append(row)
    output = []
    for key, group in grouped.items():
        point_values = [float(x["point_clv"]) for x in group if x.get("point_clv") is not None]
        prob_values = [float(x["implied_probability_clv"]) for x in group if x.get("implied_probability_clv") is not None]
        positive = sum(1 for x in group if x["clv_class"] == "POSITIVE")
        negative = sum(1 for x in group if x["clv_class"] == "NEGATIVE")
        neutral = len(group) - positive - negative
        output.append({
            "key": key,
            "observations": len(group),
            "markets": len({x["market_id"] for x in group}),
            "average_point_clv": round(mean(point_values), 6) if point_values else None,
            "median_point_clv": round(median(point_values), 6) if point_values else None,
            "average_implied_probability_clv": round(mean(prob_values), 6) if prob_values else None,
            "positive_clv": positive,
            "negative_clv": negative,
            "neutral_clv": neutral,
            "positive_clv_rate": round(positive / len(group), 6) if group else 0.0,
        })
    return sorted(output, key=lambda x: (-x["positive_clv_rate"], -(x["observations"]), x["key"]))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run() -> dict[str, Any]:
    timelines = load_timelines()
    results = build_results(timelines)
    non_close = [x for x in results if not x["is_closing_observation"]]
    by_book = aggregate(results, lambda x: str(x["bookmaker"]))
    by_player = aggregate(results, lambda x: str(x.get("participant") or "UNKNOWN"))
    by_team = aggregate(results, lambda x: f"{x['away_team']} @ {x['home_team']}")
    by_market = aggregate(results, lambda x: str(x["market"]))
    leaderboard = sorted(
        non_close,
        key=lambda x: (
            -(x["point_clv"] if x["point_clv"] is not None else -999),
            -(x["implied_probability_clv"] if x["implied_probability_clv"] is not None else -999),
        ),
    )
    generated = now_utc()
    write(RESULTS_OUT, {"generated_at_utc": generated, "definition": "stored observation versus final pregame observation; not an executed wager", "records": results})
    write(BOOK_OUT, {"generated_at_utc": generated, "sportsbooks": by_book})
    write(PLAYER_OUT, {"generated_at_utc": generated, "players": by_player})
    write(TEAM_OUT, {"generated_at_utc": generated, "matchups": by_team})
    write(MARKET_OUT, {"generated_at_utc": generated, "markets": by_market})
    write(LEADERBOARD_OUT, {"generated_at_utc": generated, "best": leaderboard[:100], "worst": list(reversed(leaderboard[-100:]))})
    summary = {
        "generated_at_utc": generated,
        "status": "READY" if results else "STANDBY",
        "markets_analyzed": len({x["market_id"] for x in results}),
        "observations_analyzed": len(results),
        "non_closing_observations": len(non_close),
        "positive_clv_observations": sum(1 for x in non_close if x["clv_class"] == "POSITIVE"),
        "negative_clv_observations": sum(1 for x in non_close if x["clv_class"] == "NEGATIVE"),
        "neutral_clv_observations": sum(1 for x in non_close if x["clv_class"] == "NEUTRAL"),
        "sportsbooks": len(by_book),
        "market_types": len(by_market),
        "top_positive": leaderboard[:25],
        "top_negative": list(reversed(leaderboard[-25:])),
        "methodology_note": "CLV is measured for stored observations against the final pregame observation. It is a timing-quality metric, not proof that a wager was placed.",
    }
    write(SUMMARY_OUT, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
