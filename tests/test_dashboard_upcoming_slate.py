#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.wnba_dashboard_slate_context import resolve_dashboard_slate_context
from scripts import wnba_s19_m02_prop_source as prop_source
from scripts.wnba_s19_m02_predictions import approved_supported_bets

TARGET = "2026-09-17"
GAME = "Test Away @ Test Home"
BOOKS = ["draftkings", "fanatics", "fanduel"]


def write_json(root: Path, relative_path: str, payload: dict) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def break_context() -> SimpleNamespace:
    return SimpleNamespace(
        current_date="2026-09-14",
        target_date="2026-09-14",
        mode="break",
        next_slate_date=TARGET,
        reason="no_games_today_next_slate_confirmed",
    )


def write_ready_stack(root: Path, *, injury_verified: bool = False) -> None:
    common = {"target_date": TARGET}
    write_json(root, "data/dashboard/wnba_master.json", {
        **common,
        "today_games": [{"game": GAME}],
    })
    write_json(root, "data/dashboard/wnba_player_props.json", {
        **common,
        "row_count": 1,
        "sportsbooks_allowed": BOOKS,
        "sportsbooks_observed": ["draftkings", "fanduel"],
        "unsupported_bookmakers_rejected": [],
        "rows": [{
            "game": GAME,
            "books": [
                {"book": "DraftKings", "side": "OVER", "price": -110},
                {"book": "FanDuel", "side": "UNDER", "price": -105},
            ],
        }],
    })
    write_json(root, "data/dashboard/wnba_daily_canonical_manifest.json", {
        **common,
        "status": "PASS",
        "game_count": 1,
        "player_prop_rows": 1,
        "sportsbooks_allowed": BOOKS,
        "sportsbooks_observed": ["draftkings", "fanduel"],
    })
    write_json(root, "data/dashboard/wnba_sprint2_predictions.json", {
        **common,
        "status": "PASS",
        "games": [{"game": GAME}],
    })
    write_json(root, "data/dashboard/wnba_injury_intelligence.json", {
        **common,
        "source_only": True,
        "injury_source_verified": injury_verified,
    })
    write_json(root, "data/dashboard/wnba_sprint2_phase2.json", {
        **common,
        "status": "PASS",
        "games": [{"game": GAME}],
    })
    write_json(root, "data/dashboard/wnba_s19_m02_predictions.json", {
        **common,
        "status": "READY",
        "games": [{"game": GAME}],
        "player_props": [{"player": "Test Player", "game": GAME}],
        "best_bets": [],
        "portfolio": [],
        "summary": {
            "player_prop_predictions": 1,
            "bet_player_props": 0,
            "v5_best_bets": 0,
            "v5_portfolio_rows": 0,
        },
    })
    write_json(root, "data/dashboard/wnba_s19_m02_prediction_audit.json", {
        **common,
        "status": "READY",
        "player_prop_predictions": 1,
        "all_rendered_props_exact_current_slate": True,
        "actionable_out_props": 0,
        "phase2_best_bets_fallback_enabled": False,
        "phase2_portfolio_fallback_enabled": False,
    })
    write_json(root, "data/dashboard/wnba_projection_integrity_audit.json", {
        **common,
        "status": "PASS",
        "violation_count": 0,
    })
    write_json(root, "data/dashboard/wnba_tab_freshness.json", common)
    write_json(root, "data/dashboard/wnba_alt_market_warehouse.json", {
        "target_date": "2026-08-31",
        "rows": [],
    })
    write_json(root, "data/dashboard/wnba_alt_streaks.json", {
        "target_date": "2026-08-31",
        "rows": [],
    })


class DashboardUpcomingSlateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="wnba-upcoming-dashboard-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_complete_next_slate_stack_exits_maintenance(self) -> None:
        write_ready_stack(self.root)
        context = resolve_dashboard_slate_context(break_context(), root=self.root)

        self.assertEqual(context.target_date, TARGET)
        self.assertEqual(context.deployment_mode, "upcoming")
        self.assertTrue(context.prepared_upcoming)
        self.assertFalse(context.maintenance_break)
        self.assertTrue(context.source_stack_ready)
        self.assertFalse(context.injury_source_verified)
        self.assertFalse(context.recommendations_actionable)
        self.assertFalse(context.alt_current_source)
        self.assertFalse(context.paid_api_called)
        self.assertEqual(context.game_count, 1)
        self.assertEqual(context.standard_prop_rows, 1)

    def test_unsupported_book_fails_closed_to_break_mode(self) -> None:
        write_ready_stack(self.root)
        path = self.root / "data/dashboard/wnba_player_props.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["sportsbooks_observed"].append("caesars")
        payload["rows"][0]["books"].append({"book": "Caesars", "side": "OVER", "price": -110})
        path.write_text(json.dumps(payload), encoding="utf-8")

        context = resolve_dashboard_slate_context(break_context(), root=self.root)

        self.assertEqual(context.deployment_mode, "break")
        self.assertTrue(context.maintenance_break)
        self.assertFalse(context.prepared_upcoming)
        self.assertIn("sportsbooks:unsupported_book_observed", context.source_errors)

    def test_unverified_injury_actionable_payload_fails_closed(self) -> None:
        write_ready_stack(self.root)
        path = self.root / "data/dashboard/wnba_s19_m02_predictions.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["best_bets"] = [{"player": "Unsafe Bet"}]
        payload["summary"]["bet_player_props"] = 1
        payload["summary"]["v5_best_bets"] = 1
        path.write_text(json.dumps(payload), encoding="utf-8")

        context = resolve_dashboard_slate_context(break_context(), root=self.root)

        self.assertTrue(context.maintenance_break)
        self.assertIn("injury_unverified:actionable_rows_present", context.source_errors)
        self.assertIn("injury_unverified:decision_payload_not_empty", context.source_errors)

    def test_m02_bet_gate_requires_verified_injury_source(self) -> None:
        payload = {
            "target_date": TARGET,
            "rows": [{
                "target_date": TARGET,
                "player": "Test Player",
                "final_action": "BET",
                "sportsbook": "DraftKings",
            }],
        }

        current, blocked = approved_supported_bets(payload, TARGET, False)
        _current, approved = approved_supported_bets(payload, TARGET, True)

        self.assertEqual(len(current), 1)
        self.assertEqual(blocked, [])
        self.assertEqual(len(approved), 1)

    def test_renderer_uses_final_bet_eligibility_not_candidate_flag(self) -> None:
        renderer = (ROOT / "patch_dashboard_s19_m02.py").read_text(encoding="utf-8")
        self.assertIn("r.eligible_for_bet===true", renderer)
        self.assertNotIn("if(r.eligible)counts.ACTIONABLE++", renderer)
        self.assertIn("Official injury report unverified", renderer)

    def test_m02_prefers_fresh_canonical_props_over_same_date_raw_cache(self) -> None:
        dash = self.root / "data" / "dashboard"
        raw = self.root / "data" / "raw"
        dash.mkdir(parents=True, exist_ok=True)
        raw.mkdir(parents=True, exist_ok=True)

        write_json(self.root, "data/dashboard/wnba_sprint2_phase2.json", {
            "target_date": TARGET,
            "games": [{"game": GAME}],
        })
        write_json(self.root, "data/dashboard/wnba_player_props.json", {
            "generated_at_utc": "2026-09-15T20:12:28+00:00",
            "target_date": TARGET,
            "rows": [{
                "target_date": TARGET,
                "event_id": "fresh-event",
                "commence_time": "2026-09-17T23:30:00Z",
                "game": GAME,
                "away_team": "Test Away",
                "home_team": "Test Home",
                "player": "Fresh Player",
                "team": "Test Away",
                "stat": "PTS",
                "line": 18.5,
                "books": [
                    {"book": "DraftKings", "side": "OVER", "price": -110},
                    {"book": "FanDuel", "side": "UNDER", "price": -105},
                ],
            }],
        })
        stale = {column: None for column in prop_source.odds_props.RAW_COLUMNS}
        stale.update({
            "game_date": TARGET,
            "event_id": "stale-event",
            "player": "Stale Player",
            "opp_team": GAME,
            "stat_raw": "player_points",
            "stat": "pts",
            "line": 16.5,
            "over_price": -110,
            "under_price": -110,
            "num_books": 1,
            "sportsbooks": "draftkings",
            "odds_type": "sportsbook",
            "game_time": "2026-09-17T23:30:00Z",
            "home_team": "Test Home",
            "away_team": "Test Away",
            "source": "older-m02-cache",
            "scraped_at": "2026-09-15T01:10:00+00:00",
        })
        pd.DataFrame([stale], columns=prop_source.odds_props.RAW_COLUMNS).to_csv(
            raw / f"props_raw_{TARGET}.csv", index=False
        )

        with mock.patch.multiple(
            prop_source,
            ROOT=self.root,
            RAW=raw,
            DASH=dash,
            GAMES=dash / "wnba_sprint2_phase2.json",
            CANONICAL_PROPS=dash / "wnba_player_props.json",
            AUDIT=dash / "wnba_s19_m02_prop_source_audit.json",
        ), mock.patch.object(
            prop_source,
            "fetch_live",
            side_effect=AssertionError("canonical source should prevent a paid fallback"),
        ):
            audit = prop_source.build(TARGET)

        saved = pd.read_csv(raw / f"props_raw_{TARGET}.csv")
        self.assertEqual(audit["source"], "data/dashboard/wnba_player_props.json")
        self.assertFalse(audit["api_called"])
        self.assertEqual(audit["rows"], 1)
        self.assertEqual(saved.iloc[0]["player"], "Fresh Player")
        self.assertEqual(float(saved.iloc[0]["line"]), 18.5)


if __name__ == "__main__":
    unittest.main()
