#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from scrape_scores import (
    parse_box_score,
    parse_official_schedule,
    parse_scoreboard,
    parse_sportsdataverse_schedule,
)
from scripts.wnba_game_archive_backfill import find_actual


class ScoreSlateDateTests(unittest.TestCase):
    def test_scoreboard_keeps_requested_slate_date_across_utc_midnight(self) -> None:
        payload = {
            "events": [{
                "id": "game-1",
                "date": "2026-09-18T02:00:00Z",
                "status": {"type": {"name": "STATUS_FINAL"}},
                "competitions": [{
                    "competitors": [
                        {"homeAway": "away", "score": "81", "team": {"displayName": "Away"}},
                        {"homeAway": "home", "score": "88", "team": {"displayName": "Home"}},
                    ]
                }],
            }]
        }

        frame = parse_scoreboard(payload, "2026-09-17")

        self.assertEqual(frame.iloc[0]["game_date"], "2026-09-17")
        self.assertEqual(frame.iloc[0]["event_start_utc"], "2026-09-18T02:00:00Z")

    def test_boxscore_keeps_requested_slate_date_across_utc_midnight(self) -> None:
        summary = {
            "header": {"competitions": [{"date": "2026-09-18T02:00:00Z"}]},
            "boxscore": {"players": [{
                "team": {"displayName": "Away"},
                "statistics": [{
                    "labels": ["MIN", "PTS", "REB", "AST"],
                    "athletes": [{
                        "athlete": {"displayName": "Test Player", "position": {"abbreviation": "G"}},
                        "stats": ["30", "18", "5", "4"],
                    }],
                }],
            }]},
        }

        frame = parse_box_score(summary, "game-1", "2026-09-17")

        self.assertEqual(frame.iloc[0]["game_date"], "2026-09-17")
        self.assertEqual(frame.iloc[0]["event_start_utc"], "2026-09-18T02:00:00Z")

    def test_official_wnba_schedule_normalizes_final_score(self) -> None:
        payload = {
            "leagueSchedule": {
                "gameDates": [{
                    "gameDate": "09/17/2026 00:00:00",
                    "games": [{
                        "gameId": "1022600305",
                        "gameStatus": 3,
                        "gameStatusText": "Final",
                        "gameDateTimeUTC": "2026-09-18T02:00:00Z",
                        "awayTeam": {"teamCity": "Las Vegas", "teamName": "Aces", "score": "114"},
                        "homeTeam": {"teamCity": "Seattle", "teamName": "Storm", "score": "77"},
                    }],
                }]
            }
        }

        frame = parse_official_schedule(payload, "2026-09-17")

        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["away_team"], "Las Vegas Aces")
        self.assertEqual(frame.iloc[0]["home_team"], "Seattle Storm")
        self.assertEqual(frame.iloc[0]["away_score"], 114)
        self.assertEqual(frame.iloc[0]["home_score"], 77)
        self.assertTrue(frame.iloc[0]["is_final"])
        self.assertEqual(frame.iloc[0]["source"], "wnba_official_schedule_cdn")

    def test_sportsdataverse_release_normalizes_exact_date_final(self) -> None:
        payload = pd.DataFrame([
            {
                "id": 401857194,
                "game_id": 401857194,
                "date": "2026-09-18T02:00Z",
                "game_date": "2026-09-17",
                "status_type_name": "STATUS_FINAL",
                "status_type_state": "post",
                "status_type_completed": True,
                "away_display_name": "Las Vegas Aces",
                "away_score": 114,
                "home_display_name": "Seattle Storm",
                "home_score": 77,
                "venue_full_name": "Climate Pledge Arena",
                "attendance": 14200,
            },
            {
                "id": 401857195,
                "game_id": 401857195,
                "date": "2026-09-19T00:00Z",
                "game_date": "2026-09-18",
                "status_type_name": "STATUS_SCHEDULED",
                "status_type_state": "pre",
                "status_type_completed": False,
                "away_display_name": "Other Away",
                "home_display_name": "Other Home",
            },
        ])

        frame = parse_sportsdataverse_schedule(payload, "2026-09-17")

        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["game_date"], "2026-09-17")
        self.assertEqual(frame.iloc[0]["away_team"], "Las Vegas Aces")
        self.assertEqual(frame.iloc[0]["home_team"], "Seattle Storm")
        self.assertEqual(frame.iloc[0]["away_score"], 114)
        self.assertEqual(frame.iloc[0]["home_score"], 77)
        self.assertEqual(frame.iloc[0]["actual_spread"], -37)
        self.assertEqual(frame.iloc[0]["actual_total"], 191)
        self.assertTrue(frame.iloc[0]["is_final"])
        self.assertEqual(frame.iloc[0]["source"], "sportsdataverse_espn_schedule_release")

    def test_game_backfill_rejects_adjacent_date_match(self) -> None:
        adjacent = {
            "game_date": "2026-09-18",
            "away_team": "Las Vegas Aces",
            "home_team": "Seattle Storm",
            "away_score": "114",
            "home_score": "77",
        }
        exact = {}
        by_matchup = {("las vegas aces", "seattle storm"): [adjacent]}

        actual, mode = find_actual(
            exact,
            by_matchup,
            "2026-09-17",
            "las vegas aces",
            "seattle storm",
        )

        self.assertIsNone(actual)
        self.assertIsNone(mode)


if __name__ == "__main__":
    unittest.main()
