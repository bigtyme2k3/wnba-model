"""Sprint 21 Phase 2: leakage-safe rolling feature-set validation."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HISTORY = Path("data/history/wnba_model_history.jsonl")
RECOMMENDED = Path("data/audit/recommended_feature_set.json")
RANKINGS = Path("data/audit/feature_rankings.json")
OUT_COMPARISON = Path("data/audit/feature_set_comparison.json")
OUT_ROLLING = Path("data/audit/rolling_validation_results.json")
OUT_BEST = Path("data/audit/best_feature_set.json")
OUT_MARKETS = Path("data/audit/market_feature_recommendations.json")

LEAKAGE_FIELDS = {
    "actual", "outcome", "result", "status", "profit", "payout", "settled",
    "closing_result", "hit", "won", "loss", "final_actual", "actual_value",
}
IDENTITY_FIELDS = {
    "date", "player", "team", "opponent", "game", "market", "stat", "selection",
    "signal", "sportsbook", "book", "history_key", "event_id", "id", "notes",
}
MIN_TRAIN = 300
MIN_VALID = 100
FOLDS = 4


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


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (ValueError, TypeError, json.JSONDecodeError):
        return default


def number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return float(value)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def outcome(row: Dict[str, Any]) -> Optional[int]:
    value = str(row.get("outcome") or row.get("result") or "").upper()
    return 1 if value == "WIN" else 0 if value == "LOSS" else None


def market(row: Dict[str, Any]) -> str:
    return str(row.get("stat") or row.get("market") or "UNKNOWN").upper()


def sigmoid(value: float) -> float:
    value = max(-35.0, min(35.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def fit_logistic(x: Sequence[Sequence[float]], y: Sequence[int], steps: int = 350, rate: float = 0.08, l2: float = 0.01) -> List[float]:
    if not x:
        return [0.0]
    weights = [0.0] * (len(x[0]) + 1)
    n = float(len(x))
    for _ in range(steps):
        gradient = [0.0] * len(weights)
        for row, target in zip(x, y):
            prediction = sigmoid(weights[0] + sum(w * value for w, value in zip(weights[1:], row)))
            error = prediction - target
            gradient[0] += error
            for index, value in enumerate(row, start=1):
                gradient[index] += error * value
        weights[0] -= rate * gradient[0] / n
        for index in range(1, len(weights)):
            weights[index] -= rate * (gradient[index] / n + l2 * weights[index])
    return weights


def predict(weights: Sequence[float], x: Sequence[Sequence[float]]) -> List[float]:
    return [sigmoid(weights[0] + sum(w * value for w, value in zip(weights[1:], row))) for row in x]


def auc(probabilities: Sequence[float], targets: Sequence[int]) -> Optional[float]:
    positives = [p for p, y in zip(probabilities, targets) if y == 1]
    negatives = [p for p, y in zip(probabilities, targets) if y == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            wins += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return wins / (len(positives) * len(negatives))


def brier(probabilities: Sequence[float], targets: Sequence[int]) -> Optional[float]:
    return sum((p - y) ** 2 for p, y in zip(probabilities, targets)) / len(targets) if targets else None


def log_loss(probabilities: Sequence[float], targets: Sequence[int]) -> Optional[float]:
    if not targets:
        return None
    total = 0.0
    for p, y in zip(probabilities, targets):
        p = max(1e-6, min(1 - 1e-6, p))
        total -= y * math.log(p) + (1 - y) * math.log(1 - p)
    return total / len(targets)


def ece(probabilities: Sequence[float], targets: Sequence[int], bins: int = 10) -> Optional[float]:
    if not targets:
        return None
    total = 0.0
    for bucket in range(bins):
        low, high = bucket / bins, (bucket + 1) / bins
        members = [(p, y) for p, y in zip(probabilities, targets) if low <= p < high or (bucket == bins - 1 and p == 1.0)]
        if members:
            avg_p = sum(p for p, _ in members) / len(members)
            hit = sum(y for _, y in members) / len(members)
            total += abs(avg_p - hit) * len(members) / len(targets)
    return total


def decile_spread(probabilities: Sequence[float], targets: Sequence[int]) -> Optional[float]:
    if len(targets) < 20:
        return None
    ordered = sorted(zip(probabilities, targets), key=lambda item: item[0])
    size = max(1, len(ordered) // 10)
    low, high = ordered[:size], ordered[-size:]
    return sum(y for _, y in high) / len(high) - sum(y for _, y in low) / len(low)


def safe_features(features: Iterable[str]) -> Tuple[List[str], List[str]]:
    kept, excluded = [], []
    for feature in features:
        key = str(feature)
        lowered = key.lower()
        if lowered in LEAKAGE_FIELDS or lowered in IDENTITY_FIELDS or lowered.startswith("actual"):
            excluded.append(key)
        elif key not in kept:
            kept.append(key)
    return kept, excluded


def available_numeric(rows: Sequence[Dict[str, Any]], minimum: int = 100) -> List[str]:
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        for key, value in row.items():
            if key.lower() in LEAKAGE_FIELDS or key.lower() in IDENTITY_FIELDS:
                continue
            if number(value) is not None:
                counts[key] += 1
    return sorted(key for key, count in counts.items() if count >= minimum)


def candidate_sets(rows: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, List[str]], List[str]]:
    rec = load_json(RECOMMENDED, {})
    rankings = load_json(RANKINGS, {})
    ranking_rows = rankings.get("features", rankings if isinstance(rankings, list) else [])
    ranked = [row.get("feature") for row in ranking_rows if isinstance(row, dict) and row.get("feature")]
    keep, excluded_keep = safe_features(rec.get("keep", []))
    review, excluded_review = safe_features(rec.get("review", []))
    numeric = available_numeric(rows)
    top_ranked, excluded_ranked = safe_features(ranked[:8])
    production, excluded_production = safe_features(numeric)
    engineered = [field for field in ["clv", "ev_pct", "edge_pct", "line", "american_odds", "book_count", "history_games"] if field in numeric]
    candidates = {
        "core": keep,
        "core_plus_review": list(dict.fromkeys(keep + review)),
        "minimal_ranked": top_ranked[:4],
        "core_plus_engineered": list(dict.fromkeys(keep + review + engineered)),
        "current_numeric": production,
    }
    candidates = {name: values for name, values in candidates.items() if values}
    return candidates, sorted(set(excluded_keep + excluded_review + excluded_ranked + excluded_production))


def rolling_splits(rows: Sequence[Dict[str, Any]]) -> List[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
    ordered = sorted(rows, key=lambda row: (str(row.get("date") or ""), str(row.get("history_key") or "")))
    if len(ordered) < MIN_TRAIN + MIN_VALID:
        return []
    validation_size = max(MIN_VALID, len(ordered) // (FOLDS + 3))
    splits = []
    first_end = len(ordered) - validation_size * FOLDS
    first_end = max(MIN_TRAIN, first_end)
    for fold in range(FOLDS):
        train_end = first_end + fold * validation_size
        valid_end = min(len(ordered), train_end + validation_size)
        train, valid = ordered[:train_end], ordered[train_end:valid_end]
        if len(train) >= MIN_TRAIN and len(valid) >= MIN_VALID:
            splits.append((train, valid))
    return splits


def matrices(train: Sequence[Dict[str, Any]], valid: Sequence[Dict[str, Any]], features: Sequence[str]) -> Tuple[List[List[float]], List[int], List[List[float]], List[int], List[str]]:
    usable = [feature for feature in features if any(number(row.get(feature)) is not None for row in train)]
    medians, scales = {}, {}
    for feature in usable:
        values = sorted(value for row in train if (value := number(row.get(feature))) is not None)
        if not values:
            medians[feature], scales[feature] = 0.0, 1.0
            continue
        mid = len(values) // 2
        median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        medians[feature], scales[feature] = median, max(math.sqrt(variance), 1e-6)

    def convert(source: Sequence[Dict[str, Any]]) -> Tuple[List[List[float]], List[int]]:
        x, y = [], []
        for row in source:
            target = outcome(row)
            if target is None:
                continue
            x.append([((number(row.get(feature)) if number(row.get(feature)) is not None else medians[feature]) - medians[feature]) / scales[feature] for feature in usable])
            y.append(target)
        return x, y

    train_x, train_y = convert(train)
    valid_x, valid_y = convert(valid)
    return train_x, train_y, valid_x, valid_y, usable


def evaluate(rows: Sequence[Dict[str, Any]], features: Sequence[str]) -> Dict[str, Any]:
    fold_results = []
    all_probabilities: List[float] = []
    all_targets: List[int] = []
    for fold, (train, valid) in enumerate(rolling_splits(rows), start=1):
        train_x, train_y, valid_x, valid_y, usable = matrices(train, valid, features)
        if not usable or len(set(train_y)) < 2 or len(set(valid_y)) < 2:
            continue
        weights = fit_logistic(train_x, train_y)
        probabilities = predict(weights, valid_x)
        all_probabilities.extend(probabilities)
        all_targets.extend(valid_y)
        fold_results.append({
            "fold": fold,
            "train_records": len(train_y),
            "validation_records": len(valid_y),
            "features_used": usable,
            "auc": round(auc(probabilities, valid_y) or 0.5, 6),
            "brier": round(brier(probabilities, valid_y) or 0.0, 6),
            "log_loss": round(log_loss(probabilities, valid_y) or 0.0, 6),
            "ece": round(ece(probabilities, valid_y) or 0.0, 6),
            "decile_spread": round(decile_spread(probabilities, valid_y) or 0.0, 6),
        })
    auc_value = auc(all_probabilities, all_targets)
    fold_aucs = [item["auc"] for item in fold_results]
    stability = 1.0 - min(1.0, (max(fold_aucs) - min(fold_aucs)) / 0.20) if fold_aucs else 0.0
    return {
        "features": list(features),
        "folds": fold_results,
        "fold_count": len(fold_results),
        "validation_records": len(all_targets),
        "auc": None if auc_value is None else round(auc_value, 6),
        "brier": None if not all_targets else round(brier(all_probabilities, all_targets) or 0.0, 6),
        "log_loss": None if not all_targets else round(log_loss(all_probabilities, all_targets) or 0.0, 6),
        "ece": None if not all_targets else round(ece(all_probabilities, all_targets) or 0.0, 6),
        "decile_spread": None if not all_targets else round(decile_spread(all_probabilities, all_targets) or 0.0, 6),
        "stability_score": round(stability, 6),
    }


def build(target_date: str) -> Dict[str, Any]:
    all_rows = read_jsonl(HISTORY)
    rows = [row for row in all_rows if outcome(row) is not None]
    candidates, leakage_excluded = candidate_sets(rows)
    evaluations = {name: evaluate(rows, features) for name, features in candidates.items()}
    valid = [(name, result) for name, result in evaluations.items() if result.get("auc") is not None and result.get("fold_count", 0) >= 2]
    valid.sort(key=lambda item: (item[1]["auc"], item[1].get("decile_spread") or -1, -(item[1].get("brier") or 1)), reverse=True)
    best_name, best = valid[0] if valid else (None, None)
    baseline = evaluations.get("current_numeric")
    gate_reasons = []
    if not best:
        gate_reasons.append("no_valid_feature_set")
    else:
        if best["auc"] < 0.53:
            gate_reasons.append("auc_below_0_53")
        if (best.get("decile_spread") or 0.0) < 0.08:
            gate_reasons.append("decile_spread_below_0_08")
        if best.get("stability_score", 0.0) < 0.50:
            gate_reasons.append("unstable_across_folds")
        if baseline and baseline.get("auc") is not None and best["auc"] < baseline["auc"] + 0.01:
            gate_reasons.append("insufficient_auc_improvement_over_current")
    deployment_gate = "PASS" if not gate_reasons else "HOLD"

    markets: Dict[str, Any] = {}
    by_market: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_market[market(row)].append(row)
    for key, market_rows in sorted(by_market.items()):
        if len(market_rows) < MIN_TRAIN + MIN_VALID:
            continue
        market_results = {name: evaluate(market_rows, features) for name, features in candidates.items()}
        ranked = [(name, result) for name, result in market_results.items() if result.get("auc") is not None]
        ranked.sort(key=lambda item: item[1]["auc"], reverse=True)
        markets[key] = {
            "records": len(market_rows),
            "best_feature_set": ranked[0][0] if ranked else None,
            "best_auc": ranked[0][1]["auc"] if ranked else None,
            "evaluations": market_results,
        }

    now = datetime.now(timezone.utc).isoformat()
    summary = {
        "history_records": len(all_rows),
        "settled_records": len(rows),
        "candidate_sets": len(candidates),
        "best_feature_set": best_name,
        "best_auc": None if not best else best["auc"],
        "best_decile_spread": None if not best else best.get("decile_spread"),
        "deployment_gate": deployment_gate,
        "status": "PASS" if valid else "WARN",
    }
    comparison = {
        "generated_at_utc": now,
        "target_date": target_date,
        "summary": summary,
        "leakage_excluded": leakage_excluded,
        "candidate_sets": candidates,
        "evaluations": evaluations,
        "deployment_gate_reasons": gate_reasons,
    }
    rolling = {"generated_at_utc": now, "target_date": target_date, "feature_sets": evaluations}
    best_payload = {
        "generated_at_utc": now,
        "target_date": target_date,
        "deployment_gate": deployment_gate,
        "deployment_gate_reasons": gate_reasons,
        "best_feature_set": best_name,
        "features": [] if not best else best["features"],
        "metrics": best,
        "leakage_policy": "Postgame and outcome-derived fields are always excluded.",
    }
    market_payload = {"generated_at_utc": now, "target_date": target_date, "markets": markets}
    for path, payload in ((OUT_COMPARISON, comparison), (OUT_ROLLING, rolling), (OUT_BEST, best_payload), (OUT_MARKETS, market_payload)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    report = build(args.date)
    print("Sprint 21 Phase 2:", report["summary"])


if __name__ == "__main__":
    main()
