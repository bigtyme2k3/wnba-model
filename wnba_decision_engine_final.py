"""Final autonomous decision engine with normalized 0-100 scoring and strict betting guardrails."""
from __future__ import annotations
import argparse, json, math, os
from datetime import date, datetime, timezone

SUPPORTED_STATS = {"PTS", "REB", "AST", "PRA", "PR", "PA", "RA", "3PM", "STL", "BLK", "TOV"}


def load(path, default):
    try:
        if os.path.exists(path):
            return json.load(open(path, encoding="utf-8"))
    except Exception:
        pass
    return default


def sf(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


def key(row):
    return (str(row.get("player") or "").strip().lower(), str(row.get("game") or "").strip().lower(), str(row.get("stat") or "").strip().upper())


def prop_map():
    master = load("data/dashboard/wnba_master.json", {}) or load("data/master/wnba_master.json", {})
    result = {}
    for row in master.get("props", []) or []:
        result[key(row)] = row
    return result


def agreement_count(value):
    try:
        left, right = str(value).split("/", 1)
        return int(left), int(right)
    except Exception:
        return 0, 0


def american_to_implied(odds):
    odds = sf(odds, 0)
    if odds == 0:
        return 0.0
    return abs(odds) / (abs(odds) + 100) if odds < 0 else 100 / (odds + 100)


def chosen_price(row, prop):
    side = str(row.get("signal") or "").upper()
    if side == "OVER":
        return sf(prop.get("best_over_price", prop.get("over_price", row.get("over_price"))), 0), prop.get("best_over_book") or prop.get("book")
    return sf(prop.get("best_under_price", prop.get("under_price", row.get("under_price"))), 0), prop.get("best_under_book") or prop.get("book")


def build(target):
    consensus = load("data/warehouse/wnba_consensus_engine.json", {}).get("all_consensus", [])
    simulations = load("data/warehouse/wnba_monte_carlo_engine.json", {}).get("all_simulations", [])
    market = load("data/warehouse/wnba_market_engine.json", {}).get("movements", [])
    props = prop_map()
    sim_map = {key(row): row for row in simulations}
    market_map = {key(row): row for row in market}
    decisions = []

    for row in consensus:
        stat = str(row.get("stat") or "").upper().replace("THREES", "3PM")
        signal = str(row.get("signal") or "").upper()
        prop = props.get(key(row), {})
        sim = sim_map.get(key(row), {})
        movement = market_map.get(key(row), {})
        line = sf(row.get("line"), -1)
        prediction = sf(row.get("pred"), line)
        edge = abs(sf(row.get("edge"), prediction - line))
        probability = clamp(sf(sim.get("signal_probability"), 0.5), 0.0, 1.0)
        raw_ev = sf(row.get("ev_pct"), 0)
        price, book = chosen_price(row, prop)
        implied = american_to_implied(price)
        calculated_ev = ((probability / implied) - 1) * 100 if implied > 0 else 0
        ev_pct = clamp(calculated_ev, -25, 25)
        consensus_score = clamp(sf(row.get("consensus_score")), 0, 100)
        agreement, engines = agreement_count(row.get("engine_agreement"))
        history_games = int(sf(prop.get("history_games_available"), len(prop.get("last10", []) or [])))
        book_count = int(sf(prop.get("book_count"), 1 if book else 0))
        edge_pct = (edge / line * 100) if line > 0 else 0
        edge_score = clamp(edge_pct * 5, 0, 100)
        probability_score = clamp((probability - 0.5) * 400, 0, 100)
        ev_score = clamp(max(ev_pct, 0) * 5, 0, 100)
        agreement_score = clamp((agreement / engines * 100) if engines else 0, 0, 100)
        final_score = round(clamp(consensus_score * 0.35 + probability_score * 0.25 + edge_score * 0.15 + ev_score * 0.15 + agreement_score * 0.10, 0, 100), 1)

        reasons = []
        supported = stat in SUPPORTED_STATS
        valid_market = line > 0 and signal in {"OVER", "UNDER"} and price != 0 and -1000 <= price <= 1000
        valid_ev = 2.0 <= ev_pct <= 20.0 and raw_ev < 100
        enough_history = history_games >= 5
        enough_books = book_count >= 2
        enough_probability = probability >= 0.56
        enough_edge = edge_pct >= 5.0
        enough_agreement = agreement >= 4
        if not supported: reasons.append("unsupported market")
        if not valid_market: reasons.append("invalid or missing sportsbook price")
        if raw_ev >= 100: reasons.append("raw EV rejected as malformed")
        if not valid_ev: reasons.append("EV outside 2-20% guardrail")
        if not enough_history: reasons.append(f"only {history_games} history games")
        if not enough_books: reasons.append(f"only {book_count} sportsbook")
        if not enough_probability: reasons.append("simulation probability below 56%")
        if not enough_edge: reasons.append("projection edge below 5%")
        if not enough_agreement: reasons.append("fewer than four engines agree")

        eligible = all([supported, valid_market, valid_ev, enough_history, enough_books, enough_probability, enough_edge, enough_agreement])
        if eligible and final_score >= 78:
            action = "BET"
        elif supported and valid_market and enough_history and final_score >= 68:
            action = "LEAN"
        elif supported and valid_market and final_score >= 55:
            action = "WATCH"
        else:
            action = "PASS"

        decisions.append({
            **row,
            "stat": stat,
            "simulation_probability": round(probability, 4),
            "market_move": sf(movement.get("move"), 0),
            "sportsbook": book,
            "american_odds": int(price) if price else None,
            "implied_probability": round(implied, 4) if implied else None,
            "raw_ev_pct": round(raw_ev, 2),
            "ev_pct": round(ev_pct, 2),
            "edge_pct": round(edge_pct, 2),
            "confidence": final_score,
            "final_score": final_score,
            "final_action": action,
            "eligible_for_bet": eligible,
            "history_games": history_games,
            "book_count": book_count,
            "guardrail_failures": reasons,
            "decision_reason": "Qualified across score, probability, EV, history, books and agreement." if eligible else "; ".join(reasons),
        })

    decisions.sort(key=lambda row: (row.get("final_action") == "BET", row.get("final_score", 0)), reverse=True)
    bets = [row for row in decisions if row.get("final_action") == "BET"]
    leans = [row for row in decisions if row.get("final_action") == "LEAN"]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "scoring_scale": "0-100",
        "summary": {"rows": len(decisions), "bets": len(bets), "leans": len(leans), "watch": sum(1 for row in decisions if row.get("final_action") == "WATCH"), "passes": sum(1 for row in decisions if row.get("final_action") == "PASS")},
        "guardrails": {"supported_stats": sorted(SUPPORTED_STATS), "minimum_probability": 0.56, "minimum_ev_pct": 2, "maximum_ev_pct": 20, "minimum_history_games": 5, "minimum_books": 2, "minimum_edge_pct": 5, "minimum_engine_agreement": 4},
        "top_decisions": decisions[:75],
        "qualified_bets": bets,
    }
    os.makedirs("data/warehouse", exist_ok=True); os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_decision_engine_final.json", "data/dashboard/wnba_decision_engine_final.json"]:
        json.dump(report, open(path, "w", encoding="utf-8"), indent=2, allow_nan=False)
    return report


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args()
    print("Final decision engine built:", build(args.date)["summary"])


if __name__ == "__main__": main()
