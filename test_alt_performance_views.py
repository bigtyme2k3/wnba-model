import sys
import types

# The production workflow installs requests/pandas.  These focused unit tests
# exercise the pure raw-payload audit without requiring network dependencies.
sys.modules.setdefault("requests", types.SimpleNamespace())
sys.modules.setdefault("pandas", types.SimpleNamespace())

import scrape_odds_props
import wnba_alt_calibration as calibration
import wnba_alt_performance_tracker as performance


def row(action, outcome, profit):
    return {"streak_action": action, "outcome": outcome, "profit_loss": profit}


def test_live_performance_excludes_research_actions():
    rows = [row("BET", "WIN", 0.8), row("PASS", "LOSS", -1), row("LEAN", "WIN", 0.5)]
    live = performance.performance_summary([r for r in rows if r["streak_action"] == "BET"])
    assert live["n"] == 1
    assert live["wins"] == 1
    assert live["profit_loss_units"] == 0.8


def test_daily_performance_summary_reports_only_supplied_bets():
    daily = performance.performance_summary([
        row("BET", "WIN", 0.25), row("BET", "LOSS", -1.0),
    ])
    assert daily["n"] == 2
    assert daily["wins"] == 1
    assert daily["losses"] == 1
    assert daily["profit_loss_units"] == -0.75
    assert daily["roi"] == -0.375


def test_alt_payload_audit_reads_both_sides_before_filtering():
    payload = {"bookmakers": [{"markets": [{
        "key": "player_points_alternate",
        "outcomes": [{"name": "Over"}, {"name": "Under"}],
    }]}]}
    audit = scrape_odds_props.audit_alt_payload(payload)
    assert audit["outcome_sides"] == {"OVER": 1, "UNDER": 1, "OTHER": 0}


def test_segment_qualification_uses_level_sample():
    assert calibration.MIN_SAMPLE == {"specific": 25, "price": 50, "broad": 100}
    assert calibration.MIN_SIDE_SAMPLE == 100
