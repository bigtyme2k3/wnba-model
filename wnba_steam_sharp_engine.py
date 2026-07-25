"""Sprint 15 Commit 3: classify WNBA line movement into actionable market signals.

Inputs are produced by Sprint 15 Commit 2. No API calls are made.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

MOVEMENTS_IN = Path("data/market/line_movements.json")
BOOKS_IN = Path("data/market/sportsbook_movements.json")
OUT_DIR = Path("data/market")
CLASSIFICATIONS_OUT = OUT_DIR / "movement_classifications.json"
STEAM_OUT = OUT_DIR / "steam_alerts.json"
SHARP_OUT = OUT_DIR / "sharp_movements.json"
CONSENSUS_OUT = OUT_DIR / "consensus_movements.json"
SIGNALS_OUT = OUT_DIR / "market_signals.json"
SUMMARY_OUT = Path("data/dashboard/wnba_steam_sharp_summary.json")
VALID_CLASSES = {"NORMAL", "SHARP", "STEAM", "BOOK_LEADER", "MARKET_CORRECTION", "LATE_MONEY", "POSSIBLE_INJURY"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def absnum(value: Any) -> float:
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 0.0


def load_list(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Required input missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get(key, [])
    if not isinstance(rows, list):
        raise RuntimeError(f"Invalid {key} payload in {path}")
    return rows


def minutes_before_tip(row: dict[str, Any]) -> float | None:
    move = parse_time(row.get("last_movement_time_utc"))
    tip = parse_time(row.get("commence_time_utc"))
    if move is None or tip is None:
        return None
    return round((tip - move).total_seconds() / 60, 2)


def base_score(row: dict[str, Any]) -> float:
    point = min(30.0, absnum(row.get("point_movement")) * 15.0)
    price = min(20.0, absnum(row.get("price_movement")) / 5.0)
    volatility = min(30.0, float(row.get("volatility_score") or 0) * 0.30)
    count = min(20.0, float(row.get("movement_count") or 0) * 4.0)
    return min(100.0, point + price + volatility + count)


def classify(row: dict[str, Any], comparison: dict[str, Any] | None) -> dict[str, Any]:
    score = base_score(row)
    mbt = minutes_before_tip(row)
    movement_count = int(row.get("movement_count") or 0)
    vol = float(row.get("volatility_score") or 0)
    point_mag = absnum(row.get("point_movement"))
    price_mag = absnum(row.get("price_movement"))
    leader = comparison.get("first_book_to_move") if comparison else None
    lag = comparison.get("movement_lag_minutes") if comparison else None
    agree = bool(comparison and comparison.get("books_agree_on_point"))
    consensus = bool(comparison and leader and lag is not None and lag <= 60 and (agree or absnum(comparison.get("current_point_disagreement")) <= 0.5))

    label = "NORMAL"
    reasons: list[str] = []
    if movement_count == 0:
        reasons.append("no meaningful line or price change")
    if consensus and score >= 55:
        label = "STEAM"
        score += 15
        reasons.append("both books converged within 60 minutes")
    elif score >= 65 or vol >= 75 or point_mag >= 1.5 or price_mag >= 35:
        label = "SHARP"
        reasons.append("large or high-velocity movement")
    elif leader and movement_count > 0:
        label = "BOOK_LEADER"
        score += 5
        reasons.append(f"{leader} moved first")

    if mbt is not None and 0 <= mbt <= 60 and movement_count > 0:
        if label not in {"STEAM", "SHARP"}:
            label = "LATE_MONEY"
        score += 10
        reasons.append(f"last move occurred {mbt:.1f} minutes before tip")

    possible_injury = bool(
        mbt is not None and 0 <= mbt <= 180 and consensus and
        (point_mag >= 1.5 or price_mag >= 40 or vol >= 85)
    )
    if possible_injury:
        label = "POSSIBLE_INJURY"
        score += 10
        reasons.append("large, late, multi-book move; injury/news review required")

    correction = bool(
        movement_count >= 2 and point_mag <= 0.5 and price_mag <= 10 and vol >= 35
    )
    if correction and label == "NORMAL":
        label = "MARKET_CORRECTION"
        reasons.append("market moved but returned near its opening level")

    confidence = round(max(0.0, min(100.0, score)), 2)
    return {
        **row,
        "classification": label,
        "confidence": confidence,
        "minutes_before_tip": mbt,
        "consensus_move": consensus,
        "first_book_to_move": leader,
        "movement_lag_minutes": lag,
        "possible_injury": possible_injury,
        "reasons": reasons or ["movement below alert thresholds"],
    }


def comparison_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {(r["event_id"], r["market"], r["outcome_key"]): r for r in rows}


def build_signals(classifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in classifications:
        if row["classification"] != "NORMAL":
            by_event[row["event_id"]].append(row)
    signals = []
    for event_id, rows in by_event.items():
        rows.sort(key=lambda x: (-x["confidence"], x["market_id"]))
        top = rows[0]
        signals.append({
            "event_id": event_id,
            "commence_time_utc": top["commence_time_utc"],
            "home_team": top["home_team"],
            "away_team": top["away_team"],
            "signal_count": len(rows),
            "max_confidence": top["confidence"],
            "dominant_classification": top["classification"],
            "steam_count": sum(1 for x in rows if x["classification"] == "STEAM"),
            "sharp_count": sum(1 for x in rows if x["classification"] == "SHARP"),
            "late_money_count": sum(1 for x in rows if x["classification"] == "LATE_MONEY"),
            "possible_injury_count": sum(1 for x in rows if x["possible_injury"]),
            "top_markets": rows[:10],
        })
    return sorted(signals, key=lambda x: (-x["max_confidence"], x["commence_time_utc"], x["event_id"]))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run() -> dict[str, Any]:
    movements = load_list(MOVEMENTS_IN, "movements")
    comparisons = load_list(BOOKS_IN, "comparisons")
    comp = comparison_index(comparisons)
    classifications = []
    for row in movements:
        key = (row["event_id"], row["market"], row["outcome_key"])
        classifications.append(classify(row, comp.get(key)))
    classifications.sort(key=lambda x: (x["commence_time_utc"], -x["confidence"], x["market_id"]))
    steam = [x for x in classifications if x["classification"] == "STEAM"]
    sharp = [x for x in classifications if x["classification"] in {"SHARP", "POSSIBLE_INJURY"}]
    consensus = [x for x in classifications if x["consensus_move"]]
    signals = build_signals(classifications)
    generated = now_utc()
    write(CLASSIFICATIONS_OUT, {"generated_at_utc": generated, "classifications": classifications})
    write(STEAM_OUT, {"generated_at_utc": generated, "alerts": sorted(steam, key=lambda x: -x["confidence"])})
    write(SHARP_OUT, {"generated_at_utc": generated, "movements": sorted(sharp, key=lambda x: -x["confidence"])})
    write(CONSENSUS_OUT, {"generated_at_utc": generated, "movements": sorted(consensus, key=lambda x: -x["confidence"])})
    write(SIGNALS_OUT, {"generated_at_utc": generated, "signals": signals})
    counts = {name: sum(1 for x in classifications if x["classification"] == name) for name in sorted(VALID_CLASSES)}
    summary = {
        "generated_at_utc": generated,
        "status": "READY" if classifications else "STANDBY",
        "markets_analyzed": len(classifications),
        "markets_with_signals": sum(1 for x in classifications if x["classification"] != "NORMAL"),
        "classifications": counts,
        "steam_alerts": len(steam),
        "sharp_movements": len(sharp),
        "consensus_movements": len(consensus),
        "possible_injury_flags": sum(1 for x in classifications if x["possible_injury"]),
        "events_with_signals": len(signals),
        "average_signal_confidence": round(mean(x["confidence"] for x in classifications if x["classification"] != "NORMAL"), 2) if any(x["classification"] != "NORMAL" for x in classifications) else 0.0,
        "top_alerts": sorted((x for x in classifications if x["classification"] != "NORMAL"), key=lambda x: -x["confidence"])[:25],
    }
    write(SUMMARY_OUT, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
