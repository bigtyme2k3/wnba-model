#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scrape_scores import parse_box_score, parse_scoreboard


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


if __name__ == "__main__":
    unittest.main()
