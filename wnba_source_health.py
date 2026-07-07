"""
wnba_source_health.py
---------------------
Creates one dashboard-readable source health report.

Outputs:
- data/warehouse/wnba_source_health.json
- data/dashboard/wnba_source_health.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from typing import Any, Dict


def load_json(path: str, default: Any):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def file_status(path: str) -> Dict[str, Any]:
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    return {"path": path, "exists": exists, "bytes": size, "populated": exists and size > 5}


def build(target: str) -> Dict[str, Any]:
    sports = load_json("data/warehouse/sports_skills_provider_status.json", {})
    odds = load_json("data/raw/odds_source_status.json", {})
    wh = load_json("data/warehouse/wnba_source_quality.json", {})
    modules = {
        "sports_skills": {"label": "sports-skills", "status": "ok" if sports.get("ready") else "degraded", "detail": sports.get("commands", {})},
        "stats_wnba": {"label": "stats.wnba.com", "status": "ok" if file_status("data/raw/wnba_players_live.json")["populated"] else "missing", "detail": file_status("data/raw/wnba_players_live.json")},
        "data_warehouse": {"label": "Data Warehouse", "status": "ok" if wh.get("ready_for_model") else "degraded", "detail": wh.get("normalized_counts", {})},
        "player_intelligence": {"label": "Player Intelligence", "status": "ok" if file_status("data/warehouse/wnba_player_intelligence.json")["populated"] else "missing", "detail": file_status("data/warehouse/wnba_player_intelligence.json")},
        "matchup_intelligence": {"label": "Matchup Intelligence", "status": "ok" if file_status("data/warehouse/wnba_matchup_intelligence.json")["populated"] else "missing", "detail": file_status("data/warehouse/wnba_matchup_intelligence.json")},
        "consensus_engine": {"label": "Consensus Engine", "status": "ok" if file_status("data/warehouse/wnba_consensus_engine.json")["populated"] else "missing", "detail": file_status("data/warehouse/wnba_consensus_engine.json")},
        "odds_layer": {"label": "Odds Layer", "status": odds.get("status", "missing"), "detail": odds},
        "odds_api": {"label": "The Odds API", "status": "optional", "detail": "Disabled by default to conserve credits."},
    }
    ok = sum(1 for m in modules.values() if m["status"] in {"ok", "optional"})
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target, "summary": {"sources": len(modules), "ok_or_optional": ok, "degraded_or_missing": len(modules) - ok}, "sources": modules}
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_source_health.json", "data/dashboard/wnba_source_health.json"]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    report = build(args.date)
    print(f"✅ Source health built: {report['summary']}")


if __name__ == "__main__":
    main()
