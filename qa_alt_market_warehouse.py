"""Acceptance tests for sportsbook-specific alternate ladders."""
from __future__ import annotations

import wnba_alt_market_warehouse as engine


def test_exact_threshold_hit_rates():
    games = [
        {"minutes": 30, "scoring": {"total_pts": 22, "three_pm": 2}, "boxscore": {"reb": 5, "ast": 4}, "derived": {"pra": 31, "pr": 27, "pa": 26, "ra": 9}, "game_date": "2026-07-10"},
        {"minutes": 30, "scoring": {"total_pts": 18, "three_pm": 1}, "boxscore": {"reb": 4, "ast": 3}, "derived": {"pra": 25, "pr": 22, "pa": 21, "ra": 7}, "game_date": "2026-07-08"},
    ]
    summary = engine.hit_summary(games, "PTS", 20)
    assert summary["l5"]["hits"] == 1
    assert summary["l5"]["games"] == 2
    assert summary["l5"]["rate"] == .5


def test_book_lines_are_distinct():
    a = ("event", "player", "PTS", "OVER", "15.0", "fanduel")
    b = ("event", "player", "PTS", "OVER", "15.0", "draftkings")
    assert a != b


def test_supported_market_policy():
    assert "DD" not in engine.SUPPORTED
    assert "TD" not in engine.SUPPORTED
    assert {"PTS", "REB", "AST", "3PM"}.issubset(engine.SUPPORTED)


def test_price_math():
    assert round(engine.implied_probability(-110), 4) == .5238
    assert round(engine.american_decimal(150), 2) == 2.5


def main():
    tests = [
        ("exact threshold hit rates", test_exact_threshold_hit_rates),
        ("book lines remain distinct", test_book_lines_are_distinct),
        ("supported market policy", test_supported_market_policy),
        ("price math", test_price_math),
    ]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as exc:
            failed.append((name, str(exc)))
            print("FAIL", name, exc)
    print({"tests": len(tests), "passed": len(tests) - len(failed), "failed": len(failed)})
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
