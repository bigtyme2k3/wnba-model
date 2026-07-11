"""Build an immutable, paper-trading Monte Carlo live-test card for one WNBA slate."""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

MC_PATH = Path("data/warehouse/wnba_monte_carlo_engine.json")
CONSENSUS_PATH = Path("data/warehouse/wnba_sportsbook_consensus.json")
OUT_PATH = Path("data/dashboard/wnba_monte_carlo_live_test.json")
ARCHIVE_DIR = Path("data/history/live_tests")

ALLOWED_BOOKS = {"DraftKings", "FanDuel", "Fanatics"}


def load(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.load(path.open(encoding="utf-8"))
    except Exception:
        pass
    return default


def sf(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("’", "'").split())


def american_implied(odds: float) -> float:
    return abs(odds) / (abs(odds) + 100.0) if odds < 0 else 100.0 / (odds + 100.0)


def fair_american(probability: float) -> int | None:
    probability = max(0.0001, min(0.9999, probability))
    if probability >= 0.5:
        return round(-100 * probability / (1 - probability))
    return round(100 * (1 - probability) / probability)


def expected_value(probability: float, odds: float) -> float:
    profit = 100.0 / abs(odds) if odds < 0 else odds / 100.0
    return probability * profit - (1 - probability)


def consensus_lookup() -> dict[tuple[str, str, str], dict[str, Any]]:
    payload = load(CONSENSUS_PATH, {})
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in payload.get("markets", []) or []:
        key = (norm(row.get("player")), str(row.get("stat") or "").upper(), norm(row.get("game")))
        result[key] = row
    return result


def choose_market(mc: dict[str, Any], market: dict[str, Any]) -> tuple[str, str | None, float | None]:
    side = str(mc.get("recommended_side") or mc.get("model_signal") or "").upper()
    if side == "OVER":
        return side, market.get("best_over_book"), sf(market.get("best_over_price"), float("nan"))
    if side == "UNDER":
        return side, market.get("best_under_book"), sf(market.get("best_under_price"), float("nan"))
    return side, None, None


def build(target: str, min_probability: float, min_ev: float, min_books: int, min_history: int) -> dict[str, Any]:
    mc_payload = load(MC_PATH, {})
    lookup = consensus_lookup()
    generated = datetime.now(timezone.utc)
    rows = []
    rejected: dict[str, int] = {}

    for mc in mc_payload.get("all_simulations", []) or []:
        key = (norm(mc.get("player")), str(mc.get("stat") or "").upper(), norm(mc.get("game")))
        market = lookup.get(key)
        if not market:
            rejected["no_consensus_market"] = rejected.get("no_consensus_market", 0) + 1
            continue

        side, book, odds = choose_market(mc, market)
        probability = sf(mc.get("over_probability") if side == "OVER" else mc.get("under_probability"))
        book_count = int(sf(market.get("book_count")))
        history_games = int(sf(mc.get("history_games", mc.get("history_games_available", 0))))

        reasons = []
        if probability < min_probability:
            reasons.append("probability")
        if not book or book not in ALLOWED_BOOKS:
            reasons.append("sportsbook")
        if odds is None or not math.isfinite(odds) or abs(odds) > 10000 or odds == 0:
            reasons.append("odds")
        if book_count < min_books:
            reasons.append("books")
        if history_games and history_games < min_history:
            reasons.append("history")
        if str(mc.get("injury_status") or "ACTIVE").upper() not in {"ACTIVE", "PROBABLE"}:
            reasons.append("injury")

        ev = expected_value(probability, odds) if odds is not None and math.isfinite(odds) and odds != 0 else -99
        if ev < min_ev:
            reasons.append("ev")
        if reasons:
            for reason in set(reasons):
                rejected[reason] = rejected.get(reason, 0) + 1
            continue

        rows.append({
            "snapshot_id": f"{target}|{mc.get('player')}|{mc.get('stat')}|{mc.get('line')}|{side}",
            "player": mc.get("player"),
            "team": mc.get("team"),
            "game": mc.get("game"),
            "stat": mc.get("stat"),
            "side": side,
            "line": mc.get("line"),
            "sportsbook": book,
            "american_odds": int(odds),
            "model_probability": round(probability, 4),
            "implied_probability": round(american_implied(odds), 4),
            "fair_odds": fair_american(probability),
            "ev_pct": round(ev * 100, 2),
            "projection_mean": mc.get("projection_mean"),
            "projection_sd": mc.get("projection_sd"),
            "p05": mc.get("p05"),
            "p25": mc.get("p25"),
            "p50": mc.get("p50"),
            "p75": mc.get("p75"),
            "p95": mc.get("p95"),
            "simulations": mc.get("simulations"),
            "risk_band": mc.get("risk_band"),
            "matchup_score": mc.get("matchup_score"),
            "role_score": mc.get("role_score"),
            "injury_status": mc.get("injury_status"),
            "minutes_trend": mc.get("minutes_trend"),
            "book_count": book_count,
            "history_games": history_games or None,
            "test_status": "PENDING",
            "actual": None,
            "outcome": None,
        })

    rows.sort(key=lambda row: (row["ev_pct"], row["model_probability"], -sf(row.get("projection_sd"))), reverse=True)
    # Keep a small, reviewable paper-trading card and avoid multiple correlated rows for the same player/stat.
    card = []
    seen = set()
    game_counts: dict[str, int] = {}
    for row in rows:
        key = (norm(row["player"]), row["stat"])
        if key in seen:
            continue
        if game_counts.get(str(row["game"]), 0) >= 3:
            continue
        seen.add(key)
        game_counts[str(row["game"])] = game_counts.get(str(row["game"]), 0) + 1
        card.append(row)
        if len(card) >= 12:
            break

    report = {
        "generated_at_utc": generated.isoformat(),
        "target_date": target,
        "mode": "PAPER_TEST_ONLY",
        "locked": True,
        "rules": {
            "minimum_probability": min_probability,
            "minimum_ev": min_ev,
            "minimum_books": min_books,
            "minimum_history_games": min_history,
            "allowed_books": sorted(ALLOWED_BOOKS),
            "maximum_card_size": 12,
            "maximum_plays_per_game": 3,
        },
        "summary": {
            "simulation_rows": len(mc_payload.get("all_simulations", []) or []),
            "qualified_rows": len(rows),
            "live_test_card_size": len(card),
            "rejected": rejected,
        },
        "live_test_card": card,
        "all_qualified": rows,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    archive = ARCHIVE_DIR / f"monte_carlo_live_test_{target}_{stamp}.json"
    archive.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Locked snapshot: {archive}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--min-probability", type=float, default=0.70)
    parser.add_argument("--min-ev", type=float, default=0.02)
    parser.add_argument("--min-books", type=int, default=2)
    parser.add_argument("--min-history", type=int, default=5)
    args = parser.parse_args()
    build(args.date, args.min_probability, args.min_ev, args.min_books, args.min_history)


if __name__ == "__main__":
    main()
