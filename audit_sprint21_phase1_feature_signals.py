"""Sprint 21 Phase 1: feature importance, stability, redundancy, and signal audit."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HISTORY = Path("data/history/wnba_model_history.jsonl")
OUT_IMPORTANCE = Path("data/audit/feature_importance.json")
OUT_RANKINGS = Path("data/audit/feature_rankings.json")
OUT_CORRELATIONS = Path("data/audit/feature_correlations.json")
OUT_RECOMMENDED = Path("data/audit/recommended_feature_set.json")

EXCLUDED = {
    "outcome", "result", "status", "date", "generated_at", "generated_at_utc",
    "history_key", "player", "team", "opponent", "game", "market", "stat",
    "selection", "signal", "sportsbook", "book", "final_action", "reason",
    "notes", "id", "event_id", "commence_time", "target_date",
}
MIN_FEATURE_SAMPLES = 100
MIN_STABILITY_SAMPLES = 40


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return rows


def number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return float(value)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def target(row: Dict[str, Any]) -> Optional[int]:
    result = str(row.get("outcome") or row.get("result") or "").upper()
    return 1 if result == "WIN" else 0 if result == "LOSS" else None


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    if dx <= 0 or dy <= 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(dx * dy)


def auc(pairs: Sequence[Tuple[float, int]]) -> Optional[float]:
    positives = [x for x, y in pairs if y == 1]
    negatives = [x for x, y in pairs if y == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for n in negatives:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(positives) * len(negatives))


def quantile_separation(pairs: Sequence[Tuple[float, int]], fraction: float = 0.2) -> Optional[float]:
    if len(pairs) < 20:
        return None
    ordered = sorted(pairs, key=lambda item: item[0])
    size = max(1, int(len(ordered) * fraction))
    bottom, top = ordered[:size], ordered[-size:]
    return sum(y for _, y in top) / len(top) - sum(y for _, y in bottom) / len(bottom)


def mutual_information(pairs: Sequence[Tuple[float, int]], bins: int = 8) -> float:
    if len(pairs) < 20:
        return 0.0
    ordered = sorted(pairs, key=lambda item: item[0])
    assignments: List[Tuple[int, int]] = []
    for index, (_, y) in enumerate(ordered):
        bucket = min(bins - 1, int(index * bins / len(ordered)))
        assignments.append((bucket, y))
    total = len(assignments)
    bx, by, joint = defaultdict(int), defaultdict(int), defaultdict(int)
    for bucket, y in assignments:
        bx[bucket] += 1
        by[y] += 1
        joint[(bucket, y)] += 1
    mi = 0.0
    for (bucket, y), count in joint.items():
        pxy = count / total
        px, py = bx[bucket] / total, by[y] / total
        mi += pxy * math.log(max(pxy / (px * py), 1e-12))
    return mi


def numeric_features(rows: Sequence[Dict[str, Any]]) -> List[str]:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        for key, value in row.items():
            if key in EXCLUDED or key.startswith("_"):
                continue
            if number(value) is not None:
                counts[key] += 1
    return sorted(key for key, count in counts.items() if count >= MIN_FEATURE_SAMPLES)


def period_stability(rows: Sequence[Dict[str, Any]], feature: str) -> Dict[str, Any]:
    dated = sorted(rows, key=lambda row: str(row.get("date") or ""))
    if len(dated) < MIN_STABILITY_SAMPLES * 2:
        return {"periods": 0, "correlations": [], "stability_score": 0.0, "sign_consistency": 0.0}
    period_size = max(MIN_STABILITY_SAMPLES, len(dated) // 4)
    correlations: List[float] = []
    for start in range(0, len(dated), period_size):
        block = dated[start:start + period_size]
        pairs = [(number(row.get(feature)), target(row)) for row in block]
        clean = [(x, y) for x, y in pairs if x is not None and y is not None]
        if len(clean) >= MIN_STABILITY_SAMPLES:
            correlations.append(pearson([x for x, _ in clean], [float(y) for _, y in clean]))
    if not correlations:
        return {"periods": 0, "correlations": [], "stability_score": 0.0, "sign_consistency": 0.0}
    mean_abs = sum(abs(value) for value in correlations) / len(correlations)
    spread = max(correlations) - min(correlations)
    nonzero = [value for value in correlations if abs(value) > 0.005]
    positive = sum(value > 0 for value in nonzero)
    negative = sum(value < 0 for value in nonzero)
    consistency = max(positive, negative) / len(nonzero) if nonzero else 0.0
    score = max(0.0, min(1.0, consistency * (1.0 - min(1.0, spread / max(0.05, mean_abs * 4)))))
    return {
        "periods": len(correlations),
        "correlations": [round(value, 6) for value in correlations],
        "stability_score": round(score, 6),
        "sign_consistency": round(consistency, 6),
    }


def grade(score: float, samples: int, missing_rate: float, redundant: bool) -> str:
    adjusted = score
    if samples < 250:
        adjusted *= 0.8
    if missing_rate > 0.35:
        adjusted *= 0.75
    if redundant:
        adjusted *= 0.8
    if adjusted >= 0.70:
        return "A"
    if adjusted >= 0.52:
        return "B"
    if adjusted >= 0.34:
        return "C"
    if adjusted >= 0.18:
        return "D"
    return "F"


def build(target_date: str) -> Dict[str, Any]:
    all_rows = read_jsonl(HISTORY)
    rows = [row for row in all_rows if target(row) is not None]
    features = numeric_features(rows)

    correlation_matrix: List[Dict[str, Any]] = []
    redundant_features = set()
    feature_values: Dict[str, Dict[int, float]] = {}
    for feature in features:
        feature_values[feature] = {i: value for i, row in enumerate(rows) if (value := number(row.get(feature))) is not None}
    for i, left in enumerate(features):
        for right in features[i + 1:]:
            common = sorted(set(feature_values[left]) & set(feature_values[right]))
            if len(common) < MIN_FEATURE_SAMPLES:
                continue
            value = pearson([feature_values[left][j] for j in common], [feature_values[right][j] for j in common])
            if abs(value) >= 0.85:
                redundant_features.update((left, right))
                correlation_matrix.append({"feature_a": left, "feature_b": right, "samples": len(common), "correlation": round(value, 6), "redundancy_flag": True})

    audited: List[Dict[str, Any]] = []
    for feature in features:
        pairs = [(number(row.get(feature)), target(row)) for row in rows]
        clean = [(x, y) for x, y in pairs if x is not None and y is not None]
        if len(clean) < MIN_FEATURE_SAMPLES:
            continue
        xs, ys = [x for x, _ in clean], [int(y) for _, y in clean]
        corr = pearson(xs, [float(y) for y in ys])
        raw_auc = auc(clean)
        base_auc = 0.5 if raw_auc is None else raw_auc
        directional_auc = max(base_auc, 1.0 - base_auc)
        separation = quantile_separation(clean) or 0.0
        mi = mutual_information(clean)
        stability = period_stability(rows, feature)
        missing_rate = 1.0 - len(clean) / len(rows) if rows else 1.0
        signal_score = min(1.0, (
            min(abs(corr) / 0.15, 1.0) * 0.25
            + min(max(directional_auc - 0.5, 0.0) / 0.12, 1.0) * 0.30
            + min(abs(separation) / 0.20, 1.0) * 0.20
            + min(mi / 0.04, 1.0) * 0.10
            + stability["stability_score"] * 0.15
        ))
        is_redundant = feature in redundant_features
        feature_grade = grade(signal_score, len(clean), missing_rate, is_redundant)
        audited.append({
            "feature": feature,
            "samples": len(clean),
            "missing_rate": round(missing_rate, 6),
            "correlation": round(corr, 6),
            "direction": "positive" if corr >= 0 else "negative",
            "auc": None if raw_auc is None else round(raw_auc, 6),
            "directional_auc": round(directional_auc, 6),
            "quantile_separation": round(separation, 6),
            "mutual_information": round(mi, 6),
            "stability": stability,
            "redundant": is_redundant,
            "signal_score": round(signal_score, 6),
            "grade": feature_grade,
            "recommendation": "KEEP" if feature_grade in {"A", "B"} else "REVIEW" if feature_grade == "C" else "REMOVE_CANDIDATE",
        })

    audited.sort(key=lambda row: (row["signal_score"], row["directional_auc"]), reverse=True)
    rankings = [{"rank": index + 1, **row} for index, row in enumerate(audited)]
    keep = [row["feature"] for row in audited if row["recommendation"] == "KEEP"]
    review = [row["feature"] for row in audited if row["recommendation"] == "REVIEW"]
    remove = [row["feature"] for row in audited if row["recommendation"] == "REMOVE_CANDIDATE"]

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "summary": {
            "history_records": len(all_rows),
            "settled_records": len(rows),
            "features_audited": len(audited),
            "keep_features": len(keep),
            "review_features": len(review),
            "remove_candidates": len(remove),
            "status": "PASS" if len(rows) >= MIN_FEATURE_SAMPLES and audited else "WARN",
        },
        "features": audited,
    }
    correlations = {"generated_at_utc": report["generated_at_utc"], "high_correlation_pairs": correlation_matrix}
    recommended = {
        "generated_at_utc": report["generated_at_utc"],
        "keep": keep,
        "review": review,
        "remove_candidates": remove,
        "deployment_rule": "Do not remove features until market-specific rolling validation confirms equal or better out-of-sample performance.",
    }

    for path, payload in (
        (OUT_IMPORTANCE, report),
        (OUT_RANKINGS, {"generated_at_utc": report["generated_at_utc"], "features": rankings}),
        (OUT_CORRELATIONS, correlations),
        (OUT_RECOMMENDED, recommended),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    report = build(args.date)
    print("Sprint 21 Phase 1:", report["summary"])


if __name__ == "__main__":
    main()
