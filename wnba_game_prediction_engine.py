"""Build current-slate spread, total, and win-probability predictions from owned game history.

The engine is intentionally conservative: it blends rolling team performance with the
live market instead of pretending limited WNBA samples are perfectly predictive.
It writes a standalone report and enriches both normalized master files.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

MASTER_PATHS = [Path("data/dashboard/wnba_master.json"), Path("data/master/wnba_master.json")]
OUT_PATHS = [Path("data/dashboard/wnba_game_predictions.json"), Path("data/warehouse/wnba_game_predictions.json")]


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Warning: could not read {path}: {exc}")
    return default


def finite(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def read_history(target: str) -> list[dict[str, Any]]:
    """Read and deduplicate final team scores prior to the target slate."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    paths = sorted(glob.glob("data/raw/scores_*.csv")) + ["data/raw/scores.csv", "data/raw/scores_today.csv"]
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    game_date = str(row.get("game_date") or row.get("date") or "")[:10]
                    if not game_date or game_date >= target:
                        continue
                    home = str(row.get("home_team") or "").strip()
                    away = str(row.get("away_team") or "").strip()
                    hp = finite(row.get("home_score", row.get("home_pts")))
                    ap = finite(row.get("away_score", row.get("away_pts")))
                    if not home or not away or hp is None or ap is None:
                        continue
                    key = str(row.get("game_id") or f"{game_date}|{away}|{home}")
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({"game_id": key, "game_date": game_date, "home_team": home, "away_team": away, "home_pts": hp, "away_pts": ap})
        except Exception as exc:
            print(f"Warning: skipped {path}: {exc}")
    rows.sort(key=lambda r: (r["game_date"], r["game_id"]))
    return rows


