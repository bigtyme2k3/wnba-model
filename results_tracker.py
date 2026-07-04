"""
results_tracker.py
------------------
Grades saved WNBA best bets against ESPN final scores and writes a running log.
Designed for GitHub Actions after games are final.

Usage:
    python results_tracker.py --date 2026-07-04
"""

import argparse
import glob
import json
import os
import re
from datetime import date, datetime, timedelta

import pandas as pd
import requests

PREDICTIONS_DIR = "predictions"
RESULTS_FILE = "data/results_log.csv"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"


def fetch_scores(target_date: str) -> dict:
    params = {"dates": target_date.replace("-", "")}
    try:
        resp = requests.get(ESPN_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  [WARN] ESPN fetch failed: {exc}")
        return {}

    scores = {}
    for event in data.get("events", []):
        status = event.get("status", {}).get("type", {}).get("name", "")
        if "FINAL" not in status.upper():
            continue

        comps = event.get("competitions", [{}])[0]
        competitors = comps.get("competitors", [])
        if len(competitors) < 2:
            continue

        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
        home_name = home.get("team", {}).get("displayName", "")
        away_name = away.get("team", {}).get("displayName", "")
        home_score = int(home.get("score", 0) or 0)
        away_score = int(away.get("score", 0) or 0)
        key = f"{away_name}@{home_name}"
        scores[key] = {
            "game_id": event.get("id"),
            "home_team": home_name,
            "away_team": away_name,
            "home_score": home_score,
            "away_score": away_score,
            "actual_spread": home_score - away_score,
            "actual_total": home_score + away_score,
        }
        print(f"  {away_name} {away_score} @ {home_name} {home_score}")
    return scores


def prediction_path(target_date: str) -> str | None:
    exact = os.path.join(PREDICTIONS_DIR, f"predictions_{target_date}.json")
    if os.path.exists(exact):
        return exact
    files = sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")))
    return files[-1] if files else None


def load_predictions(target_date: str) -> dict:
    path = prediction_path(target_date)
    if not path:
        return {}
    if not path.endswith(f"predictions_{target_date}.json"):
        print(f"  [INFO] Exact date file missing. Using latest file: {path}")
    with open(path) as f:
        return json.load(f)


def extract_number(text):
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", str(text or ""))
    return float(nums[-1]) if nums else None


def grade_spread(bet, game, score):
    play = str(bet.get("play", ""))
    home = game.get("home", {}).get("name", "")
    away = game.get("away", {}).get("name", "")
    actual_home_margin = score["actual_spread"]

    play_line = extract_number(play)
    if play_line is None:
        market_line = bet.get("market_line", game.get("spread", {}).get("posted_line"))
        if market_line is None:
            return "NO_LINE", None
        play_line = float(market_line)

    # If the play names the away team, flip to away margin.
    if away.lower() in play.lower():
        margin = -actual_home_margin
        # If market_line was home spread and play_line came from market_line, flip it.
        if bet.get("market_line") is not None and extract_number(play) is None:
            play_line = -float(bet["market_line"])
    else:
        margin = actual_home_margin

    graded = margin + play_line
    if abs(graded) < 1e-9:
        return "PUSH", graded
    return ("WIN" if graded > 0 else "LOSS"), graded


def grade_total(bet, game, score):
    play = str(bet.get("play", "")).upper()
    line = bet.get("market_line", game.get("totals", {}).get("line"))
    if line is None:
        line = extract_number(play)
    if line is None:
        return "NO_LINE", None

    actual_total = score["actual_total"]
    diff = actual_total - float(line)
    if abs(diff) < 1e-9:
        return "PUSH", diff
    if "UNDER" in play:
        return ("WIN" if diff < 0 else "LOSS"), diff
    if "OVER" in play:
        return ("WIN" if diff > 0 else "LOSS"), diff
    return "NO_PLAY", diff


def evaluate_bets(predictions: dict, scores: dict) -> list:
    results = []
    games = {f"{g['away']['name']}@{g['home']['name']}": g for g in predictions.get("games", [])}

    for bet in predictions.get("best_bets", []):
        game_key = str(bet.get("game", "")).replace(" @ ", "@")
        score = scores.get(game_key)
        game = games.get(game_key, {})

        if not score:
            result, grade_margin = "NO_RESULT", None
        elif bet.get("type") == "SPREAD":
            result, grade_margin = grade_spread(bet, game, score)
        elif bet.get("type") == "TOTAL":
            result, grade_margin = grade_total(bet, game, score)
        else:
            result, grade_margin = "PENDING_PROP", None

        results.append({
            "date": predictions.get("date", ""),
            "type": bet.get("type", ""),
            "game": bet.get("game", ""),
            "play": bet.get("play", ""),
            "edge": bet.get("edge", 0),
            "edge_abs": bet.get("edge_abs", abs(bet.get("edge", 0) or 0)),
            "conf": bet.get("conf", ""),
            "stars": bet.get("stars", 1),
            "result": result,
            "grade_margin": grade_margin,
            "home_score": score.get("home_score") if score else None,
            "away_score": score.get("away_score") if score else None,
            "actual_spread": score.get("actual_spread") if score else None,
            "actual_total": score.get("actual_total") if score else None,
            "evaluated_at": datetime.now().isoformat(),
        })
    return results


def update_log(new_results: list) -> pd.DataFrame:
    new_df = pd.DataFrame(new_results)
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)

    if os.path.exists(RESULTS_FILE):
        old = pd.read_csv(RESULTS_FILE)
        if not new_df.empty:
            keys = set(zip(new_df["date"], new_df["type"], new_df["game"], new_df["play"]))
            old = old[~old.apply(lambda r: (r.get("date"), r.get("type"), r.get("game"), r.get("play")) in keys, axis=1)]
        log = pd.concat([old, new_df], ignore_index=True)
    else:
        log = new_df

    log.to_csv(RESULTS_FILE, index=False)
    return log


