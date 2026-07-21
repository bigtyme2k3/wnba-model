"""Build verified first-quarter WNBA game-props research outputs."""
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
MASTER = DASH / "wnba_master.json"
Q1_HISTORY = WAREHOUSE / "wnba_q1_team_history.json"
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
    text = str(value or "").strip().lower().replace("’", "'")
    aliases = {
        "las vegas aces": "las vegas aces", "aces": "las vegas aces",
        "new york liberty": "new york liberty", "liberty": "new york liberty",
        "golden state valkyries": "golden state valkyries", "valkyries": "golden state valkyries",
        "toronto tempo": "toronto tempo", "tempo": "toronto tempo",
    }
    return aliases.get(" ".join(text.split()), " ".join(text.split()))


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def current_games(target: str) -> list[dict[str, Any]]:
    payload = load(MASTER, {})
    games = payload.get("games", []) if isinstance(payload, dict) else []
    out = []
    for game in games:
        if not isinstance(game, dict):
            continue
        game_date = str(game.get("game_date") or game.get("date") or "")[:10]
        if game_date and game_date != target:
            continue
        away = str(game.get("away_team") or "").strip()
        home = str(game.get("home_team") or "").strip()
        if away and home:
            out.append({**game, "away_team": away, "home_team": home, "game": f"{away} @ {home}"})
    return out


def q1_team_history() -> tuple[dict[str, list[float]], dict[str, Any]]:
    payload = load(Q1_HISTORY, {"records": [], "summary": {}})
    history: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in payload.get("records", []):
        if not isinstance(row, dict):
            continue
        team = str(row.get("team") or "").strip()
        game_date = str(row.get("game_date") or "")[:10]
        value = num(row.get("q1_points"))
        if team and game_date and value is not None:
            history[norm(team)].append((game_date, value))
    result: dict[str, list[float]] = {}
    for team, rows in history.items():
        rows.sort(key=lambda item: item[0])
        result[team] = [value for _, value in rows]
    return result, payload.get("summary", {})


def race_probability(team_rate: float, opp_rate: float, target: int) -> float:
    total = max(0.1, team_rate + opp_rate)
    share = min(0.99, max(0.01, team_rate / total))
    probability = 0.0
    for losses in range(target):
        probability += math.comb(target + losses - 1, losses) * share**target * (1-share)**losses
    return min(0.99, max(0.01, probability))


def player_q1_rows(target: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen = set()
    for path in (RAW / f"props_raw_{target}.csv", RAW / "props_today.csv"):
        for row in read_csv(path):
            market = str(row.get("stat_raw") or row.get("market_key") or "").lower()
            stat = str(row.get("stat") or "").lower()
            if market not in {"player_points_q1", "player_points_1st_quarter"} and stat not in {"q1_pts", "q1 points"}:
                continue
            key = (row.get("event_id"), row.get("player"), row.get("line"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "game": f"{row.get('away_team','')} @ {row.get('home_team','')}",
                "event_id": row.get("event_id"), "player": row.get("player"),
                "line": num(row.get("line")), "over_price": num(row.get("over_price")),
                "under_price": num(row.get("under_price")), "num_books": int(num(row.get("num_books")) or 0),
                "source": row.get("source") or "the-odds-api", "scraped_at": row.get("scraped_at"),
            })
        if rows:
            break
    return rows


def q1_moneyline_rows(target: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in (RAW / f"game_props_q1_{target}.csv", RAW / "game_props_q1_today.csv"):
        for row in read_csv(path):
            market = str(row.get("market_key") or row.get("market") or "").lower()
            if market not in {"h2h_q1", "first_quarter_moneyline", "q1_moneyline"}:
                continue
            rows.append({
                "game": row.get("game") or f"{row.get('away_team','')} @ {row.get('home_team','')}",
                "team": row.get("team") or row.get("name"), "price": num(row.get("price") or row.get("odds")),
                "sportsbook": row.get("sportsbook") or row.get("bookmaker"),
                "source": row.get("source") or "the-odds-api", "scraped_at": row.get("scraped_at"),
            })
        if rows:
            break
    return rows


def build(target: str) -> dict[str, Any]:
    games = current_games(target)
    history, history_summary = q1_team_history()
    player_rows = player_q1_rows(target)
    moneyline_rows = q1_moneyline_rows(target)
    game_rows = []
    for game in games:
        away, home = game["away_team"], game["home_team"]
        away_hist = history.get(norm(away), [])[-20:]
        home_hist = history.get(norm(home), [])[-20:]
        away_avg = sum(away_hist)/len(away_hist) if away_hist else None
        home_avg = sum(home_hist)/len(home_hist) if home_hist else None
        race = []
        winner = None
        if away_avg is not None and home_avg is not None:
            for threshold in (10, 15, 20):
                away_probability = race_probability(away_avg, home_avg, threshold)
                race.append({
                    "threshold": threshold, "away_team": away, "home_team": home,
                    "away_probability": round(away_probability, 4),
                    "home_probability": round(1-away_probability, 4),
                    "source": "verified_q1_history_model", "sportsbook_odds_available": False,
                })
            difference = home_avg-away_avg
            home_probability = 1/(1+math.exp(-difference/3.5))
            winner = {"home_probability": round(home_probability,4), "away_probability": round(1-home_probability,4), "source": "verified_q1_history_model"}
        game_rows.append({
            "game": game["game"], "event_id": game.get("game_id") or game.get("event_id"),
            "commence_time": game.get("commence_time") or game.get("start_time"),
            "away_team": away, "home_team": home,
            "away_q1_average": round(away_avg,2) if away_avg is not None else None,
            "home_q1_average": round(home_avg,2) if home_avg is not None else None,
            "away_samples": len(away_hist), "home_samples": len(home_hist),
            "q1_winner_model": winner, "race_markets": race,
            "history_available": bool(away_hist and home_hist),
        })
    usable_games = sum(bool(g.get("history_available")) for g in game_rows)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target,
        "status": "ok" if usable_games else "waiting_for_q1_history" if games else "no_games",
        "summary": {
            "games": len(game_rows), "games_with_verified_q1_history": usable_games,
            "player_q1_props": len(player_rows), "sportsbook_q1_moneylines": len(moneyline_rows),
            "race_model_rows": sum(len(g["race_markets"]) for g in game_rows),
            "history_records": history_summary.get("records", 0), "history_games": history_summary.get("games", 0),
        },
        "player_q1_points": player_rows, "sportsbook_q1_moneyline": moneyline_rows, "games": game_rows,
        "guardrails": [
            "Race-to probabilities are model estimates, not sportsbook prices.",
            "Q1 averages use verified completed-game ESPN first-period linescores only.",
            "Sportsbook Q1 markets display only when supplied by the source.",
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
