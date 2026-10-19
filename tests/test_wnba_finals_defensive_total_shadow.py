import unittest
from scripts.wnba_finals_defensive_total_shadow import build

class ShadowTotalTests(unittest.TestCase):
    def test_prior_only_and_capped_adjustment(self):
        pred={"target_date":"2026-10-19","games":[{"game":"A @ B","away_team":"A","home_team":"B","projection":{"total":156.9},"market":{"total":152.5}}]}
        hist={"recent_games":[{"prediction_id":"old","target_date":"2026-10-17","status":"GRADED","away_team":"A","home_team":"B","projected_total":158.7,"actual_total":132},{"prediction_id":"future","target_date":"2026-10-19","status":"GRADED","away_team":"A","home_team":"B","projected_total":100,"actual_total":300}]}
        out=build(pred,hist)
        self.assertEqual(out["games"][0]["shadow_total"],150.9)
        self.assertEqual(out["games"][0]["prior_prediction_ids"],["old"])
        self.assertEqual(out["games"][0]["recommendation"],"PASS")
    def test_no_history_no_change(self):
        pred={"target_date":"2026-10-19","games":[{"game":"A @ B","away_team":"A","home_team":"B","projection":{"total":156.9},"market":{}}]}
        self.assertEqual(build(pred,{"recent_games":[]})["games"][0]["shadow_total"],156.9)

if __name__ == "__main__":
    unittest.main()
