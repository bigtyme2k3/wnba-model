#!/usr/bin/env python3
"""Read-only WNBA V5 Finals research derived from immutable graded game evidence."""
import json
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("data/dashboard/wnba_game_performance.json")
OUTPUT = Path("data/dashboard/wnba_finals_research.json")
TEAMS = ("Atlanta Dream", "Golden State Valkyries")
CUTOFF = "2026-09-27"

def report(rows):
    out = {}
    for team in TEAMS:
        games = []
        for row in rows:
            if row.get("status") != "GRADED" or str(row.get("target_date", "")) < CUTOFF:
                continue
            if team not in (row.get("home_team"), row.get("away_team")):
                continue
            away, home = row.get("actual_away_score"), row.get("actual_home_score")
            if not isinstance(away, (int, float)) or not isinstance(home, (int, float)):
                continue
            is_home = row["home_team"] == team
            pf, pa = (home, away) if is_home else (away, home)
            games.append({"date": row["target_date"], "opponent": row["away_team"] if is_home else row["home_team"],
                          "points_for": pf, "points_against": pa, "won": pf > pa,
                          "winner_prediction_correct": row.get("winner_result") == "WIN",
                          "margin_error": row.get("margin_error"), "total_error": row.get("total_error")})
        games.sort(key=lambda g: (g["date"], g["opponent"]))
        def summarize(part):
            n = len(part)
            def avg(key):
                values = [float(g[key]) for g in part if isinstance(g.get(key), (int, float))]
                return round(sum(values) / len(values), 3) if values else None
            return {"games": n, "wins": sum(g["won"] for g in part),
                    "win_rate": round(sum(g["won"] for g in part) / n, 4) if n else None,
                    "avg_points_for": avg("points_for"), "avg_points_against": avg("points_against"),
                    "avg_point_differential": round(sum(g["points_for"]-g["points_against"] for g in part)/n, 3) if n else None,
                    "winner_prediction_accuracy": round(sum(g["winner_prediction_correct"] for g in part)/n, 4) if n else None,
                    "avg_margin_error": avg("margin_error"), "avg_total_error": avg("total_error")}
        out[team] = {"playoffs": summarize(games), "last_three": summarize(games[-3:]), "games": games}
    return out

def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = source.get("recent_games") or []
    data = {"schema_version": 1, "status": "RESEARCH_ONLY", "finals_teams": list(TEAMS),
            "postseason_start": CUTOFF, "source": str(SOURCE),
            "source_generated_at_utc": source.get("generated_at_utc"),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "production_mutation": False, "no_actionable_bets": True,
            "teams": report(rows)}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for team, detail in data["teams"].items():
        print(team, detail["playoffs"])
    print("Wrote", OUTPUT)

if __name__ == "__main__":
    main()
