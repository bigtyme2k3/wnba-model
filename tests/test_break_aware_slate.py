#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zoneinfo import ZoneInfo

import active_slate_date as slate
import patch_dashboard_break_state as dashboard_break
import wnba_alt_game_log_recovery as alt_recovery


def write_schedule(path: Path, dates: list[str]) -> None:
    payload = {
        "generated_at_utc": "2026-08-31T18:14:46+00:00",
        "data": {
            "events": {
                "leagues": [
                    {"calendar": [f"{value}T07:00Z" for value in dates]}
                ],
                "events": [],
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class BreakAwareSlateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.schedule = self.root / "scores.json"
        self.now = datetime(2026, 9, 12, 12, 52, tzinfo=ZoneInfo("America/New_York"))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_confirmed_break_separates_today_from_next_slate(self) -> None:
        write_schedule(self.schedule, ["2026-08-30", "2026-09-17", "2026-09-18"])
        context = slate.resolve_slate_context(schedule_source=self.schedule, now=self.now)

        self.assertEqual(context.current_date, "2026-09-12")
        self.assertEqual(context.target_date, "2026-09-12")
        self.assertIsNone(context.active_slate_date)
        self.assertEqual(context.next_slate_date, "2026-09-17")
        self.assertEqual(context.display_slate_date, "2026-09-17")
        self.assertEqual(context.days_until_slate, 5)
        self.assertEqual(context.mode, "break")
        self.assertFalse(context.current_market_refresh_allowed)
        self.assertTrue(context.maintenance_deploy_allowed)
        self.assertEqual(context.upcoming_slate_dates, ["2026-09-17", "2026-09-18"])

    def test_game_day_is_active(self) -> None:
        write_schedule(self.schedule, ["2026-09-17", "2026-09-18"])
        now = datetime(2026, 9, 17, 0, 1, tzinfo=ZoneInfo("America/New_York"))
        context = slate.resolve_slate_context(schedule_source=self.schedule, now=now)

        self.assertEqual(context.mode, "active")
        self.assertEqual(context.active_slate_date, "2026-09-17")
        self.assertEqual(context.next_slate_date, "2026-09-17")
        self.assertEqual(context.days_until_slate, 0)
        self.assertTrue(context.current_market_refresh_allowed)
        self.assertFalse(context.maintenance_deploy_allowed)

    def test_utc_midnight_does_not_roll_eastern_observation_date(self) -> None:
        write_schedule(self.schedule, ["2026-09-17"])
        utc_now = datetime(2026, 9, 13, 1, 30, tzinfo=timezone.utc)
        context = slate.resolve_slate_context(schedule_source=self.schedule, now=utc_now)

        self.assertEqual(context.current_date, "2026-09-12")
        self.assertEqual(context.target_date, "2026-09-12")
        self.assertEqual(context.next_slate_date, "2026-09-17")
        self.assertEqual(slate.resolve_target_date(now=utc_now), "2026-09-12")

    def test_missing_schedule_evidence_fails_closed(self) -> None:
        context = slate.resolve_slate_context(schedule_source=self.schedule, now=self.now)

        self.assertEqual(context.mode, "schedule_unavailable")
        self.assertFalse(context.schedule_evidence_available)
        self.assertFalse(context.current_market_refresh_allowed)
        self.assertFalse(context.maintenance_deploy_allowed)
        self.assertIsNone(context.next_slate_date)

    def test_manual_date_preserves_operator_authority(self) -> None:
        context = slate.resolve_slate_context(
            manual_date="2026-09-17",
            schedule_source=self.schedule,
            now=self.now,
        )

        self.assertEqual(context.mode, "manual")
        self.assertEqual(context.target_date, "2026-09-17")
        self.assertEqual(context.active_slate_date, "2026-09-17")
        self.assertTrue(context.current_market_refresh_allowed)

    def test_break_dashboard_patch_is_idempotent_and_fail_closed(self) -> None:
        html = self.root / "index.html"
        html.write_text(
            """<!doctype html><html><head></head><body><div class=\"app\"><div id=\"sub\">Slate 2026-08-31</div><div id=\"pill\"></div><div id=\"tabs\"></div><div id=\"root\">OLD ACTIONABLE DATA</div></div><script>window.render=function(){};</script></body></html>""",
            encoding="utf-8",
        )
        context = {
            "mode": "break",
            "current_date": "2026-09-12",
            "next_slate_date": "2026-09-17",
            "days_until_slate": 5,
            "schedule_source": "data/wnba/scores.json",
        }

        first = dashboard_break.install_break_state(html, context)
        second = dashboard_break.install_break_state(html, context)
        rendered = html.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertEqual(rendered.count('id="wnba-break-state-style"'), 1)
        self.assertEqual(rendered.count('id="wnba-break-state-script"'), 1)
        self.assertIn("const CURRENT_VIEWS=new Set(['games','matchups','props','alt-props'", rendered)
        self.assertIn("Results, Game Performance, Remaining Season, and Data Health", rendered)
        self.assertIn('"paid_api_called":false', rendered)
        self.assertIn('"stale_predictions_actionable":false', rendered)

    def test_deploy_workflow_has_distinct_break_path(self) -> None:
        workflow = (ROOT / ".github/workflows/deploy_wnba_dashboard.yml").read_text(encoding="utf-8")
        self.assertIn("SLATE_MODE=$(python active_slate_date.py --field mode)", workflow)
        self.assertIn("NEXT_SLATE_DATE=$(python active_slate_date.py --field next_slate_date)", workflow)
        self.assertIn("BREAK_MODE_DEPLOY_SAFE", workflow)
        self.assertIn("patch_dashboard_break_state.py", workflow)
        self.assertIn("if: env.MAINTENANCE_BREAK != 'true'", workflow)

    def test_automatic_alt_recovery_pauses_external_feeds_during_break(self) -> None:
        diagnostics = {
            "inspector": [
                {
                    "category": "missing_verified_game_log",
                    "date": "2026-08-29",
                    "player": "Example Player",
                    "game": "Example Game",
                }
            ]
        }

        def fake_load(path: Path) -> dict:
            if path == alt_recovery.DIAGNOSTICS:
                return diagnostics
            if path == alt_recovery.PLAYER_LOGS:
                return {"records": []}
            return {}

        context = SimpleNamespace(target_date="2026-09-12", mode="break")
        with mock.patch.object(alt_recovery, "load", side_effect=fake_load), mock.patch.object(
            alt_recovery, "resolve_slate_context", return_value=context
        ):
            payload = alt_recovery.build_payload()

        self.assertEqual(payload["status"], "paused_schedule_break")
        self.assertEqual(payload["targets"]["dates"], [])
        self.assertEqual(payload["recovery_commands"], [])
        self.assertFalse(payload["automatic_recovery"]["external_feed_calls_allowed"])


if __name__ == "__main__":
    unittest.main()