def team_profiles(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    games: dict[str, list[dict[str, float]]] = defaultdict(list)
    for row in history:
        games[row["home_team"]].append({"scored": row["home_pts"], "allowed": row["away_pts"], "margin": row["home_pts"] - row["away_pts"]})
        games[row["away_team"]].append({"scored": row["away_pts"], "allowed": row["home_pts"], "margin": row["away_pts"] - row["home_pts"]})
    profiles: dict[str, dict[str, Any]] = {}
    for team, rows in games.items():
        last10 = rows[-10:]
        last5 = rows[-5:]
        avg = lambda sample, field, fallback: sum(x[field] for x in sample) / len(sample) if sample else fallback
        profiles[team] = {
            "games": len(rows),
            "last5_games": len(last5),
            "last10_games": len(last10),
            "scored_l5": round(avg(last5, "scored", 80.0), 2),
            "allowed_l5": round(avg(last5, "allowed", 80.0), 2),
            "margin_l5": round(avg(last5, "margin", 0.0), 2),
            "scored_l10": round(avg(last10, "scored", 80.0), 2),
            "allowed_l10": round(avg(last10, "allowed", 80.0), 2),
            "margin_l10": round(avg(last10, "margin", 0.0), 2),
        }
    return profiles


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def confidence(edge: float, samples: int) -> int:
    sample_factor = min(1.0, max(0.35, samples / 10.0))
    raw = 50 + min(35, abs(edge) * 6.0) * sample_factor
    return int(round(min(90, max(50, raw))))


def predict_game(game: dict[str, Any], profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    home = str(game.get("home_team") or "")
    away = str(game.get("away_team") or "")
    hp = profiles.get(home, {})
    ap = profiles.get(away, {})
    home_scored = 0.60 * finite(hp.get("scored_l5"), 80.0) + 0.40 * finite(hp.get("scored_l10"), 80.0)
    home_allowed = 0.60 * finite(hp.get("allowed_l5"), 80.0) + 0.40 * finite(hp.get("allowed_l10"), 80.0)
    away_scored = 0.60 * finite(ap.get("scored_l5"), 80.0) + 0.40 * finite(ap.get("scored_l10"), 80.0)
    away_allowed = 0.60 * finite(ap.get("allowed_l5"), 80.0) + 0.40 * finite(ap.get("allowed_l10"), 80.0)

    stats_home_points = (home_scored + away_allowed) / 2.0 + 1.4
    stats_away_points = (away_scored + home_allowed) / 2.0
    stats_margin = stats_home_points - stats_away_points
    stats_total = stats_home_points + stats_away_points

    market_spread = finite(game.get("spread"))
    market_total = finite(game.get("total"))
    market_margin = -market_spread if market_spread is not None else stats_margin

    min_samples = min(int(hp.get("last10_games", 0)), int(ap.get("last10_games", 0)))
    history_weight = min(0.72, max(0.42, min_samples / 14.0))
    model_margin = history_weight * stats_margin + (1.0 - history_weight) * market_margin
    model_total = history_weight * stats_total + (1.0 - history_weight) * (market_total if market_total is not None else stats_total)

    spread_edge = model_margin - market_margin
    total_edge = model_total - market_total if market_total is not None else 0.0
    home_win_probability = normal_cdf(model_margin / 11.5)

    if market_spread is None:
        spread_pick = None
    elif spread_edge >= 0:
        spread_pick = f"{home} {market_spread:+g}"
    else:
        away_line = -market_spread
        spread_pick = f"{away} {away_line:+g}"

    total_pick = None
    if market_total is not None:
        total_pick = f"{'OVER' if total_edge >= 0 else 'UNDER'} {market_total:g}"

    candidates = []
    if spread_pick:
        candidates.append({"market": "SPREAD", "pick": spread_pick, "edge": round(abs(spread_edge), 2), "signed_edge": round(spread_edge, 2), "confidence": confidence(spread_edge, min_samples)})
    if total_pick:
        candidates.append({"market": "TOTAL", "pick": total_pick, "edge": round(abs(total_edge), 2), "signed_edge": round(total_edge, 2), "confidence": confidence(total_edge, min_samples)})
    candidates.sort(key=lambda x: (x["edge"], x["confidence"]), reverse=True)
    best = candidates[0] if candidates and candidates[0]["edge"] >= 1.0 else None

    return clean({
        "game_id": game.get("game_id"),
        "game_date": game.get("game_date"),
        "game": game.get("game"),
        "away_team": away,
        "home_team": home,
        "market_spread": market_spread,
        "market_total": market_total,
        "predicted_home_points": round(model_total / 2.0 + model_margin / 2.0, 1),
        "predicted_away_points": round(model_total / 2.0 - model_margin / 2.0, 1),
        "predicted_home_margin": round(model_margin, 2),
        "predicted_total": round(model_total, 2),
        "home_win_probability": round(home_win_probability, 4),
        "away_win_probability": round(1.0 - home_win_probability, 4),
        "spread_edge": round(spread_edge, 2),
        "total_edge": round(total_edge, 2),
        "spread_pick": spread_pick,
        "total_pick": total_pick,
        "best_play": best,
        "all_game_plays": candidates,
        "sample_games": min_samples,
        "history_weight": round(history_weight, 3),
        "model_status": "ready" if min_samples >= 5 else "limited_history",
        "inputs": {"home": hp, "away": ap, "stats_margin": round(stats_margin, 2), "stats_total": round(stats_total, 2)},
    })


def build(target: str) -> dict[str, Any]:
    master = next((load_json(path, {}) for path in MASTER_PATHS if path.exists()), {})
    history = read_history(target)
    profiles = team_profiles(history)
    games = [g for g in master.get("games", []) if str(g.get("game_date") or "")[:10] == target and str(g.get("bucket") or "today") == "today"]
    predictions = [predict_game(game, profiles) for game in games]
    by_id = {str(row.get("game_id")): row for row in predictions}
    by_game = {str(row.get("game")): row for row in predictions}

    for path in MASTER_PATHS:
        data = load_json(path, {})
        if not data:
            continue
        for game in data.get("games", []):
            pred = by_id.get(str(game.get("game_id"))) or by_game.get(str(game.get("game")))
            if pred:
                game["prediction"] = pred
                game["model_spread"] = pred["predicted_home_margin"]
                game["model_total"] = pred["predicted_total"]
                game["home_win_probability"] = pred["home_win_probability"]
                game["spread_pick"] = pred["spread_pick"]
                game["total_pick"] = pred["total_pick"]
                game["best_game_play"] = pred["best_play"]
        data["game_predictions"] = predictions
        if isinstance(data.get("summary"), dict):
            data["summary"]["game_predictions"] = len(predictions)
        path.write_text(json.dumps(clean(data), indent=2, allow_nan=False), encoding="utf-8")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "summary": {
            "games": len(predictions),
            "ready": sum(row["model_status"] == "ready" for row in predictions),
            "limited_history": sum(row["model_status"] != "ready" for row in predictions),
            "spread_plays": sum(bool(row.get("spread_pick")) for row in predictions),
            "total_plays": sum(bool(row.get("total_pick")) for row in predictions),
            "qualified_best_plays": sum(bool(row.get("best_play")) for row in predictions),
            "historical_games": len(history),
            "teams_profiled": len(profiles),
        },
        "method": "rolling team scoring/defense blended with live market; conservative home-court adjustment; normal margin distribution",
        "predictions": predictions,
    }
    for path in OUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(clean(report), indent=2, allow_nan=False), encoding="utf-8")
    print("Game predictions built:", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
