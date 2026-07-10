"""Audits warehouse health, recommendation scoring, guardrails, and portfolio diversification."""
from __future__ import annotations
import argparse, json, math, os
from datetime import date, datetime, timezone

SUPPORTED_STATS = {"PTS", "REB", "AST", "PRA", "PR", "PA", "RA", "3PM", "STL", "BLK", "TOV"}


def load(path, default):
    try:
        if os.path.exists(path): return json.load(open(path, encoding="utf-8"))
    except Exception: pass
    return default


def finite(value):
    try: return math.isfinite(float(value))
    except Exception: return False


def build(target):
    warehouse = load("data/dashboard/wnba_data_warehouse.json", {})
    decisions = load("data/dashboard/wnba_decision_engine_final.json", {})
    portfolio = load("data/dashboard/wnba_portfolio_optimizer_v2.json", {})
    rows = decisions.get("top_decisions", []) or []
    bets = decisions.get("qualified_bets", []) or [r for r in rows if r.get("final_action") == "BET"]
    card = portfolio.get("recommended_card", []) or []
    errors, warnings = [], []

    if not warehouse.get("ready_for_model"):
        errors.append("data warehouse is not ready for model use")
    scores = [r.get("final_score") for r in rows]
    if any(not finite(v) or not 0 <= float(v) <= 100 for v in scores):
        errors.append("one or more final scores are outside the 0-100 scale")
    invalid_bets = [r for r in bets if not r.get("eligible_for_bet")]
    if invalid_bets: errors.append(f"{len(invalid_bets)} BET rows bypassed eligibility guardrails")
    unsupported = [r for r in bets if str(r.get("stat") or "").upper() not in SUPPORTED_STATS]
    if unsupported: errors.append(f"{len(unsupported)} unsupported markets reached final BET status")
    malformed_ev = [r for r in bets if not 2 <= float(r.get("ev_pct") or 0) <= 20]
    if malformed_ev: errors.append(f"{len(malformed_ev)} final bets have EV outside 2-20%")
    if len(card) > 5: errors.append("portfolio exceeds five-bet cap")
    players = [str(r.get("player") or "").strip().lower() for r in card]
    if len(players) != len(set(players)): errors.append("portfolio contains multiple bets for the same player")
    game_counts = {}
    for row in card:
        game = str(row.get("game") or "UNKNOWN"); game_counts[game] = game_counts.get(game, 0) + 1
    if any(count > 2 for count in game_counts.values()): errors.append("portfolio contains more than two bets from one game")
    if len(bets) > 12: warnings.append(f"{len(bets)} qualified bets remain; consider tighter calibration after results accumulate")
    if not bets: warnings.append("no bets passed all guardrails; a pass day is valid")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target,
        "status": "ok" if not errors else "error", "errors": errors, "warnings": warnings,
        "counts": {"decision_rows": len(rows), "qualified_bets": len(bets), "portfolio_card": len(card)},
        "checks": {"warehouse_ready": bool(warehouse.get("ready_for_model")), "scores_0_100": not any(not finite(v) or not 0 <= float(v) <= 100 for v in scores),
                   "all_bets_eligible": not invalid_bets, "supported_markets_only": not unsupported,
                   "ev_guardrails": not malformed_ev, "portfolio_diversified": len(players) == len(set(players)) and all(v <= 2 for v in game_counts.values())},
    }
    os.makedirs("data/dashboard", exist_ok=True); os.makedirs("data/warehouse", exist_ok=True)
    for path in ["data/dashboard/wnba_model_quality_audit.json", "data/warehouse/wnba_model_quality_audit.json"]:
        json.dump(report, open(path, "w", encoding="utf-8"), indent=2, allow_nan=False)
    print(json.dumps(report, indent=2))
    if errors: raise SystemExit(1)
    return report


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args(); build(args.date)


if __name__ == "__main__": main()
