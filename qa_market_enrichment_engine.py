"""QA for Validation Week Commit 6 market enrichment engine."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("data/forecast/enriched_market_predictions.json")
DASH = Path("data/dashboard/wnba_market_enrichment_summary.json")


def load(path: Path):
    assert path.exists(), f"Missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    payload = load(OUT)
    summary = load(DASH)
    records = payload.get("predictions", [])
    assert isinstance(records, list)
    ids = [r.get("market_id") for r in records]
    assert all(ids), "Missing market_id"
    assert len(ids) == len(set(ids)), "Duplicate enriched market_id"
    for row in records:
        assert row.get("enrichment_source") in {"OPPORTUNITY_SCANNER", "DERIVED_MARKET_CONTEXT"}
        assert row.get("market_quality_grade") in {"A+", "A", "B", "C", "RESEARCH", "AVOID"}
        assert row.get("scanner_recommendation") in {"BET_NOW", "WATCH", "PASS"}
        assert row.get("tier") in {"ELITE", "STRONG", "WATCH", "LOW", "AVOID"}
        for key in ("opportunity_score", "volatility_score", "sportsbook_edge_score", "clv_confidence"):
            value = row.get(key)
            assert value is not None and 0 <= float(value) <= 100, f"Invalid {key}: {row.get('market_id')}"
        expected = row.get("expected_closing_value")
        assert isinstance(expected, dict)
        if row.get("forecast_status") != "MODEL_READY":
            assert float(row.get("opportunity_score") or 0) <= 49
            assert row.get("scanner_recommendation") != "BET_NOW"
    assert summary.get("predictions_enriched") == len(records)
    assert summary.get("non_null_opportunity_scores") == len(records)
    assert summary.get("non_null_signals") == len(records)
    assert summary.get("non_null_volatility") == len(records)
    assert sum(summary.get("grade_counts", {}).values()) == len(records)
    expected_status = "READY" if records else "STANDBY"
    assert summary.get("status") == expected_status
    print(json.dumps({
        "status": "PASS",
        "predictions_enriched": len(records),
        "model_ready": summary.get("model_ready", 0),
        "derived_context": summary.get("derived_context", 0),
        "opportunity_context": summary.get("opportunity_context", 0),
    }, indent=2))


if __name__ == "__main__":
    main()
