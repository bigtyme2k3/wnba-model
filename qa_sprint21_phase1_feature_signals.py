"""QA for Sprint 21 Phase 1 feature signal audit."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import audit_sprint21_phase1_feature_signals as audit


def fixture_rows() -> list[dict]:
    rows = []
    for i in range(240):
        win = i % 2 == 0
        rows.append({
            "date": f"2026-06-{1 + (i % 28):02d}",
            "outcome": "WIN" if win else "LOSS",
            "strong_signal": 0.9 if win else 0.1,
            "inverse_signal": 0.1 if win else 0.9,
            "noise": float((i * 17) % 31),
            "duplicate_signal": 0.9 if win else 0.1,
            "partly_missing": None if i % 3 == 0 else (1.0 if win else 0.0),
            "player": f"P{i}",
        })
    return rows


def run() -> dict:
    tests = 0
    assert round(audit.pearson([1, 2, 3], [1, 2, 3]), 6) == 1.0
    tests += 1

    assert audit.auc([(0.9, 1), (0.8, 1), (0.2, 0), (0.1, 0)]) == 1.0
    tests += 1

    rows = fixture_rows()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        history = root / "history.jsonl"
        history.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        old = (audit.HISTORY, audit.OUT_IMPORTANCE, audit.OUT_RANKINGS, audit.OUT_CORRELATIONS, audit.OUT_RECOMMENDED)
        audit.HISTORY = history
        audit.OUT_IMPORTANCE = root / "importance.json"
        audit.OUT_RANKINGS = root / "rankings.json"
        audit.OUT_CORRELATIONS = root / "correlations.json"
        audit.OUT_RECOMMENDED = root / "recommended.json"
        try:
            report = audit.build("2026-07-27")
        finally:
            audit.HISTORY, audit.OUT_IMPORTANCE, audit.OUT_RANKINGS, audit.OUT_CORRELATIONS, audit.OUT_RECOMMENDED = old

        by_name = {row["feature"]: row for row in report["features"]}
        assert by_name["strong_signal"]["grade"] in {"A", "B"}
        assert by_name["strong_signal"]["directional_auc"] >= 0.99
        tests += 1

        assert by_name["inverse_signal"]["direction"] == "negative"
        assert by_name["inverse_signal"]["directional_auc"] >= 0.99
        tests += 1

        correlation_payload = json.loads((root / "correlations.json").read_text())
        assert any({pair["feature_a"], pair["feature_b"]} == {"strong_signal", "duplicate_signal"} for pair in correlation_payload["high_correlation_pairs"])
        tests += 1

        recommended = json.loads((root / "recommended.json").read_text())
        assert recommended["deployment_rule"]
        assert (root / "importance.json").exists() and (root / "rankings.json").exists()
        tests += 1

    return {"status": "PASS", "tests": tests}


if __name__ == "__main__":
    print(json.dumps(run()))
