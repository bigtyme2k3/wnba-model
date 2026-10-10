"""Offline deterministic contract tests for Finals research."""
import unittest
from scripts.wnba_finals_research import report

class FinalsResearchTests(unittest.TestCase):
    def test_grading_and_cutoff_and_home_away(self):
        rows = [
            {"prediction_id":"a","target_date":"2026-10-09","status":"GRADED",
             "home_team":"Atlanta Dream","away_team":"Golden State Valkyries",
             "actual_home_score":85,"actual_away_score":80,"winner_result":"WIN",
             "margin_error":2.0,"total_error":3.0},
            {"prediction_id":"b","target_date":"2026-09-20","status":"GRADED",
             "home_team":"Atlanta Dream","away_team":"Golden State Valkyries",
             "actual_home_score":100,"actual_away_score":50},
            {"prediction_id":"c","target_date":"2026-10-10","status":"PENDING",
             "home_team":"Atlanta Dream","away_team":"Golden State Valkyries"}]
        data = report(rows)
        atl = data["Atlanta Dream"]["playoffs"]
        gs = data["Golden State Valkyries"]["playoffs"]
        self.assertEqual(atl["games"], 1)
        self.assertEqual(atl["wins"], 1)
        self.assertEqual(atl["avg_points_for"], 85)
        self.assertEqual(gs["wins"], 0)
        self.assertEqual(gs["avg_points_for"], 80)
        self.assertEqual(atl["winner_prediction_accuracy"], 1.0)

if __name__ == "__main__":
    unittest.main()
