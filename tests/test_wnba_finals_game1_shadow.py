import unittest
from scripts.wnba_finals_game1_shadow import build

class FinalsGame1ShadowTests(unittest.TestCase):
    def test_midpoint_and_pass_gate(self):
        data={"teams":{
            "Atlanta Dream":{"playoffs":{"games":5,"avg_points_for":92.6,"avg_points_against":83.0}},
            "Golden State Valkyries":{"playoffs":{"games":6,"avg_points_for":87.0,"avg_points_against":79.833}}
        }}
        out=build(data)
        self.assertEqual(out["projected_points"]["Atlanta Dream"],86.22)
        self.assertEqual(out["projected_points"]["Golden State Valkyries"],85.0)
        self.assertEqual(out["bet_recommendation"],"PASS")
        self.assertIsNone(out["model_probability"])
        self.assertFalse(out["sportsbook_lines_verified"])

if __name__=="__main__":
    unittest.main()
