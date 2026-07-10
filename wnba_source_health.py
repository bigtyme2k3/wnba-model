"""
wnba_source_health.py
---------------------
Creates one dashboard-readable source health report.
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


def odds_status_from_health(odds: Dict[str, Any], odds_health: Dict[str, Any]) -> str:
    status = str(odds_health.get("status") or odds.get("status") or "missing")
    if status in {"ok", "props_only"}:
        return "ok"
    if status in {"props_unpriced", "empty"}:
        return "degraded"
    return "missing"


def build(target: str) -> Dict[str, Any]:
    sports = load_json("data/warehouse/sports_skills_provider_status.json", {})
    odds = load_json("data/raw/odds_source_status.json", {})
    odds_health = load_json("data/warehouse/wnba_odds_health.json", load_json("data/dashboard/wnba_odds_health.json", {}))
    wh = load_json("data/warehouse/wnba_source_quality.json", {})
    wehoop_status = load_json("data/raw/wehoop_stats_status.json", {})
    wehoop_files = {
        "status": wehoop_status,
        "players": file_status("data/raw/wnba_players_live.json"),
        "boxscores": file_status("data/raw/boxscores_wehoop.csv"),
        "history": file_status("data/raw/wehoop_player_boxscores.csv"),
    }
    wehoop_ok = (
        wehoop_files["players"]["populated"]
        and wehoop_files["boxscores"]["populated"]
        and str(wehoop_status.get("status", "ok")) == "ok"
    )
    modules = {
        "wehoop": {
            "label": "wehoop / ESPN Stats",
            "status": "ok" if wehoop_ok else "degraded",
            "detail": wehoop_files,
        },
        "sports_skills": {
            "label": "sports-skills Supplemental",
            "status": "ok" if sports.get("ready") else "degraded",
            "detail": sports.get("commands", {}),
        },
        "data_warehouse": {
            "label": "Data Warehouse",
            "status": "ok" if wh.get("ready_for_model") else "degraded",
            "detail": wh.get("normalized_counts", {}),
        },
        "player_intelligence": {
            "label": "Player Intelligence",
            "status": "ok" if file_status("data/warehouse/wnba_player_intelligence.json")["populated"] else "missing",
            "detail": file_status("data/warehouse/wnba_player_intelligence.json"),
        },
        "matchup_intelligence": {
            "label": "Matchup Intelligence",
            "status": "ok" if file_status("data/warehouse/wnba_matchup_intelligence.json")["populated"] else "missing",
            "detail": file_status("data/warehouse/wnba_matchup_intelligence.json"),
        },
        "consensus_engine": {
            "label": "Consensus Engine",
            "status": "ok" if file_status("data/warehouse/wnba_consensus_engine.json")["populated"] else "missing",
            "detail": file_status("data/warehouse/wnba_consensus_engine.json"),
        },
        "odds_layer": {
            "label": "Odds Layer",
            "status": odds_status_from_health(odds, odds_health),
            "detail": {"raw_status": odds, "health": odds_health},
        },
        "odds_api": {
            "label": "The Odds API",
            "status": "ok" if odds.get("selected_source") in {"the_odds_api", "current_file"} else "optional",
            "detail": {"selected_source": odds.get("selected_source"), "rows": odds.get("rows", 0)},
        },
    }
    ok = sum(1 for module in modules.values() if module["status"] in {"ok", "optional"})
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "summary": {
            "sources": len(modules),
            "ok_or_optional": ok,
            "degraded_or_missing": len(modules) - ok,
        },
        "sources": modules,
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_source_health.json", "data/dashboard/wnba_source_health.json"]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    report = build(args.date)
    print(f"Source health built: {report['summary']}")


if __name__ == "__main__":
    main()
