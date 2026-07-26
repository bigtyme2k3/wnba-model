"""QA for Validation Week Commit 4 signal performance outputs."""
from __future__ import annotations

import json
from pathlib import Path

SOURCE = Path("data/validation/live_prediction_results.json")
OUT = Path("data/validation/signal_performance.json")
DASH = Path("data/dashboard/wnba_signal_performance_summary.json")
VALID_GRADES = {"A+", "A", "B", "C", "RESEARCH", "AVOID"}


def load(path: Path):
    if not path.exists():
        raise AssertionError(f"Missing output: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def rate(value):
    return value is None or 0 <= float(value) <= 1


def main() -> None:
    source = load(SOURCE) if SOURCE.exists() else {"records": []}
    output = load(OUT)
    dash = load(DASH)

    graded = [r for r in source.get("records", []) if r.get("validation_status") == "GRADED" and r.get("grade") in {"WIN", "LOSS", "PUSH"}]
    signals = output.get("signals", [])
    combos = output.get("combinations", [])

    assert output.get("graded_records") == len(graded)
    assert dash.get("graded_records") == len(graded)
    assert dash.get("signals_analyzed") == len(signals)
    assert dash.get("signal_combinations") == len(combos)
    assert dash.get("status") == ("READY" if graded else "STANDBY")

    signal_names = [x.get("signal") for x in signals]
    combo_names = [x.get("combination") for x in combos]
    assert len(signal_names) == len(set(signal_names)), "Duplicate signal rows"
    assert len(combo_names) == len(set(combo_names)), "Duplicate combination rows"

    for row in signals + combos:
        assert row.get("grade") in VALID_GRADES
        assert 0 <= float(row.get("signal_score", 0)) <= 100
        assert rate(row.get("hit_rate"))
        assert rate(row.get("within_half_point_rate"))
        assert rate(row.get("within_one_point_rate"))
        assert int(row.get("records", 0)) == int(row.get("wins", 0)) + int(row.get("losses", 0)) + int(row.get("pushes", 0))
        assert int(row.get("decided", 0)) == int(row.get("wins", 0)) + int(row.get("losses", 0))
        if row.get("average_closing_line_error") is not None:
            assert float(row["average_closing_line_error"]) >= 0
        if row.get("average_absolute_clv") is not None:
            assert float(row["average_absolute_clv"]) >= 0

    if not graded:
        assert signals == []
        assert combos == []
        assert dash.get("best_signal") is None
        assert dash.get("best_combination") is None

    print(json.dumps({
        "status": "PASS",
        "graded_records": len(graded),
        "signals": len(signals),
        "combinations": len(combos),
        "qualified_signals": dash.get("qualified_signals"),
        "qualified_combinations": dash.get("qualified_combinations"),
    }, indent=2))


if __name__ == "__main__":
    main()
