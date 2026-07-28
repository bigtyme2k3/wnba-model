"""Collect current WNBA game and modeled player-prop lines for DraftKings/FanDuel only."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from line_shopping import COLUMNS, empty_df, parse_game_markets, parse_prop_event, summarize_best

API_KEY = os.getenv("ODDS_API_KEY")
BASE = "https://api.the-odds-api.com/v4/sports/basketball_wnba"
BOOKS = "draftkings,fanduel"
GAME_MARKETS = "h2h,spreads,totals"
PROP_MARKETS = "player_points,player_rebounds,player_assists,player_threes,player_points_rebounds_assists"
OUT = Path("data/raw")


def get(path: str, markets: str) -> tuple[Any, dict[str, int | None]]:
    if not API_KEY:
        raise RuntimeError("ODDS_API_KEY is required")
    response = requests.get(
        f"{BASE}{path}",
        params={
            "apiKey": API_KEY,
            "bookmakers": BOOKS,
            "markets": markets,
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
        timeout=30,
    )
    if response.status_code == 401:
        raise RuntimeError("ODDS_API_KEY is invalid or unauthorized")
    if response.status_code == 429:
        raise RuntimeError("The Odds API quota or rate limit was reached")
    if response.status_code in {404, 422}:
        return ([] if path == "/odds" else {}), {}
    response.raise_for_status()
    usage = {}
    for header, key in (("x-requests-last", "last"), ("x-requests-used", "used"), ("x-requests-remaining", "remaining")):
        try:
            usage[key] = int(response.headers.get(header, ""))
        except ValueError:
            usage[key] = None
    return response.json(), usage


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()
    target_date = generated[:10]
    games, core_usage = get("/odds", GAME_MARKETS)
    rows, events = parse_game_markets(games, target_date)
    prop_requests = 0
    failures = []
    last_usage = core_usage
    now_dt = datetime.now(timezone.utc)

    for event in events:
        try:
            commence = pd.to_datetime(event.get("commence_time"), utc=True, errors="coerce")
            if pd.isna(commence) or commence.to_pydatetime() <= now_dt:
                continue
            if (commence.to_pydatetime() - now_dt).total_seconds() > 48 * 3600:
                continue
            data, last_usage = get(f"/events/{event['id']}/odds", PROP_MARKETS)
            rows.extend(parse_prop_event(data, str(commence.date())))
            prop_requests += 1
        except Exception as exc:
            failures.append({"event_id": event.get("id"), "error": str(exc)})
        time.sleep(0.25)

    frame = pd.DataFrame(rows, columns=COLUMNS) if rows else empty_df()
    if not frame.empty:
        frame = frame[frame["book_key"].astype(str).str.lower().isin({"draftkings", "fanduel"})].copy()
        parsed = pd.to_datetime(frame["commence_time"], utc=True, errors="coerce")
        frame["game_date"] = parsed.dt.date.astype(str)
    best = summarize_best(frame)
    frame.to_csv(OUT / "line_shopping_today.csv", index=False)
    best.to_csv(OUT / "line_shopping_best_today.csv", index=False)
    status = {
        "generated_at_utc": generated,
        "status": "PASS" if len(frame) else "WARN",
        "source": "The Odds API current endpoints",
        "books": ["draftkings", "fanduel"],
        "game_markets": GAME_MARKETS.split(","),
        "prop_markets": PROP_MARKETS.split(","),
        "events_seen": len(events),
        "prop_event_requests": prop_requests,
        "rows": int(len(frame)),
        "prop_rows": int((frame["market_type"] == "PROP").sum()) if not frame.empty else 0,
        "failures": failures,
        "api_usage": last_usage or core_usage,
    }
    (OUT / "sprint24_phase2_live_collection_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))
    return status


if __name__ == "__main__":
    run()
