"""QA for Sprint 23 Phase 3 shadow market opportunity scoring."""
import json
from pathlib import Path

import pandas as pd

OUT = Path("data/processed/sprint23")
DATA = OUT / "props_market_opportunities_shadow.csv"
CATALOG = OUT / "props_market_opportunity_catalog.json"
ALLOWED_BOOKS = {"draftkings", "fanduel"}


def run() -> dict:
    df = pd.read_csv(DATA, low_memory=False)
    catalog = json.loads(CATALOG.read_text())
    empty_ok = catalog["status"] == "EMPTY" and len(df) == 0
    tests = {
        "catalog_status_valid": catalog["status"] in {"PASS", "EMPTY"},
        "shadow_only": catalog["deployment_status"] == "SHADOW_ONLY",
        "production_unchanged": catalog["production_recommendations_changed"] is False,
        "allowed_books_only": empty_ok or set(df["sportsbook_key"].astype(str).str.lower()).issubset(ALLOWED_BOOKS),
        "required_columns": all(c in df.columns for c in [
            "player", "stat", "side", "line", "odds", "projection", "model_probability",
            "implied_probability", "expected_value_per_dollar", "deployment_status"
        ]),
        "probabilities_bounded": empty_ok or (
            pd.to_numeric(df["model_probability"], errors="coerce").between(0, 1).all()
            and pd.to_numeric(df["implied_probability"], errors="coerce").between(0, 1).all()
        ),
        "finite_scores": empty_ok or pd.to_numeric(df["expected_value_per_dollar"], errors="coerce").notna().all(),
        "valid_sides": empty_ok or set(df["side"].astype(str)).issubset({"OVER", "UNDER"}),
        "unique_book_market_rows": empty_ok or not df.duplicated([
            "event_id", "player", "stat", "side", "sportsbook_key", "line"
        ]).any(),
    }
    failed = [name for name, passed in tests.items() if not passed]
    result = {"status": "PASS" if not failed else "FAIL", "tests": tests, "failed": failed}
    print(json.dumps(result, indent=2))
    if failed:
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    run()
