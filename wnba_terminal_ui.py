"""Builds a single professional-dashboard data bundle from all priority modules."""
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
        "monte_carlo": load_json("data/dashboard/wnba_monte_carlo_engine.json", {}),
        "market_engine": load_json("data/dashboard/wnba_market_engine.json", {}),
        "portfolio_v2": load_json("data/dashboard/wnba_portfolio_optimizer_v2.json", {}),
        "decision_final": load_json("data/dashboard/wnba_decision_engine_final.json", {}),
        "history": load_json("data/dashboard/wnba_historical_summary.json", {}),
        "learning": load_json("data/dashboard/wnba_self_learning.json", {}),
        "grading": load_json("data/dashboard/wnba_results_grading.json", {}),
        "clv": load_json("data/dashboard/wnba_clv_summary.json", {}),
        "portfolio": load_json("data/dashboard/deepseek_portfolio_optimizer.json", {}),
        "market_timing": load_json("data/dashboard/market_timing_intelligence.json", {}),
        "projection_accuracy": load_json("data/dashboard/projection_accuracy.json", {}),
    }
    top=(bundle.get("decision_final",{}) or {}).get("top_decisions", [])[:20] or (bundle.get("consensus",{}) or {}).get("top_consensus", [])[:20]
    sim=(bundle.get("monte_carlo",{}) or {}).get("summary",{})
    port=(bundle.get("portfolio_v2",{}) or {}).get("summary",{})
    dec=(bundle.get("decision_final",{}) or {}).get("summary",{})
    market=(bundle.get("market_engine",{}) or {}).get("summary",{})
    bundle["terminal_summary"]={
        "top_cards": top[:5],
        "final_bets": dec.get("bets",0),
        "final_leans": dec.get("leans",0),
        "bet_count": (bundle.get("consensus",{}) or {}).get("summary",{}).get("bets",0),
        "lean_count": (bundle.get("consensus",{}) or {}).get("summary",{}).get("leans",0),
        "source_ok": (bundle.get("source_health",{}) or {}).get("summary",{}).get("ok_or_optional",0),
        "history_records": (bundle.get("history",{}) or {}).get("total_records",0),
        "graded_this_run": (bundle.get("grading",{}) or {}).get("graded_this_run",0),
        "win_rate": (bundle.get("grading",{}) or {}).get("win_rate",0),
        "clv_updates": (bundle.get("clv",{}) or {}).get("history_clv_updates",0),
        "mc_rows": sim.get("rows",0),
        "mc_prob_60_plus": sim.get("prob_60_plus",0),
        "mc_low_risk": sim.get("low_risk",0),
        "portfolio_card_size": port.get("card_size",0),
        "portfolio_total_stake": port.get("total_stake",0),
        "market_rows": market.get("markets",0),
    }
    os.makedirs("data/dashboard", exist_ok=True)
    with open("data/dashboard/terminal_ui.json","w",encoding="utf-8") as f: json.dump(bundle,f,indent=2)
    return bundle["terminal_summary"]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--date", default=str(date.today())); args=ap.parse_args()
    print(f"Terminal UI bundle built: {build(args.date)}")
if __name__=="__main__": main()
