"""Portfolio optimizer v2: builds a small diversified card from qualified final decisions."""
from __future__ import annotations
import argparse, json, math, os
from datetime import date, datetime, timezone


def load(path, default):
    try:
        if os.path.exists(path): return json.load(open(path, encoding="utf-8"))
    except Exception: pass
    return default


def sf(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def kelly(probability, odds):
    probability = max(0.0, min(1.0, probability))
    odds = sf(odds, -110)
    b = 100 / abs(odds) if odds < 0 else odds / 100
    if b <= 0: return 0.0
    full = (b * probability - (1 - probability)) / b
    return max(0.0, min(0.025, full * 0.25))


def build(target, bankroll=500.0):
    final = load("data/warehouse/wnba_decision_engine_final.json", {})
    qualified = final.get("qualified_bets", []) or [row for row in final.get("top_decisions", []) if row.get("final_action") == "BET" and row.get("eligible_for_bet")]
    candidates = []
    for row in qualified:
        probability = sf(row.get("simulation_probability"), 0.5)
        odds = sf(row.get("american_odds"), -110)
        fraction = kelly(probability, odds)
        stake = round(bankroll * fraction, 2)
        if stake < 5: continue
        candidates.append({
            **row,
            "portfolio_score": round(sf(row.get("final_score")), 1),
            "recommended_stake": stake,
            "kelly_fraction": round(fraction, 4),
            "risk_band": "LOW" if probability >= 0.62 and sf(row.get("ev_pct")) <= 12 else "MED",
        })

    candidates.sort(key=lambda row: (row.get("portfolio_score", 0), row.get("ev_pct", 0)), reverse=True)
    card, players, player_stats = [], set(), set()
    game_count = {}
    max_exposure = bankroll * 0.08
    for row in candidates:
        player = str(row.get("player") or "").strip().lower()
        game = str(row.get("game") or "UNKNOWN")
        player_stat = (player, str(row.get("stat") or ""))
        if not player or player in players: continue
        if player_stat in player_stats: continue
        if game_count.get(game, 0) >= 2: continue
        if sum(sf(item.get("recommended_stake")) for item in card) + sf(row.get("recommended_stake")) > max_exposure: continue
        card.append(row); players.add(player); player_stats.add(player_stat); game_count[game] = game_count.get(game, 0) + 1
        if len(card) >= 5: break

    total_stake = round(sum(sf(row.get("recommended_stake")) for row in card), 2)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "bankroll": bankroll,
        "rules": {"max_card_size": 5, "max_bets_per_game": 2, "max_bets_per_player": 1, "max_daily_exposure_pct": 8, "kelly_multiplier": 0.25, "max_single_bet_pct": 2.5},
        "summary": {"qualified_candidates": len(candidates), "card_size": len(card), "total_stake": total_stake, "exposure_pct": round(total_stake / bankroll * 100, 2) if bankroll else 0},
        "recommended_card": card,
        "candidates": candidates,
    }
    os.makedirs("data/warehouse", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_portfolio_optimizer_v2.json", "data/dashboard/wnba_portfolio_optimizer_v2.json"]:
        json.dump(report, open(path, "w", encoding="utf-8"), indent=2, allow_nan=False)
    return report


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); parser.add_argument("--bankroll", type=float, default=500.0); args = parser.parse_args()
    print("Portfolio v2 built:", build(args.date, args.bankroll)["summary"])


if __name__ == "__main__": main()
