"""
wnba_terminal_ui.py
-------------------
Builds a single professional-dashboard data bundle from all priority modules.

Outputs:
- data/dashboard/terminal_ui.json
"""
from __future__ import annotations

import argparse, json, os
from datetime import date, datetime, timezone
from typing import Any


def load_json(path: str, default: Any):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception:
        pass
    return default


def build(target: str):
    bundle={
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "source_health": load_json("data/dashboard/wnba_source_health.json", {}),
        "consensus": load_json("data/dashboard/wnba_consensus_engine.json", {}),
        "matchups": load_json("data/dashboard/wnba_matchup_intelligence.json", {}),
        "players": load_json("data/dashboard/wnba_player_intelligence.json", {}),
        "history": load_json("data/dashboard/wnba_historical_summary.json", {}),
        "learning": load_json("data/dashboard/wnba_self_learning.json", {}),
        "portfolio": load_json("data/dashboard/deepseek_portfolio_optimizer.json", {}),
        "market_timing": load_json("data/dashboard/market_timing_intelligence.json", {}),
        "projection_accuracy": load_json("data/dashboard/projection_accuracy.json", {}),
    }
    top=(bundle.get("consensus",{}) or {}).get("top_consensus", [])[:20]
    bundle["terminal_summary"]={
        "top_cards": top[:5],
        "bet_count": (bundle.get("consensus",{}) or {}).get("summary",{}).get("bets",0),
        "lean_count": (bundle.get("consensus",{}) or {}).get("summary",{}).get("leans",0),
        "source_ok": (bundle.get("source_health",{}) or {}).get("summary",{}).get("ok_or_optional",0),
        "history_records": (bundle.get("history",{}) or {}).get("total_records",0),
    }
    os.makedirs("data/dashboard", exist_ok=True)
    with open("data/dashboard/terminal_ui.json","w",encoding="utf-8") as f: json.dump(bundle,f,indent=2)
    return bundle["terminal_summary"]


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--date", default=str(date.today())); args=ap.parse_args()
    print(f"✅ Terminal UI bundle built: {build(args.date)}")

if __name__=="__main__": main()
