"""Evidence-based calibration for WNBA alternate prop decisions.

This module never changes frozen historical scores. It evaluates verified graded
ALT observations strictly before the target date and determines whether a current
score/price/stat/side segment has demonstrated enough realized profitability to
justify a BUY label.

Calibration evidence is side-isolated. OVER history can never qualify or soften
an UNDER decision, and vice versa.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import wnba_alt_performance_tracker as tracker

ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
REPORTS = [Path("data/warehouse/wnba_alt_calibration.json"), Path("data/dashboard/wnba_alt_calibration.json")]

MIN_SAMPLE = {"specific": 25, "price": 50, "broad": 100}
MIN_SIDE_SAMPLE = 100
MIN_ROI = 0.03
MIN_PROB_EDGE = 0.01


def num(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def implied(odds: Any) -> float | None:
    n = num(odds)
    if n is None or n == 0:
        return None
    return (-n / (-n + 100.0)) if n < 0 else (100.0 / (n + 100.0))


def score_band(score: Any) -> str:
    s = num(score)
    if s is None: return "UNSCORED"
    if s >= 85: return "85+"
    if s >= 80: return "80-84.9"
    if s >= 75: return "75-79.9"
    if s >= 70: return "70-74.9"
    if s >= 60: return "60-69.9"
    return "BELOW_60"


def odds_tier(odds: Any) -> str:
    o = num(odds)
    if o is None: return "UNKNOWN"
    if o >= 100: return "PLUS"
    if o > -150: return "-101_TO_-149"
    if o > -300: return "-150_TO_-299"
    if o > -500: return "-300_TO_-499"
    return "-500_OR_SHORTER"


def wilson_lower(wins: int, n: int, z: float = 1.96) -> float | None:
    if n <= 0: return None
    p = wins / n
    denom = 1 + z*z/n
    center = p + z*z/(2*n)
    spread = z * math.sqrt((p*(1-p) + z*z/(4*n))/n)
    return max(0.0, (center - spread) / denom)


def eligible_history(target: str) -> list[dict[str, Any]]:
    """Calibration sample: one graded observation per candidate_id before target.

    Do not call tracker.canonical_rows() here. That helper intentionally applies
    strict archive-schema-2.0/exact-market chronology gates used by the performance
    tracker. Historical UNDER observations predate those metadata flags, so using
    it for calibration silently removed valid graded UNDER evidence.
    """
    raw = tracker.read_jsonl(ARCHIVE)
    chosen: dict[str, dict[str, Any]] = {}
    for row in raw:
        row_date = str(row.get("date") or row.get("target_date") or "")[:10]
        if not row_date or row_date >= target:
            continue
        if row.get("outcome") not in {"WIN", "LOSS"}:
            continue
        if num(row.get("streak_score")) is None or implied(row.get("best_odds")) is None:
            continue
        side = str(row.get("side") or "").upper()
        if side not in {"OVER", "UNDER"}:
            continue
        key = str(row.get("candidate_id") or row.get("stable_candidate_key") or "").strip()
        if not key:
            key = tracker.stable_candidate_key(row, row_date)
        prior = chosen.get(key)
        if prior is None:
            chosen[key] = row
            continue
        current_time = tracker.parse_time(row.get("snapshot_at_utc"))
        prior_time = tracker.parse_time(prior.get("snapshot_at_utc"))
        if current_time is not None and (prior_time is None or current_time < prior_time):
            chosen[key] = row
    return list(chosen.values())


def segment_keys(row: dict[str, Any]) -> dict[str, str]:
    band = score_band(row.get("streak_score"))
    tier = odds_tier(row.get("best_odds"))
    stat = str(row.get("stat") or "UNKNOWN").upper()
    side = str(row.get("side") or "UNKNOWN").upper()
    return {
        "broad": f"{band}|{side}",
        "price": f"{band}|{side}|{tier}",
        "specific": f"{band}|{stat}|{side}|{tier}",
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(r.get("outcome") == "WIN" for r in rows)
    losses = sum(r.get("outcome") == "LOSS" for r in rows)
    n = wins + losses
    units = 0.0
    implied_values = []
    for r in rows:
        p = tracker.one_unit_profit(str(r.get("outcome")), r.get("best_odds"))
        if p is not None: units += p
        q = implied(r.get("best_odds"))
        if q is not None: implied_values.append(q)
    win_rate = wins / n if n else None
    avg_be = sum(implied_values) / len(implied_values) if implied_values else None
    lower = wilson_lower(wins, n)
    roi = units / n if n else None
    return {
        "n": n, "wins": wins, "losses": losses,
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "wilson_lower_95": round(lower, 4) if lower is not None else None,
        "avg_break_even": round(avg_be, 4) if avg_be is not None else None,
        "probability_margin_lower": round(lower-avg_be, 4) if lower is not None and avg_be is not None else None,
        "profit_loss_units": round(units, 2),
        "roi": round(roi, 4) if roi is not None else None,
    }


def build(target: str) -> dict[str, Any]:
    history = eligible_history(target)
    side_counts = Counter(str(r.get("side") or "UNKNOWN").upper() for r in history)
    buckets: dict[str, dict[str, list[dict[str, Any]]]] = {
        "broad": defaultdict(list), "price": defaultdict(list), "specific": defaultdict(list)
    }
    for row in history:
        for level, key in segment_keys(row).items():
            buckets[level][key].append(row)

    segments: dict[str, dict[str, Any]] = {}
    qualified = []
    for level in ("broad", "price", "specific"):
        segments[level] = {}
        for key, rows in sorted(buckets[level].items()):
            stats = summarize(rows)
            min_n = MIN_SAMPLE[level]
            roi = stats.get("roi")
            margin = stats.get("probability_margin_lower")
            side = str(rows[0].get("side") or "UNKNOWN").upper() if rows else "UNKNOWN"
            side_n = int(side_counts.get(side, 0))
            side_ready = side_n >= MIN_SIDE_SAMPLE
            qualifies = bool(
                side_ready and stats["n"] >= min_n and roi is not None and roi >= MIN_ROI and
                margin is not None and margin >= MIN_PROB_EDGE
            )
            stats.update({
                "level": level, "key": key, "min_sample": min_n,
                "side": side, "side_training_rows": side_n,
                "side_calibration_ready": side_ready,
                "qualifies_buy": qualifies,
            })
            segments[level][key] = stats
            if qualifies:
                qualified.append({"level": level, "key": key, **stats})

    side_coverage = {
        side: {
            "graded_training_rows": int(side_counts.get(side, 0)),
            "calibration_ready": int(side_counts.get(side, 0)) >= MIN_SIDE_SAMPLE,
            "minimum_required": MIN_SIDE_SAMPLE,
        }
        for side in ("OVER", "UNDER")
    }
    ready_segments = [
        row for row in qualified
        if row.get("n", 0) >= int(row.get("min_sample") or 0)
        and row.get("probability_margin_lower") is not None
        and row.get("roi") is not None
    ]
    report = {
        "schema_version": "1.4",
        "target_date": target,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        # Readiness is a property of independently qualified segments, never
        # the league-wide row count.  A large pile of unrelated PASS markets
        # cannot make an uncovered live segment ready.
        "status": "READY" if ready_segments else "COLLECTING",
        "calibration_ready": bool(ready_segments),
        "graded_training_rows": len(history),
        "ready_segment_count": len(ready_segments),
        "side_coverage": side_coverage,
        "historical_side_bias_detected": not all(v["calibration_ready"] for v in side_coverage.values()),
        "policy": {
            "history": "candidate_id-deduplicated graded WIN/LOSS rows strictly before target date",
            "price_aware": True,
            "side_isolated": True,
            "cross_side_fallback_allowed": False,
            "minimum_side_sample": MIN_SIDE_SAMPLE,
            "minimum_samples": MIN_SAMPLE,
            "minimum_realized_roi": MIN_ROI,
            "minimum_wilson_lower_edge_over_break_even": MIN_PROB_EDGE,
            "readiness_rule": "READY requires at least one segment that independently meets its level-specific sample, ROI, Wilson-edge, and same-side coverage gates",
            "selection_rule": "BUY requires a qualifying side-specific price-aware historical segment; the score band is already part of that evidence key and no additional global score floor is applied",
        },
        "qualified_segments": qualified,
        "segments": segments,
    }
    for path in REPORTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def decision(row: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    keys = segment_keys(row)
    side = str(row.get("side") or "UNKNOWN").upper()
    coverage = ((report.get("side_coverage") or {}).get(side) or {})
    if coverage.get("calibration_ready") is not True:
        return {
            "action": "PASS",
            "reason": f"{side} calibration blocked: insufficient verified same-side history",
            "segment": None,
            "keys": keys,
            "evidence_checked": [],
            "side_coverage": coverage,
        }
    evidence = []
    chosen = None
    for level in ("specific", "price", "broad"):
        stats = ((report.get("segments") or {}).get(level) or {}).get(keys[level])
        if not isinstance(stats, dict):
            continue
        evidence.append(stats)
        if stats.get("n", 0) >= MIN_SAMPLE[level]:
            chosen = stats
            break
    score = num(row.get("streak_score")) or 0.0
    # The calibrated segment already includes score band, side and price tier
    # (and stat at the specific level). Requiring score >= 70 here made every
    # qualified 60-69.9 segment impossible to act on, including the recovered
    # UNDER segments. Trust the conservative segment gate directly.
    if chosen and chosen.get("qualifies_buy"):
        action = "BET"
        reason = f"Calibrated BUY: {chosen['level']} segment {chosen['key']}"
    elif score >= 70 and chosen and (chosen.get("roi") or -99) > -0.05:
        action = "WATCH"
        reason = "Score is competitive but same-side historical segment has not cleared the conservative BUY gate"
    else:
        action = "PASS"
        reason = "No same-side price-aware historical segment cleared the conservative BUY gate"
    return {
        "action": action,
        "reason": reason,
        "segment": chosen,
        "keys": keys,
        "evidence_checked": evidence,
        "side_coverage": coverage,
    }


def main(target: str) -> None:
    report = build(target)
    print({
        "status": report["status"], "target": target,
        "training_rows": report["graded_training_rows"],
        "side_coverage": report["side_coverage"],
        "qualified_segments": len(report["qualified_segments"]),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    main(args.date)
