"""
deepseek_portfolio_optimizer.py
-------------------------------
Safe integration of DeepSeek's portfolio optimization concept.

This module does NOT replace the existing slip_optimizer.py. It reads the
current predictions file and produces a separate dashboard JSON so the logic can
be reviewed and compared without disrupting the working production pipeline.

Outputs:
  - data/dashboard/deepseek_portfolio_optimizer.json
  - data/intelligence/deepseek_portfolio_optimizer_YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from itertools import combinations
from typing import Any, Dict, List

PRED_DIR = "predictions"
OUT_DASH = "data/dashboard"
OUT_INTEL = "data/intelligence"


def f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return default
        return float(v)
    except Exception:
        return default


def american_to_decimal(odds: Any) -> float:
    o = f(odds, -110)
    if o >= 100:
        return 1 + (o / 100.0)
    if o < 0:
        return 1 + (100.0 / abs(o))
    return 1.91


def implied_prob(odds: Any) -> float:
    dec = american_to_decimal(odds)
    return 1.0 / dec if dec else 0.52


def normalize_stat(v: Any) -> str:
    raw = str(v or "").upper().replace(" ", "")
    return {
        "POINTS": "PTS", "REBOUNDS": "REB", "ASSISTS": "AST",
        "THREES": "3PM", "3PTM": "3PM", "FG3M": "3PM",
        "PTS+REB+AST": "PRA", "PTS+REB": "PR", "PTS+AST": "PA", "REB+AST": "RA",
    }.get(raw, raw)


def get_action(row: Dict[str, Any]) -> str:
    da = row.get("daily_action_v2") or {}
    mt = row.get("market_timing_intelligence") or {}
    return str(
        da.get("final_action")
        or mt.get("timing_action")
        or row.get("final_action")
        or row.get("timing_action")
        or row.get("decision")
        or ""
    ).upper()


def get_score(row: Dict[str, Any]) -> float:
    da = row.get("daily_action_v2") or {}
    pi = row.get("projection_intelligence_v2") or {}
    mt = row.get("market_timing_intelligence") or {}
    mu = row.get("minutes_usage_intelligence") or {}
    muq = mu.get("quality", {}) if isinstance(mu, dict) else {}
    vals = [
        f(da.get("final_score"), 0),
        f(row.get("ups_score"), 0),
        f(pi.get("projection_quality"), 0),
        f(mt.get("timing_confidence"), 0),
        f(muq.get("minutes_usage_score"), 0),
        f(row.get("context_score"), 0),
    ]
    vals = [x for x in vals if x > 0]
    return round(sum(vals) / max(1, len(vals)), 1)


def get_probability(row: Dict[str, Any]) -> float:
    pi = row.get("projection_intelligence_v2") or {}
    p = f(pi.get("hit_probability"), 0)
    if p > 1:
        return max(0.01, min(0.99, p / 100.0))
    if p > 0:
        return max(0.01, min(0.99, p))
    score = get_score(row)
    return max(0.47, min(0.73, 0.50 + (score - 60.0) / 250.0))


def expected_value(row: Dict[str, Any]) -> float:
    p = get_probability(row)
    dec = american_to_decimal(row.get("odds", row.get("price", row.get("best_odds", -110))))
    return round((p * (dec - 1.0)) - (1.0 - p), 4)


def kelly_fraction(row: Dict[str, Any], cap: float = 0.04) -> float:
    p = get_probability(row)
    b = american_to_decimal(row.get("odds", row.get("price", row.get("best_odds", -110)))) - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - p
    k = ((b * p) - q) / b
    return round(max(0.0, min(cap, k)), 4)


def bet_id(row: Dict[str, Any]) -> str:
    return "|".join([
        str(row.get("player", "")), normalize_stat(row.get("stat")), str(row.get("signal", "")), str(row.get("game", ""))
    ])


def slim(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": bet_id(row),
        "player": row.get("player"),
        "team": row.get("team"),
        "game": row.get("game"),
        "stat": normalize_stat(row.get("stat")),
        "signal": row.get("signal"),
        "line": row.get("line"),
        "odds": row.get("odds", row.get("price", row.get("best_odds"))),
        "sportsbook": row.get("best_book_title") or row.get("best_book") or row.get("sportsbook") or row.get("book"),
        "score": get_score(row),
        "probability": round(get_probability(row), 3),
        "ev": expected_value(row),
        "kelly_fraction": kelly_fraction(row),
        "action": get_action(row),
    }


def correlation_penalty(rows: List[Dict[str, Any]]) -> float:
    penalty = 0.0
    seen_games = {}
    seen_players = {}
    seen_directions = {}
    for r in rows:
        game = str(r.get("game", ""))
        player = str(r.get("player", ""))
        signal = str(r.get("signal", ""))
        if game:
            penalty += 0.06 * seen_games.get(game, 0)
            seen_games[game] = seen_games.get(game, 0) + 1
        if player:
            penalty += 0.10 * seen_players.get(player, 0)
            seen_players[player] = seen_players.get(player, 0) + 1
        if signal:
            penalty += 0.03 * seen_directions.get(signal, 0)
            seen_directions[signal] = seen_directions.get(signal, 0) + 1
    return round(min(0.55, penalty), 3)


def portfolio_score(rows: List[Dict[str, Any]], style: str) -> float:
    ev = sum(expected_value(r) for r in rows)
    avg_score = sum(get_score(r) for r in rows) / max(1, len(rows))
    kelly = sum(kelly_fraction(r) for r in rows)
    corr = correlation_penalty(rows)
    style_mult = {"conservative": 0.70, "balanced": 1.00, "aggressive": 1.25, "max_ev": 1.35}.get(style, 1.0)
    raw = (ev * 100 * style_mult) + (avg_score * 0.45) + (kelly * 250) - (corr * 55)
    return round(raw, 2)


def make_portfolio(name: str, rows: List[Dict[str, Any]], style: str) -> Dict[str, Any]:
    total_kelly = sum(kelly_fraction(r) for r in rows)
    total_ev = sum(expected_value(r) for r in rows)
    return {
        "name": name,
        "style": style,
        "legs": len(rows),
        "portfolio_score": portfolio_score(rows, style),
        "expected_value_sum": round(total_ev, 4),
        "correlation_penalty": correlation_penalty(rows),
        "recommended_bankroll_fraction": round(min(0.08, total_kelly), 4),
        "bets": [slim(r) for r in rows],
    }


def build_portfolios(props: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates = [p for p in props if get_action(p) in {"BET NOW", "BET SOON", "LEAN", "BET", "PLAY"}]
    if not candidates:
        candidates = sorted(props, key=get_score, reverse=True)[:10]
    candidates = sorted(candidates, key=lambda r: (expected_value(r), get_score(r)), reverse=True)[:12]
    portfolios: List[Dict[str, Any]] = []
    if candidates:
        portfolios.append(make_portfolio("Best Single", [candidates[0]], "conservative"))
        portfolios.append(make_portfolio("Top 3 Singles", candidates[:3], "balanced"))
    if len(candidates) >= 2:
        best_pair = max(combinations(candidates[:8], 2), key=lambda combo: portfolio_score(list(combo), "balanced"))
        portfolios.append(make_portfolio("Best 2-Leg Portfolio", list(best_pair), "balanced"))
    if len(candidates) >= 3:
        best_three = max(combinations(candidates[:8], 3), key=lambda combo: portfolio_score(list(combo), "aggressive"))
        portfolios.append(make_portfolio("Best 3-Leg Portfolio", list(best_three), "aggressive"))
    if len(candidates) >= 4:
        low_corr = sorted(candidates[:10], key=lambda r: (str(r.get("game", "")), -get_score(r)))
        selected: List[Dict[str, Any]] = []
        games = set()
        for r in sorted(candidates[:10], key=get_score, reverse=True):
            g = str(r.get("game", ""))
            if g not in games or len(selected) < 2:
                selected.append(r)
                games.add(g)
            if len(selected) >= 4:
                break
        portfolios.append(make_portfolio("Low Correlation Card", selected, "conservative"))
    portfolios.sort(key=lambda p: p["portfolio_score"], reverse=True)
    return portfolios


def build_report(data: Dict[str, Any], target_date: str) -> Dict[str, Any]:
    props = data.get("props", []) or []
    portfolios = build_portfolios(props)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target_date,
        "source": "DeepSeek concept integrated safely by ChatGPT",
        "status": "ok" if portfolios else "no_candidates",
        "summary": {
            "props_reviewed": len(props),
            "candidate_bets": len([p for p in props if get_action(p) in {"BET NOW", "BET SOON", "LEAN", "BET", "PLAY"}]),
            "portfolios_created": len(portfolios),
            "top_portfolio": portfolios[0]["name"] if portfolios else None,
            "top_score": portfolios[0]["portfolio_score"] if portfolios else None,
        },
        "portfolios": portfolios,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    pred_path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(pred_path):
        raise SystemExit(f"Missing predictions file: {pred_path}")
    with open(pred_path) as fobj:
        data = json.load(fobj)
    report = build_report(data, args.date)
    os.makedirs(OUT_DASH, exist_ok=True)
    os.makedirs(OUT_INTEL, exist_ok=True)
    with open(os.path.join(OUT_DASH, "deepseek_portfolio_optimizer.json"), "w") as fobj:
        json.dump(report, fobj, indent=2)
    with open(os.path.join(OUT_INTEL, f"deepseek_portfolio_optimizer_{args.date}.json"), "w") as fobj:
        json.dump(report, fobj, indent=2)
    print(f"✅ DeepSeek Portfolio Optimizer built: {report['summary']['portfolios_created']} portfolios")


if __name__ == "__main__":
    main()