def compute_record(log: pd.DataFrame) -> dict:
    if log.empty:
        return {"overall": "0-0", "win_pct": 0, "total_bets": 0, "by_type": {}, "by_conf": {}, "recent_10": []}

    decided = log[log["result"].isin(["WIN", "LOSS"])]
    wins = int((decided["result"] == "WIN").sum())
    losses = int((decided["result"] == "LOSS").sum())
    total = wins + losses
    record = {
        "overall": f"{wins}-{losses}",
        "win_pct": round(wins / total, 3) if total else 0,
        "total_bets": total,
        "by_type": {},
        "by_conf": {},
        "recent_10": [],
    }

    for col, key in [("type", "by_type"), ("conf", "by_conf")]:
        for value in sorted(decided[col].dropna().unique()):
            sub = decided[decided[col] == value]
            w = int((sub["result"] == "WIN").sum())
            l = int((sub["result"] == "LOSS").sum())
            record[key][value] = f"{w}-{l} ({w/(w+l):.0%})" if (w + l) else "0-0"

    recent = decided.tail(10)
    record["recent_10"] = [
        {"date": r["date"], "type": r["type"], "play": r["play"], "result": r["result"], "edge": r.get("edge", 0)}
        for _, r in recent.iterrows()
    ]
    return record


def inject_record(record: dict):
    files = sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")))
    if not files:
        return
    latest = files[-1]
    with open(latest) as f:
        data = json.load(f)
    data["record"] = record
    with open(latest, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Record injected into {latest}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today() - timedelta(days=1)))
    args = parser.parse_args()

    print(f"\n═══ RESULTS TRACKER — {args.date} ═══\n")
    scores = fetch_scores(args.date)
    preds = load_predictions(args.date)
    if not preds:
        print("  No predictions file found.")
        return

    results = evaluate_bets(preds, scores)
    log = update_log(results)
    record = compute_record(log)
    inject_record(record)

    print(f"  Results logged: {len(results)} new / {len(log)} total")
    print(f"  Overall record: {record.get('overall')} ({record.get('win_pct', 0):.1%})")
    for r in results:
        icon = "✅" if r["result"] == "WIN" else "❌" if r["result"] == "LOSS" else "—"
        print(f"  {icon} [{r['type']}] {r['play']} → {r['result']}")
    print("\n✅ Results tracking complete.")


if __name__ == "__main__":
    main()
