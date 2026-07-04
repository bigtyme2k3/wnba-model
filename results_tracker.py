"""
results_tracker.py
------------------
Compares yesterday's predictions against actual ESPN results.
Updates a running W/L log and injects the record into the dashboard.

Run daily AFTER games complete (schedule after midnight ET).

Usage:
    python results_tracker.py
    python results_tracker.py --date 2026-07-03
"""

import os, json, glob, argparse, requests, pandas as pd
from datetime import date, datetime, timedelta

PREDICTIONS_DIR = "predictions"
RESULTS_FILE    = "data/results_log.csv"
ESPN_URL        = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"


def fetch_scores(target_date: str) -> dict:
    """Pull final scores from ESPN for a given date."""
    params = {"dates": target_date.replace("-", "")}
    try:
        resp = requests.get(ESPN_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [WARN] ESPN fetch failed: {e}")
        return {}

    results = {}
    for event in data.get("events", []):
        comps = event.get("competitions", [{}])[0]
        competitors = comps.get("competitors", [])
        if len(competitors) < 2:
            continue

        status = event.get("status", {}).get("type", {}).get("name", "")
        if "FINAL" not in status.upper():
            continue

        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home_name  = home.get("team", {}).get("displayName", "")
        away_name  = away.get("team", {}).get("displayName", "")
        home_score = int(home.get("score", 0) or 0)
        away_score = int(away.get("score", 0) or 0)

        key = f"{away_name}@{home_name}"
        results[key] = {
            "home_team":    home_name,
            "away_team":    away_name,
            "home_score":   home_score,
            "away_score":   away_score,
            "actual_spread":home_score - away_score,
            "actual_total": home_score + away_score,
        }
        print(f"  {away_name} {away_score} @ {home_name} {home_score}")

    return results


def load_predictions(target_date: str) -> dict:
    """Load predictions JSON for a given date."""
    path = os.path.join(PREDICTIONS_DIR, f"predictions_{target_date}.json")
    if not os.path.exists(path):
        # Try most recent
        files = sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")))
        if files:
            path = files[-1]
            print(f"  [INFO] Using {path}")
        else:
            return {}
    with open(path) as f:
        return json.load(f)


def evaluate_bets(predictions: dict, scores: dict) -> list:
    """Score each best bet against actual results."""
    results = []
    bets    = predictions.get("best_bets", [])
    games   = {f"{g['away']['name']}@{g['home']['name']}": g
               for g in predictions.get("games", [])}

    for bet in bets:
        game_key = bet["game"].replace(" @ ", "@")
        score    = scores.get(game_key)
        game     = games.get(game_key, {})

        if not score:
            # Try reversed key
            parts = game_key.split("@")
            if len(parts) == 2:
                score = scores.get(f"{parts[1]}@{parts[0]}")

        if not score:
            result = "NO_RESULT"
            won    = None
        else:
            actual_spread = score["actual_spread"]
            actual_total  = score["actual_total"]
            bet_type      = bet["type"]
            play          = bet["play"]
            edge          = bet.get("edge", 0) or 0

            if bet_type == "SPREAD":
                # Parse which side we bet
                # model_line e.g. "NYL -4.1" means we bet NYL -4.1
                # positive actual_spread = home won
                tot = game.get("totals", {})
                sp  = game.get("spread", {})
                line = sp.get("posted_line")
                if line is not None:
                    home_covered = actual_spread > -line
                    # Did we bet home or away?
                    bet_home = edge > 0
                    won = home_covered if bet_home else not home_covered
                else:
                    won = None

            elif bet_type == "TOTAL":
                line = game.get("totals", {}).get("line")
                if line is not None:
                    if "OVER" in play:
                        won = actual_total > line
                    else:
                        won = actual_total < line
                else:
                    won = None

            elif bet_type == "PROP":
                # Can't verify without box scores — mark as pending
                won = None

            if won is None:
                result = "NO_LINE"
            elif won:
                result = "WIN"
            else:
                result = "LOSS"

        results.append({
            "date":      predictions.get("date", ""),
            "type":      bet["type"],
            "game":      bet["game"],
            "play":      bet["play"],
            "edge":      bet.get("edge", 0),
            "conf":      bet.get("conf", ""),
            "stars":     bet.get("stars", 1),
            "result":    result,
            "actual_spread": score["actual_spread"] if score else None,
            "actual_total":  score["actual_total"]  if score else None,
            "home_score":    score["home_score"]    if score else None,
            "away_score":    score["away_score"]    if score else None,
            "evaluated_at":  datetime.now().isoformat(),
        })

    return results


def update_log(new_results: list):
    """Append new results to the running log."""
    new_df = pd.DataFrame(new_results)

    if os.path.exists(RESULTS_FILE):
        existing = pd.read_csv(RESULTS_FILE)
        # Don't duplicate — remove old entries for same date
        if not new_df.empty and "date" in existing.columns:
            dates = new_df["date"].unique()
            existing = existing[~existing["date"].isin(dates)]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
    combined.to_csv(RESULTS_FILE, index=False)
    return combined


def compute_record(log: pd.DataFrame) -> dict:
    """Compute overall and by-type W/L records."""
    if log.empty:
        return {}

    decided = log[log["result"].isin(["WIN","LOSS"])]
    if decided.empty:
        return {"overall": "0-0", "win_pct": 0}

    wins   = (decided["result"] == "WIN").sum()
    losses = (decided["result"] == "LOSS").sum()
    total  = wins + losses

    record = {
        "overall":    f"{wins}-{losses}",
        "win_pct":    round(wins / total, 3) if total else 0,
        "total_bets": int(total),
        "by_type":    {},
        "by_conf":    {},
        "recent_10":  [],
    }

    # By type
    for t in ["SPREAD","TOTAL","PROP"]:
        sub = decided[decided["type"] == t]
        if not sub.empty:
            w = (sub["result"] == "WIN").sum()
            l = (sub["result"] == "LOSS").sum()
            record["by_type"][t] = f"{w}-{l} ({w/(w+l):.0%})" if (w+l) else "0-0"

    # By confidence
    for c in ["HIGH","MED","LOW"]:
        sub = decided[decided["conf"] == c]
        if not sub.empty:
            w = (sub["result"] == "WIN").sum()
            l = (sub["result"] == "LOSS").sum()
            record["by_conf"][c] = f"{w}-{l} ({w/(w+l):.0%})" if (w+l) else "0-0"

    # Last 10 results
    recent = decided.tail(10)
    record["recent_10"] = [
        {"date": r["date"], "type": r["type"], "play": r["play"],
         "result": r["result"], "edge": r.get("edge", 0)}
        for _, r in recent.iterrows()
    ]

    return record


def inject_record_into_predictions(target_date: str, record: dict):
    """Add W/L record to today's predictions JSON for dashboard display."""
    pred_path = os.path.join(PREDICTIONS_DIR, f"predictions_{target_date}.json")
    if not os.path.exists(pred_path):
        return

    with open(pred_path) as f:
        data = json.load(f)

    data["record"] = record

    with open(pred_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  Record injected into {pred_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today() - timedelta(days=1)),
                        help="Date to evaluate (default: yesterday)")
    args = parser.parse_args()

    target = args.date
    print(f"\n═══ RESULTS TRACKER — evaluating {target} ═══\n")

    # Fetch actual scores
    print("Fetching ESPN final scores...")
    scores = fetch_scores(target)
    if not scores:
        print("  No final scores found yet. Run after games complete.")

    # Load predictions
    print(f"\nLoading predictions for {target}...")
    preds = load_predictions(target)
    if not preds:
        print("  No predictions file found.")
        return

    bets = preds.get("best_bets", [])
    print(f"  Found {len(bets)} best bets to evaluate")

    # Evaluate
    results = evaluate_bets(preds, scores)

    # Save to log
    log = update_log(results)
    print(f"\n  Results log: {len(log)} total entries → {RESULTS_FILE}")

    # Compute record
    record = compute_record(log)
    print(f"\n  Overall record: {record.get('overall','0-0')} ({record.get('win_pct',0):.1%})")
    for t, r in record.get("by_type",{}).items():
        print(f"  {t}: {r}")
    for c, r in record.get("by_conf",{}).items():
        print(f"  {c} conf: {r}")

    # Inject into today's predictions
    today = str(date.today())
    inject_record_into_predictions(today, record)

    # Print results
    print(f"\n── Yesterday's Results ──")
    for r in results:
        icon = "✅" if r["result"]=="WIN" else "❌" if r["result"]=="LOSS" else "—"
        print(f"  {icon} [{r['type']}] {r['play']} → {r['result']}")
        if r["actual_total"]:
            print(f"     Actual: {r['away_score']}-{r['home_score']} "
                  f"(total {r['actual_total']}, spread {r['actual_spread']:+d})")

    print("\n✅ Results tracking complete.")


if __name__ == "__main__":
    main()
