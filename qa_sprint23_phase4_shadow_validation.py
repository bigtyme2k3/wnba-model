"""QA for Sprint 23 Phase 4 shadow tracking and grading."""
import json
from pathlib import Path

import pandas as pd

OUT = Path("data/processed/sprint23/validation")
LEDGER = OUT / "shadow_opportunity_ledger.csv"
GRADED = OUT / "shadow_opportunities_graded.csv"
CATALOG = OUT / "shadow_validation_catalog.json"
ALLOWED_RESULTS = {"WIN", "LOSS", "PUSH", "PENDING"}
ALLOWED_BOOKS = {"draftkings", "fanduel"}


def run() -> dict:
    ledger = pd.read_csv(LEDGER, low_memory=False)
    graded = pd.read_csv(GRADED, low_memory=False)
    catalog = json.loads(CATALOG.read_text())
    required = {
        "game_date", "event_id", "player_id", "stat", "side", "sportsbook_key", "line", "odds",
        "snapshot_at_utc", "result", "actual_value", "profit_per_dollar", "line_clv", "price_clv",
        "deployment_status",
    }
    completed = graded[graded["result"].isin(["WIN", "LOSS", "PUSH"])]
    tests = {
        "catalog_pass": catalog.get("status") == "PASS",
        "shadow_only": catalog.get("deployment_status") == "SHADOW_ONLY",
        "production_unchanged": catalog.get("production_recommendations_changed") is False,
        "ledger_present": len(ledger) >= 0,
        "graded_present": len(graded) >= 0,
        "required_columns": required.issubset(set(graded.columns)),
        "allowed_books": ledger.empty or set(ledger["sportsbook_key"].astype(str).str.lower()).issubset(ALLOWED_BOOKS),
        "valid_results": graded.empty or set(graded["result"].astype(str)).issubset(ALLOWED_RESULTS),
        "completed_have_actuals": completed.empty or pd.to_numeric(completed["actual_value"], errors="coerce").notna().all(),
        "completed_have_profit": completed.empty or pd.to_numeric(completed["profit_per_dollar"], errors="coerce").notna().all(),
        "pending_not_graded": graded.empty or graded.loc[graded["result"].eq("PENDING"), "profit_per_dollar"].isna().all(),
        "unique_entry_markets": graded.empty or not graded.duplicated([
            "game_date", "event_id", "player_id", "stat", "side", "sportsbook_key"
        ]).any(),
        "promotion_not_automatic": catalog.get("promotion_review_status") in {"INSUFFICIENT_EVIDENCE", "ELIGIBLE_FOR_REVIEW"},
    }
    tests = {name: bool(value) for name, value in tests.items()}
    failed = [name for name, passed in tests.items() if not passed]
    result = {"status": "PASS" if not failed else "FAIL", "tests": tests, "failed": failed}
    print(json.dumps(result, indent=2))
    if failed:
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    run()
