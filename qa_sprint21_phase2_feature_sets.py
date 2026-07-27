"""QA for Sprint 21 Phase 2 feature-set rolling validation."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import validate_sprint21_phase2_feature_sets as validator


def fixture_rows() -> list[dict]:
    rows = []
    for i in range(900):
        win = (i % 10) < 6
        rows.append({
            "date": f"2026-{1 + (i // 75) % 12:02d}-{1 + i % 28:02d}",
            "outcome": "WIN" if win else "LOSS",
            "market": "PTS" if i % 2 == 0 else "REB",
            "good_signal": (0.8 if win else 0.2) + (i % 7) * 0.001,
            "weak_signal": float((i * 13) % 17),
            "actual": 25 if win else 12,
            "ev_pct": 0.12 if win else -0.03,
            "clv": 1.5 if win else -0.7,
        })
    return rows


def run() -> dict:
    tests = 0
    safe, excluded = validator.safe_features(["good_signal", "actual", "outcome"])
    assert safe == ["good_signal"]
    assert set(excluded) == {"actual", "outcome"}
    tests += 1

    assert validator.auc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    tests += 1

    rows = fixture_rows()
    splits = validator.rolling_splits(rows)
    assert len(splits) >= 2
    assert all(len(train) >= validator.MIN_TRAIN and len(valid) >= validator.MIN_VALID for train, valid in splits)
    tests += 1

    result = validator.evaluate(rows, ["good_signal"])
    assert result["fold_count"] >= 2
    assert result["auc"] is not None and result["auc"] >= 0.95
    assert result["decile_spread"] is not None and result["decile_spread"] > 0
    tests += 1

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        history = root / "history.jsonl"
        history.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        recommended = root / "recommended.json"
        recommended.write_text(json.dumps({"keep": ["good_signal", "actual"], "review": ["ev_pct"], "remove_candidates": []}), encoding="utf-8")
        rankings = root / "rankings.json"
        rankings.write_text(json.dumps({"features": [{"feature": "good_signal"}, {"feature": "weak_signal"}]}), encoding="utf-8")
        old = (validator.HISTORY, validator.RECOMMENDED, validator.RANKINGS, validator.OUT_COMPARISON, validator.OUT_ROLLING, validator.OUT_BEST, validator.OUT_MARKETS)
        validator.HISTORY = history
        validator.RECOMMENDED = recommended
        validator.RANKINGS = rankings
        validator.OUT_COMPARISON = root / "comparison.json"
        validator.OUT_ROLLING = root / "rolling.json"
        validator.OUT_BEST = root / "best.json"
        validator.OUT_MARKETS = root / "markets.json"
        try:
            report = validator.build("2026-07-27")
        finally:
            (validator.HISTORY, validator.RECOMMENDED, validator.RANKINGS, validator.OUT_COMPARISON, validator.OUT_ROLLING, validator.OUT_BEST, validator.OUT_MARKETS) = old
        assert "actual" in report["leakage_excluded"]
        assert report["summary"]["candidate_sets"] >= 2
        assert (root / "comparison.json").exists() and (root / "best.json").exists()
        tests += 1

    return {"status": "PASS", "tests": tests}


if __name__ == "__main__":
    print(json.dumps(run()))
