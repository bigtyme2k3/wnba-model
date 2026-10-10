#!/usr/bin/env python3
"""Research-only Finals baseline; never emits production bets."""
import json
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("data/dashboard/wnba_finals_research.json")
OUTPUT = Path("data/dashboard/wnba_finals_game1_shadow.json")
ATL = "Atlanta Dream"
GS = "Golden State Valkyries"

def build(research):
    teams = research["teams"]
    for team in (ATL, GS):
        if teams[team]["playoffs"]["games"] < 3:
            raise ValueError("Insufficient playoff sample for " + team)
    a, g = (teams[t]["playoffs"] for t in (ATL, GS))
    # Simple offense/defense midpoint; not a calibrated probability model.
    atl = (a["avg_points_for"] + g["avg_points_against"]) / 2
    gs = (g["avg_points_for"] + a["avg_points_against"]) / 2
    return {"status": "SHADOW_RESEARCH_ONLY", "production_mutation": False,
            "finals_teams": [ATL, GS], "game_number": 1,
            "venue_verified": False, "injury_status_verified": False,
            "sportsbook_lines_verified": False, "bet_recommendation": "PASS",
            "method": "playoff_offense_opponent_defense_midpoint_no_home_advantage",
            "projected_points": {ATL: round(atl, 2), GS: round(gs, 2)},
            "projected_total": round(atl + gs, 2),
            "projected_margin_atl_minus_gs": round(atl - gs, 2),
            "model_probability": None,
            "sample_games": {ATL: a["games"], GS: g["games"]},
            "limitations": ["Small playoff samples", "No home court adjustment",
                            "No opponent-strength adjustment", "No verified Game 1 injury or market inputs"]}

def main():
    research = json.loads(SOURCE.read_text(encoding="utf-8"))
    if research.get("status") != "RESEARCH_ONLY":
        raise ValueError("Finals research source is not research-only")
    out = build(research)
    out["source_generated_at_utc"] = research.get("generated_at_utc")
    out["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
