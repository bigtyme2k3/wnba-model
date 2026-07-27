"""QA for Sprint 20.5 Phase C simulation calibration audit."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import audit_phase_c_simulation_calibration as audit


def main() -> None:
    assert audit.probability(75) == 0.75
    assert audit.probability(0.75) == 0.75
    assert audit.probability(150) is None
    assert audit.outcome({"outcome": "WIN"}) == 1
    assert audit.outcome({"result": "LOSS"}) == 0
    assert audit.outcome({"outcome": "PUSH"}) is None

    perfect = [(0.8, 1)] * 8 + [(0.2, 0)] * 2
    assert round(audit.brier(perfect), 6) == 0.04
    assert audit.log_loss(perfect) is not None

    overconfident = [(0.99, 1 if i % 2 == 0 else 0) for i in range(100)]
    metrics = audit.calibration_metrics(overconfident)
    assert metrics["samples"] == 100
    assert metrics["actual_win_rate"] == 0.5
    assert metrics["global_calibration_gap"] < -0.45
    candidates = audit.candidate_calibrations(overconfident)
    assert candidates["status"] == "EVALUATED"
    assert candidates["best_candidate"]["method"] != "identity"
    assert candidates["log_loss_improvement"] > 0

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        history = root / "history.jsonl"
        rows = []
        for i in range(60):
            rows.append({
                "history_key": f"k{i}", "date": "2026-07-27", "player": f"P{i}",
                "game": "A @ B", "stat": "PTS", "signal": "OVER",
                "simulation_probability": 0.95 if i < 10 else 0.70,
                "confidence": 0.80, "final_score": 75, "consensus_score": 72,
                "outcome": "WIN" if i % 2 == 0 else "LOSS",
            })
        history.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

        original = (audit.MODEL_HISTORY, audit.REPORT_OUT, audit.CURVE_OUT, audit.DISTRIBUTION_OUT)
        audit.MODEL_HISTORY = history
        audit.REPORT_OUT = root / "report.json"
        audit.CURVE_OUT = root / "curve.json"
        audit.DISTRIBUTION_OUT = root / "distribution.json"
        try:
            report = audit.build("2026-07-27")
            assert report["summary"]["target_probability_records"] == 60
            assert report["summary"]["settled_probability_records"] == 60
            assert report["summary"]["target_extreme_probability_records"] == 10
            assert report["summary"]["status"] == "WARN"
            assert audit.REPORT_OUT.exists()
            assert audit.CURVE_OUT.exists()
            assert audit.DISTRIBUTION_OUT.exists()
            curve = json.loads(audit.CURVE_OUT.read_text(encoding="utf-8"))
            distribution = json.loads(audit.DISTRIBUTION_OUT.read_text(encoding="utf-8"))
            assert curve["samples"] == 60
            assert sum(row["count"] for row in distribution["bands"]) == 60
        finally:
            audit.MODEL_HISTORY, audit.REPORT_OUT, audit.CURVE_OUT, audit.DISTRIBUTION_OUT = original

    print("Sprint 20.5 Phase C QA passed")


if __name__ == "__main__":
    main()
