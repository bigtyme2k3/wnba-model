"""
scrape_odds_props.py
--------------------
Fetches WNBA player props from The Odds API and writes the raw props files used
by the dashboard/player_points pipeline.

This replaces PrizePicks as the props source.

Markets now include base stats, combo props, double-double, and triple-double.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from datetime import date, datetime, timezone

import pandas as pd
import requests

API_KEY = os.getenv("ODDS_API_KEY")
SPORT = "basketball_wnba"
REGIONS = "us"
ODDS_FMT = "american"
BASE_URL = "https://api.the-odds-api.com/v4/sports"

PROP_MARKETS = {
    "player_points": "pts",
    "player_rebounds": "reb",
    "player_assists": "ast",
    "player_threes": "threes",
    "player_points_rebounds_assists": "pra",
    "player_points_assists": "pa",
    "player_points_rebounds": "pr",
    "player_rebounds_assists": "ra",
    "player_double_double": "dd",
    "player_triple_double": "td",
}

RAW_COLUMNS = [
    "game_date", "event_id", "player", "team", "position", "opp_team", "is_home",
    "stat_raw", "stat", "line", "over_price", "under_price", "yes_price", "no_price",
    "num_books", "odds_type", "game_time", "home_team", "away_team", "source", "scraped_at"
]


def avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def empty_df():
    return pd.DataFrame(columns=RAW_COLUMNS)


def load_events_from_odds(raw_dir: str, target: str) -> list[dict]:
    candidates = [os.path.join(raw_dir, f"odds_{target}.csv"), os.path.join(raw_dir, "odds_today.csv")]
    for path in candidates:
        if os.path.exists(path):
            df = pd.read_csv(path)
            events = []
            for _, row in df.iterrows():
                gid = row.get("game_id")
                if pd.isna(gid) or not gid:
                    continue
                events.append({"id": str(gid), "commence_time": row.get("commence_time", ""), "home_team": row.get("home_team", ""), "away_team": row.get("away_team", "")})
            print(f"  Loaded {len(events)} events from {path}")
            return events
    return []


def fetch_events() -> list[dict]:
    if not API_KEY:
        raise ValueError("ODDS_API_KEY not set")
    url = f"{BASE_URL}/{SPORT}/events"
    resp = requests.get(url, params={"apiKey": API_KEY}, timeout=15)
    print(f"  Events HTTP {resp.status_code}")
    print(f"  API quota — used: {resp.headers.get('x-requests-used','?')} | remaining: {resp.headers.get('x-requests-remaining','?')}")
    if resp.status_code == 422:
        return []
    resp.raise_for_status()
    return resp.json()


def fetch_event_props(event_id: str) -> dict:
    if not API_KEY:
        raise ValueError("ODDS_API_KEY not set")
    url = f"{BASE_URL}/{SPORT}/events/{event_id}/odds"
    params = {"apiKey": API_KEY, "regions": REGIONS, "markets": ",".join(PROP_MARKETS.keys()), "oddsFormat": ODDS_FMT}
    resp = requests.get(url, params=params, timeout=20)
    print(f"  Event {event_id}: HTTP {resp.status_code} | used {resp.headers.get('x-requests-used','?')} remaining {resp.headers.get('x-requests-remaining','?')}")
    if resp.status_code in (404, 422):
        return {}
    resp.raise_for_status()
    return resp.json()


def parse_event_props(event_data: dict, target: str) -> list[dict]:
    if not event_data:
        return []

    event_id = event_data.get("id", "")
    home = event_data.get("home_team", "")
    away = event_data.get("away_team", "")
    game_time = event_data.get("commence_time", "")
    scraped_at = datetime.now(timezone.utc).isoformat()

    grouped = defaultdict(lambda: {"over_prices": [], "under_prices": [], "yes_prices": [], "no_prices": [], "lines": [], "books": set()})

    for book in event_data.get("bookmakers", []) or []:
        book_key = book.get("key") or book.get("title") or "book"
        for market in book.get("markets", []) or []:
            mkey = market.get("key")
            stat = PROP_MARKETS.get(mkey)
            if not stat:
                continue
            for outcome in market.get("outcomes", []) or []:
                player = outcome.get("description") or outcome.get("name") or ""
                side = str(outcome.get("name", "")).lower()
                point = outcome.get("point")
                price = outcome.get("price")
                if not player or price is None:
                    continue
                # Double-double/triple-double are usually yes/no markets with no point.
                point_key = float(point) if point is not None else 0.5
                key = (player, mkey, stat, point_key)
                grouped[key]["lines"].append(point_key)
                grouped[key]["books"].add(book_key)
                if side == "over":
                    grouped[key]["over_prices"].append(price)
                elif side == "under":
                    grouped[key]["under_prices"].append(price)
                elif side in {"yes", "record", "true"}:
                    grouped[key]["yes_prices"].append(price)
                elif side in {"no", "false"}:
                    grouped[key]["no_prices"].append(price)

    rows = []
    for (player, mkey, stat, point), info in grouped.items():
        rows.append({
            "game_date": target, "event_id": event_id, "player": player, "team": "", "position": "",
            "opp_team": f"{away} @ {home}", "is_home": "", "stat_raw": mkey, "stat": stat,
            "line": avg(info["lines"]), "over_price": avg(info["over_prices"]), "under_price": avg(info["under_prices"]),
            "yes_price": avg(info["yes_prices"]), "no_price": avg(info["no_prices"]), "num_books": len(info["books"]),
            "odds_type": "sportsbook", "game_time": game_time, "home_team": home, "away_team": away,
            "source": "the-odds-api", "scraped_at": scraped_at,
        })
    return rows


def save_outputs(df: pd.DataFrame, target: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    if df.empty:
        df = empty_df()
    today_path = os.path.join(out_dir, "props_today.csv")
    dated_path = os.path.join(out_dir, f"props_raw_{target}.csv")
    df.to_csv(today_path, index=False)
    df.to_csv(dated_path, index=False)
    hist_path = os.path.join(out_dir, "props_historical.csv")
    if not df.empty:
        if os.path.exists(hist_path):
            hist = pd.read_csv(hist_path)
            if "game_date" in hist.columns:
                hist = hist[hist["game_date"] != target]
            pd.concat([hist, df], ignore_index=True).to_csv(hist_path, index=False)
        else:
            df.to_csv(hist_path, index=False)
    print(f"  Saved → {today_path}")
    print(f"  Saved → {dated_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out", default="data/raw")
    parser.add_argument("--delay", type=float, default=1.2)
    args = parser.parse_args()

    print(f"\n═══ THE ODDS API WNBA PLAYER PROPS — {args.date} ═══\n")
    status = {"status": "unknown", "target_date": args.date, "source": "the-odds-api", "checked_at_utc": datetime.now(timezone.utc).isoformat(), "events": 0, "rows": 0, "markets": list(PROP_MARKETS.keys()), "error": None}

    try:
        events = load_events_from_odds(args.out, args.date)
        if not events:
            events = fetch_events()
        status["events"] = len(events)
        rows = []
        for event in events:
            event_id = event.get("id")
            if not event_id:
                continue
            data = fetch_event_props(event_id)
            rows.extend(parse_event_props(data, args.date))
            time.sleep(args.delay)
        df = pd.DataFrame(rows, columns=RAW_COLUMNS) if rows else empty_df()
        status["rows"] = int(len(df))
        status["status"] = "ok" if not df.empty else "empty"
        save_outputs(df, args.date, args.out)
        if not df.empty:
            print(df[["player", "stat", "line", "over_price", "under_price", "yes_price", "no_price", "num_books"]].head(25).to_string(index=False))
    except Exception as exc:
        status["status"] = "error"
        status["error"] = str(exc)
        print(f"  [ERROR] {exc}")
        save_outputs(empty_df(), args.date, args.out)

    status_path = os.path.join(args.out, "odds_props_status.json")
    with open(status_path, "w") as f:
        json.dump(status, f, indent=2)
    print(f"  Status → {status_path}")
    print("✅ Odds props scrape complete.")


if __name__ == "__main__":
    main()
