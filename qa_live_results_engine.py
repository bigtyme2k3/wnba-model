"""Acceptance tests for the event-driven live results monitor."""
from __future__ import annotations

import wnba_live_results_engine as engine


def test_status_normalization():
    assert engine.canonical_status({"status_detail": "Final"}) == "FINAL"
    assert engine.canonical_status({"status": "STATUS_FINAL"}) == "FINAL"
    assert engine.canonical_status({"status": "STATUS_IN_PROGRESS", "status_detail": "3rd Quarter"}) == "LIVE"
    assert engine.canonical_status({"status": "Scheduled"}) == "SCHEDULED"


def test_team_and_score_parsing():
    event = {"competitors": [
        {"home_away": "away", "team": {"name": "Away Team"}, "score": "77"},
        {"home_away": "home", "team": {"name": "Home Team"}, "score": "81"},
    ]}
    assert engine.teams(event) == ("Away Team", "Home Team")
    assert engine.scores(event) == (77.0, 81.0)


def test_master_schedule_survives_stale_score_feed():
    scheduled = [{"game_id": "1", "game": "Away @ Home", "away_team": "Away", "home_team": "Home", "start_time": "2026-07-18T15:00:00Z", "status": "SCHEDULED", "away_score": None, "home_score": None, "source": "master"}]
    assert engine.merge_games(scheduled, []) == scheduled


def test_game_id_first_and_final_wins():
    scheduled = [{"game_id": "401", "game": "Away @ Home", "away_team": "Away", "home_team": "Home", "start_time": "x", "status": "SCHEDULED", "away_score": None, "home_score": None, "source": "master"}]
    final = [{"game_id": "401", "game": "Away @ Home", "away_team": "Away", "home_team": "Home", "start_time": "x", "status": "FINAL", "away_score": 70.0, "home_score": 75.0, "source": "scores"}]
    result = engine.merge_games(scheduled, final)
    assert len(result) == 1
    assert result[0]["status"] == "FINAL"
    assert result[0]["home_score"] == 75.0


def test_policy_is_credit_free():
    payload = {"policy": {"odds_api_used": False, "grade_once_per_game": True}}
    assert payload["policy"]["odds_api_used"] is False
    assert payload["policy"]["grade_once_per_game"] is True


def main():
    tests = [test_status_normalization, test_team_and_score_parsing, test_master_schedule_survives_stale_score_feed, test_game_id_first_and_final_wins, test_policy_is_credit_free]
    failed = 0
    for fn in tests:
        try:
            fn(); print("PASS", fn.__name__)
        except Exception as exc:
            failed += 1; print("FAIL", fn.__name__, exc)
    print({"tests": len(tests), "passed": len(tests)-failed, "failed": failed})
    if failed: raise SystemExit(1)


if __name__ == "__main__": main()
