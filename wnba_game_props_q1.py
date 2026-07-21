"""Build a first-quarter game-props research board.

Markets:
- player first-quarter points (sportsbook rows when supplied)
- first-quarter moneyline / winner (sportsbook rows when supplied)
- race to 10 / 15 / 20 model probabilities

Race probabilities are explicitly model estimates until a sportsbook price is
available. The engine never fabricates sportsbook odds.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

RAW = Path("data/raw")
DASH = Path("data/dashboard")
WAREHOUSE = Path("data/warehouse")
PLAYER_LOGS = WAREHOUSE / "wnba_player_game_logs.json"
MASTER = DASH / "wnba_master.json"
OUTS = [DASH / "wnba_game_props_q1.json", WAREHOUSE / "wnba_game_props_q1.json"]


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def american_to_prob(odds: Any) -> float | None:
    value = num(odds)
    if value is None or value == 0:
        return None
    return abs(value) / (abs(value) + 100) if value < 0 else 100 / (value + 100)


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def current_games(target: str) -> list[dict[str, Any]]:
    master = load(MASTER, {})
    games = master.get("games", []) if isinstance(master, dict) else []
    rows = []
    for game in games:
        if not isinstance(game, dict):
            continue
        game_date = str(game.get("game_date") or game.get("date") or "")[:10]
        if game_date and game_date != target:
            continue
        away = str(game.get("away_team") or "").strip()
        home = str(game.get("home_team") or "").strip()
        if away and home:
            rows.append({**game, "away_team": away, "home_team": home, "game": f"{away} @ {home}"})
    return rows


def q1_team_history() -> dict[str, list[float]]:
    payload = load(PLAYER_LOGS, {"records": []})
    grouped: dict[tuple[str, str], float] = defaultdict(float)
    for row in payload.get("records", []):
        if not isinstance(row, dict):
            continue
        team = str(row.get("team") or "").strip()
        game_id = str(row.get("game_id") or row.get("game_date") or "").strip()
        scoring = row.get("scoring") if isinstance(row.get("scoring"), dict) else {}
        q1 = num(scoring.get("q1_pts"))
        if team and game_id and q1 is not None:
            grouped[(norm(team), game_id)] += q1
    history: dict[str, list[float]] = defaultdict(list)
    for (team, _), value in grouped.items():
        history[team].append(value)
    return history


def poisson_cdf(k: int, lam: float) -> float:
    term = math.exp(-lam)
    total = term
    for i in range(1, k + 1):
        term *= lam / i
        total += term
    return min(1.0, max(0.0, total))


def race_probability(team_rate: float, opp_rate: float, target: int) -> float:
    # Gamma-race approximation: scoring arrival share raised across target events.
    total = max(0.1, team_rate + opp_rate)
    share = min(0.99, max(0.01, team_rate / total))
    # Probability team wins a best-of-(2t-1) scoring-event race.
    probability = 0.0
    for losses in range(target):
        probability += math.comb(target + losses - 1, losses) * (share ** target) * ((1 - share) ** losses)
    return min(0.99, max(0.01, probability))


def player_q1_rows(target: str) -> list[dict[str, Any]]:
    rows = []
    for path in (RAW / f"props_raw_{target}.csv", RAW / "props_today.csv"):
        for row in read_csv(path):
            market = str(row.get("stat_raw") or row.get("market_key") or "").lower()
            stat = str(row.get("stat") or "").lower()
            if market not in {"player_points_q1", "player_points_1st_quarter"} and stat not in {"q1_pts", "q1 points"}:
                continue
            rows.append({
                "game": f"{row.get('away_team','')} @ {row.get('home_team','')}",
                "event_id": row.get("event_id"),
                "player": row.get("player"),
                "line": num(row.get("line")),
                "over_price": num(row.get("over_price")),
                "under_price": num(row.get("under_price")),
                "num_books": int(num(row.get("num_books")) or 0),
                "source": row.get("source") or "the-odds-api",
                "scraped_at": row.get("scraped_at"),
            })
        if rows:
            break
    return rows


def q1_moneyline_rows(target: str) -> list[dict[str, Any]]:
    candidates = [RAW / f"game_props_q1_{target}.csv", RAW / "game_props_q1_today.csv"]
    rows = []
    for path in candidates:
        for row in read_csv(path):
            market = str(row.get("market_key") or row.get("market") or "").lower()
            if market not in {"h2h_q1", "first_quarter_moneyline", "q1_moneyline"}:
                continue
            rows.append({
                "game": row.get("game") or f"{row.get('away_team','')} @ {row.get('home_team','')}",
                "team": row.get("team") or row.get("name"),
                "price": num(row.get("price") or row.get("odds")),
                "sportsbook": row.get("sportsbook") or row.get("bookmaker"),
                "source": row.get("source") or "the-odds-api",
                "scraped_at": row.get("scraped_at"),
            })
        if rows:
            break
    return rows


def build(target: str) -> dict[str, Any]:
    games = current_games(target)
    history = q1_team_history()
    player_rows = player_q1_rows(target)
    moneyline_rows = q1_moneyline_rows(target)
    game_rows = []
    for game in games:
        away, home = game["away_team"], game["home_team"]
        away_hist = history.get(norm(away), [])[-20:]
        home_hist = history.get(norm(home), [])[-20:]
        away_avg = sum(away_hist) / len(away_hist) if away_hist else None
        home_avg = sum(home_hist) / len(home_hist) if home_hist else None
        race = []
        if away_avg is not None and home_avg is not None:
            for threshold in (10, 15, 20):
                away_prob = race_probability(away_avg, home_avg, threshold)
                race.append({
                    "threshold": threshold,
                    "away_team": away,
                    "home_team": home,
                    "away_probability": round(away_prob, 4),
                    "home_probability": round(1-away_prob, 4),
                    "source": "model_estimate",
                    "sportsbook_odds_available": False,
                })
        winner_prob = None
        if away_avg is not None and home_avg is not None:
            diff = home_avg - away_avg
            home_prob = 1 / (1 + math.exp(-diff / 3.5))
            winner_prob = {"home_probability": round(home_prob, 4), "away_probability": round(1-home_prob, 4), "source": "q1_scoring_history_model"}
        game_rows.append({
            "game": game["game"], "event_id": game.get("game_id") or game.get("event_id"),
            "commence_time": game.get("commence_time") or game.get("start_time"),
            "away_team": away, "home_team": home,
            "away_q1_average": round(away_avg, 2) if away_avg is not None else None,
            "home_q1_average": round(home_avg, 2) if home_avg is not None else None,
            "away_samples": len(away_hist), "home_samples": len(home_hist),
            "q1_winner_model": winner_prob, "race_markets": race,
        })
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok" if games else "no_games",
        "summary": {
            "games": len(game_rows), "player_q1_props": len(player_rows),
            "sportsbook_q1_moneylines": len(moneyline_rows),
            "race_model_rows": sum(len(g["race_markets"]) for g in game_rows),
        },
        "player_q1_points": player_rows,
        "sportsbook_q1_moneyline": moneyline_rows,
        "games": game_rows,
        "guardrails": [
            "Race-to probabilities are model estimates, not sportsbook prices.",
            "Sportsbook Q1 markets display only when the source actually supplies them.",
            "No unavailable market is converted into a betting recommendation.",
        ],
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print("Q1 GAME PROPS ACTIVE", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
