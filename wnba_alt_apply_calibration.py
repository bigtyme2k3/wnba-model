"""Apply price-aware historical calibration to current ALT candidates.

The raw component score/grade remains visible for diagnostics.  Only the action
layer (BET/WATCH/PASS) is calibrated from verified pregame history.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import wnba_alt_calibration as calibration

PATHS = [Path("data/warehouse/wnba_alt_streaks.json"), Path("data/dashboard/wnba_alt_streaks.json")]


def main(target: str) -> None:
    report = calibration.build(target)
    counts = {"BET": 0, "WATCH": 0, "PASS": 0}
    updated = 0
    for path in PATHS:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if str(payload.get("target_date") or "") != target:
            raise SystemExit(f"ALT calibration source target mismatch: {payload.get('target_date')} != {target}")
        rows = [r for r in payload.get("rows", []) if isinstance(r, dict)]
        local_counts = {"BET": 0, "WATCH": 0, "PASS": 0}
        for row in rows:
            raw_action = str(row.get("streak_action") or "PASS")
            result = calibration.decision(row, report)
            action = result["action"]
            row["raw_score_action"] = raw_action
            row["streak_action"] = action
            row["calibrated_action"] = action
            row["calibration_reason"] = result["reason"]
            row["calibration_segment"] = result["segment"]
            row["calibration_keys"] = result["keys"]
            row["calibration_schema_version"] = report.get("schema_version")
            row["calibration_training_rows"] = report.get("graded_training_rows")
            local_counts[action] += 1
            updated += 1
        summary = payload.setdefault("summary", {})
        summary.update({
            "bet_rows": local_counts["BET"],
            "watch_rows": local_counts["WATCH"],
            "pass_rows": local_counts["PASS"],
            "calibration_status": report.get("status"),
            "calibration_training_rows": report.get("graded_training_rows"),
            "calibration_qualified_segments": len(report.get("qualified_segments") or []),
        })
        payload["calibration"] = {
            "schema_version": report.get("schema_version"),
            "status": report.get("status"),
            "training_rows": report.get("graded_training_rows"),
            "qualified_segments": len(report.get("qualified_segments") or []),
            "policy": report.get("policy"),
            "applied_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
        counts = local_counts
    print({
        "status": report.get("status"), "target": target, "updated": updated,
        "training_rows": report.get("graded_training_rows"),
        "qualified_segments": len(report.get("qualified_segments") or []),
        "actions": counts,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    main(args.date)
