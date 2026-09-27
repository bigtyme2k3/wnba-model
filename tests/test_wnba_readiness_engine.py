import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import wnba_readiness_engine as readiness


class ReadinessTests(unittest.TestCase):
    def test_uses_canonical_target_dated_props_without_legacy_master_props(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dash = root / "dashboard"
            ware = root / "warehouse"
            dash.mkdir()
            ware.mkdir()
            (root / "docs").mkdir()
            (root / "docs" / "index.html").write_text("ok")

            def put(path, payload):
                path.write_text(json.dumps(payload))

            put(dash / "wnba_master.json", {
                "target_date": "2026-09-27", "props": [],
                "today_games": [{"game_date": "2026-09-27", "game": "Away @ Home"}],
            })
            put(dash / "wnba_sportsbook_consensus.json", {"all_consensus": [{"market": "total"}]})
            put(dash / "wnba_daily_edges.json", {"target_date": "2026-09-27"})
            put(ware / "wnba_player_game_logs.json", {"records": [{}] * 100})
            put(dash / "wnba_player_props.json", {
                "target_date": "2026-09-27",
                "rows": [{"target_date": "2026-09-27", "books": [{"book": "DraftKings"}]}],
            })

            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.object(readiness, "DASH", dash), patch.object(readiness, "WARE", ware), \
                     patch.object(readiness, "OUTS", [dash / "wnba_pipeline_readiness.json"]):
                    report = readiness.build()
                    self.assertEqual(report["status"], "READY")
                    self.assertEqual(report["counts"]["props"], 1)

                    put(dash / "wnba_player_props.json", {
                        "target_date": "2026-09-26",
                        "rows": [{"target_date": "2026-09-27", "books": [{"book": "DraftKings"}]}],
                    })
                    report = readiness.build()
                    self.assertEqual(report["status"], "WAIT")
                    self.assertEqual(report["counts"]["props"], 0)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
