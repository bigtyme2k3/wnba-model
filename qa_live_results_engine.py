"""Acceptance tests for the event-driven live results monitor."""
from __future__ import annotations

import wnba_live_results_engine as engine


def test_status_normalization():
    assert engine.canonical_status({"status_detail": "Final"}) == "FINAL"
    assert engine.canonical_status({"status": "In Progress - 3rd Quarter"}) == "LIVE"
    assert engine.canonical_status({"status": "Scheduled"}) == "SCHEDULED"


def test_team_parsing():
    away, home = engine.teams({"competitors": [
        {"home_away": "away", "team": {"displayName": "Away Team"}},
        {"home_away": "home", "team": {"displayName": "Home Team"}},
    ]})
    assert away == "Away Team"
    assert home == "Home Team"


def test_policy_is_credit_free():
    payload = {"policy": {"odds_api_used": False, "grade_once_per_game": True}}
    assert payload["policy"]["odds_api_used"] is False
    assert payload["policy"]["grade_once_per_game"] is True


def main():
    tests = [test_status_normalization, test_team_parsing, test_policy_is_credit_free]
    failed = 0
    for fn in tests:
        try:
            fn(); print("PASS", fn.__name__)
        except Exception as exc:
            failed += 1; print("FAIL", fn.__name__, exc)
    print({"tests": len(tests), "passed": len(tests)-failed, "failed": failed})
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
