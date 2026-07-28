from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

OUT = Path("data/processed/sprint24")
SHORTLIST = OUT / "shadow_governed_shortlist.csv"
AUDIT = OUT / "shadow_governance_audit.csv"
CATALOG = OUT / "shadow_governance_catalog.json"


def run() -> dict:
    catalog = json.loads(CATALOG.read_text())
    shortlist = pd.read_csv(SHORTLIST, low_memory=False) if SHORTLIST.exists() and SHORTLIST.stat().st_size else pd.DataFrame()
    audit = pd.read_csv(AUDIT, low_memory=False) if AUDIT.exists() and AUDIT.stat().st_size else pd.DataFrame()

    tests = {
        "catalog_pass": catalog.get("status") in {"PASS", "EMPTY"},
        "shadow_only": catalog.get("deployment_status") == "SHADOW_ONLY",
        "production_unchanged": catalog.get("production_recommendations_changed") is False,
        "staking_disabled": catalog.get("staking_enabled") is False,
        "audit_present": AUDIT.exists(),
        "shortlist_present": SHORTLIST.exists(),
        "allowed_books_only": shortlist.empty or set(shortlist["sportsbook_key"].astype(str).str.lower()).issubset({"draftkings", "fanduel"}),
        "positive_ev_only": shortlist.empty or (pd.to_numeric(shortlist["expected_value_per_dollar"], errors="coerce") >= 0.03).all(),
        "probability_edge_floor": shortlist.empty or (pd.to_numeric(shortlist["probability_edge"], errors="coerce") >= 0.025).all(),
        "feature_ready_only": shortlist.empty or shortlist["feature_ready"].astype(str).str.lower().isin(["true", "1", "yes"]).all(),
        "maximum_total_respected": len(shortlist) <= 20,
        "maximum_player_exposure": shortlist.empty or shortlist.groupby("player_id").size().max() <= 2,
        "maximum_game_exposure": shortlist.empty or shortlist.groupby("event_id").size().max() <= 6,
        "maximum_stat_exposure": shortlist.empty or shortlist.groupby("stat").size().max() <= 6,
        "zero_research_stake": shortlist.empty or (pd.to_numeric(shortlist["research_stake_units"], errors="coerce").fillna(0) == 0).all(),
        "unique_governance_ranks": shortlist.empty or shortlist["governance_rank"].is_unique,
    }
    failed = [name for name, passed in tests.items() if not bool(passed)]
    result = {"status": "PASS" if not failed else "FAIL", "tests": {k: bool(v) for k, v in tests.items()}, "failed": failed}
    print(json.dumps(result, indent=2))
    if failed:
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    run()
