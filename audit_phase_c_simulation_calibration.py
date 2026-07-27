"""Sprint 20.5 Phase C: audit simulation probability calibration and overconfidence."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODEL_HISTORY = Path("data/history/wnba_model_history.jsonl")
REPORT_OUT = Path("data/audit/phase_c_calibration_report.json")
CURVE_OUT = Path("data/audit/probability_calibration_curve.json")
DISTRIBUTION_OUT = Path("data/audit/simulation_distribution.json")

BANDS: Sequence[Tuple[float, float]] = (
    (0.00, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.65),
    (0.65, 0.70), (0.70, 0.75), (0.75, 0.80), (0.80, 0.85),
    (0.85, 0.90), (0.90, 0.95), (0.95, 0.99), (0.99, 1.000001),
)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return rows


def finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def probability(value: Any) -> Optional[float]:
    number = finite(value)
    if number is None:
        return None
    if number > 1:
        number /= 100.0
    if number < 0 or number > 1:
        return None
    return number


def clamp(value: float, low: float = 1e-6, high: float = 1 - 1e-6) -> float:
    return max(low, min(high, value))


def outcome(row: Dict[str, Any]) -> Optional[int]:
    result = str(row.get("outcome") or row.get("result") or "").upper()
    if result == "WIN":
        return 1
    if result == "LOSS":
        return 0
    return None


def brier(pairs: Iterable[Tuple[float, int]]) -> Optional[float]:
    values = list(pairs)
    return sum((p - y) ** 2 for p, y in values) / len(values) if values else None


def log_loss(pairs: Iterable[Tuple[float, int]]) -> Optional[float]:
    values = list(pairs)
    if not values:
        return None
    return -sum(y * math.log(clamp(p)) + (1 - y) * math.log(clamp(1 - p)) for p, y in values) / len(values)


def calibration_bands(pairs: Sequence[Tuple[float, int]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for low, high in BANDS:
        members = [(p, y) for p, y in pairs if low <= p < high]
        if not members:
            continue
        avg_p = sum(p for p, _ in members) / len(members)
        hit_rate = sum(y for _, y in members) / len(members)
        rows.append({
            "low": round(low, 4), "high": round(min(high, 1.0), 4),
            "count": len(members), "average_probability": round(avg_p, 6),
            "actual_win_rate": round(hit_rate, 6),
            "calibration_gap": round(hit_rate - avg_p, 6),
            "absolute_gap": round(abs(hit_rate - avg_p), 6),
        })
    return rows


def calibration_metrics(pairs: Sequence[Tuple[float, int]]) -> Dict[str, Any]:
    bands = calibration_bands(pairs)
    total = len(pairs)
    ece = sum(row["absolute_gap"] * row["count"] for row in bands) / total if total else None
    mce = max((row["absolute_gap"] for row in bands), default=None)
    average_p = sum(p for p, _ in pairs) / total if total else None
    hit_rate = sum(y for _, y in pairs) / total if total else None
    return {
        "samples": total,
        "average_probability": None if average_p is None else round(average_p, 6),
        "actual_win_rate": None if hit_rate is None else round(hit_rate, 6),
        "global_calibration_gap": None if average_p is None else round(hit_rate - average_p, 6),
        "brier_score": None if not pairs else round(brier(pairs) or 0.0, 6),
        "log_loss": None if not pairs else round(log_loss(pairs) or 0.0, 6),
        "ece": None if ece is None else round(ece, 6),
        "mce": None if mce is None else round(mce, 6),
        "bands": bands,
    }


def temperature_probability(p: float, temperature: float) -> float:
    p = clamp(p)
    logit = math.log(p / (1 - p))
    return 1 / (1 + math.exp(-(logit / temperature)))


def shrink_probability(p: float, strength: float) -> float:
    return 0.5 + strength * (p - 0.5)


def candidate_calibrations(pairs: Sequence[Tuple[float, int]]) -> Dict[str, Any]:
    if len(pairs) < 50:
        return {"status": "INSUFFICIENT_SAMPLE", "minimum_samples": 50, "samples": len(pairs), "candidates": []}
    candidates: List[Dict[str, Any]] = []
    base_brier = brier(pairs) or 0.0
    base_log_loss = log_loss(pairs) or 0.0
    candidates.append({"method": "identity", "parameter": 1.0, "brier_score": round(base_brier, 6), "log_loss": round(base_log_loss, 6)})
    for temperature in [1.1, 1.2, 1.35, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]:
        transformed = [(temperature_probability(p, temperature), y) for p, y in pairs]
        candidates.append({"method": "temperature", "parameter": temperature, "brier_score": round(brier(transformed) or 0.0, 6), "log_loss": round(log_loss(transformed) or 0.0, 6)})
    for strength in [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.60, 0.50]:
        transformed = [(shrink_probability(p, strength), y) for p, y in pairs]
        candidates.append({"method": "linear_shrinkage", "parameter": strength, "brier_score": round(brier(transformed) or 0.0, 6), "log_loss": round(log_loss(transformed) or 0.0, 6)})
    best = min(candidates, key=lambda row: (row["log_loss"], row["brier_score"]))
    return {
        "status": "EVALUATED",
        "minimum_samples": 50,
        "samples": len(pairs),
        "best_candidate": best,
        "brier_improvement": round(base_brier - best["brier_score"], 6),
        "log_loss_improvement": round(base_log_loss - best["log_loss"], 6),
        "candidates": candidates,
        "note": "Diagnostic in-sample comparison only; production calibration requires time-split validation.",
    }


def market_key(row: Dict[str, Any]) -> str:
    return str(row.get("stat") or row.get("market") or "UNKNOWN").upper()


def build(target: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    rows = read_jsonl(MODEL_HISTORY)
    target_rows = [row for row in rows if str(row.get("date")) == target]

    current: List[Dict[str, Any]] = []
    for row in target_rows:
        p = probability(row.get("simulation_probability"))
        if p is None:
            continue
        current.append({
            "history_key": row.get("history_key"), "date": row.get("date"),
            "player": row.get("player"), "game": row.get("game"),
            "market": market_key(row), "selection": row.get("signal") or row.get("selection"),
            "simulation_probability": round(p, 6),
            "confidence": probability(row.get("confidence")),
            "final_score": finite(row.get("final_score")),
            "consensus_score": finite(row.get("consensus_score")),
            "extreme_probability": p >= 0.95 or p <= 0.05,
        })

    settled: List[Tuple[Dict[str, Any], float, int]] = []
    for row in rows:
        p = probability(row.get("simulation_probability"))
        y = outcome(row)
        if p is not None and y is not None:
            settled.append((row, p, y))
    pairs = [(p, y) for _, p, y in settled]

    distribution = []
    for low, high in BANDS:
        members = [item for item in current if low <= item["simulation_probability"] < high]
        distribution.append({"low": low, "high": min(high, 1.0), "count": len(members), "share": round(len(members) / len(current), 6) if current else 0.0})

    by_market_pairs: Dict[str, List[Tuple[float, int]]] = defaultdict(list)
    for row, p, y in settled:
        by_market_pairs[market_key(row)].append((p, y))
    by_market = {}
    for market, market_pairs in sorted(by_market_pairs.items()):
        metrics = calibration_metrics(market_pairs)
        metrics.pop("bands", None)
        metrics["extreme_predictions"] = sum(p >= 0.95 or p <= 0.05 for p, _ in market_pairs)
        metrics["overconfidence_flag"] = bool(metrics.get("global_calibration_gap") is not None and metrics["global_calibration_gap"] < -0.10 and len(market_pairs) >= 25)
        by_market[market] = metrics

    overall = calibration_metrics(pairs)
    current_probabilities = [item["simulation_probability"] for item in current]
    extreme_current = [item for item in current if item["extreme_probability"]]
    extreme_settled_pairs = [(p, y) for _, p, y in settled if p >= 0.95 or p <= 0.05]
    extreme_metrics = calibration_metrics(extreme_settled_pairs)
    calibration = candidate_calibrations(pairs)

    findings: List[str] = []
    if overall["samples"] < 50:
        findings.append("insufficient_settled_sample")
    if overall.get("global_calibration_gap") is not None and overall["global_calibration_gap"] < -0.05:
        findings.append("global_overconfidence")
    if overall.get("ece") is not None and overall["ece"] > 0.08:
        findings.append("high_expected_calibration_error")
    if extreme_metrics["samples"] >= 10 and extreme_metrics.get("global_calibration_gap") is not None and extreme_metrics["global_calibration_gap"] < -0.10:
        findings.append("extreme_probability_overconfidence")
    if calibration.get("best_candidate", {}).get("method") not in {None, "identity"}:
        findings.append("recalibration_candidate_improves_diagnostics")

    status = "PASS" if not findings else "WARN"
    report = {
        "generated_at_utc": now,
        "target_date": target,
        "source": str(MODEL_HISTORY),
        "summary": {
            "history_records": len(rows), "target_records": len(target_rows),
            "target_probability_records": len(current), "settled_probability_records": len(settled),
            "target_extreme_probability_records": len(extreme_current),
            "settled_extreme_probability_records": len(extreme_settled_pairs),
            "target_average_probability": round(sum(current_probabilities) / len(current_probabilities), 6) if current_probabilities else None,
            "target_median_probability": round(median(current_probabilities), 6) if current_probabilities else None,
            "brier_score": overall.get("brier_score"), "log_loss": overall.get("log_loss"),
            "ece": overall.get("ece"), "global_calibration_gap": overall.get("global_calibration_gap"),
            "status": status,
        },
        "findings": findings,
        "overall_calibration": overall,
        "extreme_probability_calibration": extreme_metrics,
        "market_calibration": by_market,
        "calibration_method_diagnostics": calibration,
        "recommendation": {
            "action": "TIME_SPLIT_CALIBRATION_VALIDATION" if "recalibration_candidate_improves_diagnostics" in findings else "CONTINUE_MONITORING",
            "do_not": "Do not hard-cap probabilities until out-of-sample calibration validation is complete.",
            "next_test": "Fit the selected calibration method on earlier dates and evaluate Brier score, log loss, ECE, ranking retention, and EV realism on later dates.",
        },
    }
    curve = {"generated_at_utc": now, "target_date": target, "samples": len(pairs), "bands": overall["bands"]}
    distribution_report = {
        "generated_at_utc": now, "target_date": target, "records": len(current),
        "bands": distribution, "extreme_records": sorted(extreme_current, key=lambda item: item["simulation_probability"], reverse=True),
        "market_counts": dict(Counter(item["market"] for item in current)),
    }

    for path, payload in ((REPORT_OUT, report), (CURVE_OUT, curve), (DISTRIBUTION_OUT, distribution_report)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    print("Phase C audit:", build(args.date)["summary"])


if __name__ == "__main__":
    main()
