from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SPORT = "basketball_wnba"
BASE = "https://api.the-odds-api.com/v4"
ET = ZoneInfo("America/New_York")
DASH = Path("data/dashboard")
RAW = Path("data/raw")
MARKETS = [
    "player_points", "player_rebounds", "player_assists", "player_threes",
    "player_points_rebounds_assists", "player_points_rebounds",
    "player_points_assists", "player_rebounds_assists",
]
STAT_MAP = {
    "player_points": "PTS", "player_rebounds": "REB", "player_assists": "AST",
    "player_threes": "3PM", "player_points_rebounds_assists": "PRA",
    "player_points_rebounds": "PR", "player_points_assists": "PA",
    "player_rebounds_assists": "RA",
}


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def event_date(value: str) -> str:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.astimezone(ET).date().isoformat()


def roster_map() -> dict[str, str]:
    out: dict[str, str] = {}
    master = load_json(DASH / "wnba_master.json", {})
    for row in master.get("players", []) if isinstance(master, dict) else []:
        name = str(row.get("player") or row.get("name") or "").strip()
        team = str(row.get("team") or "").strip()
        if name and team:
            out[name.casefold()] = team
    live = load_json(RAW / "wnba_players_live.json", {})
    if isinstance(live, dict):
        for key, row in live.items():
            if not isinstance(row, dict):
                continue
            name = str(row.get("player") or key or "").strip()
            team = str(row.get("team") or "").strip()
            if name and team:
                out[name.casefold()] = team
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    target = args.date
    api_key = os.getenv("ODDS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ODDS_API_KEY is required")

    DASH.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    events_resp = session.get(f"{BASE}/sports/{SPORT}/events", params={"apiKey": api_key}, timeout=30)
    events_resp.raise_for_status()
    events = [e for e in events_resp.json() if event_date(e.get("commence_time")) == target]
    teams_by_player = roster_map()
    grouped: dict[tuple, dict] = {}
    raw_events = []

    for event in events:
        event_id = event["id"]
        away = str(event.get("away_team") or "").strip()
        home = str(event.get("home_team") or "").strip()
        game = f"{away} @ {home}"
        resp = session.get(
            f"{BASE}/sports/{SPORT}/events/{event_id}/odds",
            params={
                "apiKey": api_key,
                "regions": "us",
                "markets": ",".join(MARKETS),
                "oddsFormat": "american",
                "dateFormat": "iso",
            },
            timeout=45,
        )
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        payload = resp.json()
        raw_events.append(payload)
        for book in payload.get("bookmakers", []):
            book_name = book.get("title") or book.get("key")
            for market in book.get("markets", []):
                stat = STAT_MAP.get(market.get("key"))
                if not stat:
                    continue
                for outcome in market.get("outcomes", []):
                    player = str(outcome.get("description") or "").strip()
                    side = str(outcome.get("name") or "").upper().strip()
                    line = outcome.get("point")
                    price = outcome.get("price")
                    if not player or side not in {"OVER", "UNDER"} or line is None:
                        continue
                    key = (event_id, player.casefold(), stat, float(line))
                    row = grouped.setdefault(key, {
                        "target_date": target,
                        "event_id": event_id,
                        "commence_time": event.get("commence_time"),
                        "game": game,
                        "away_team": away,
                        "home_team": home,
                        "player": player,
                        "team": teams_by_player.get(player.casefold(), ""),
                        "stat": stat,
                        "line": float(line),
                        "books": [],
                    })
                    row["books"].append({"book": book_name, "side": side, "price": price})

    rows = []
    for row in grouped.values():
        overs = [x for x in row["books"] if x["side"] == "OVER" and isinstance(x.get("price"), (int, float))]
        unders = [x for x in row["books"] if x["side"] == "UNDER" and isinstance(x.get("price"), (int, float))]
        best_over = max(overs, key=lambda x: x["price"], default={})
        best_under = max(unders, key=lambda x: x["price"], default={})
        row.update({
            "best_over_book": best_over.get("book"),
            "best_over_price": best_over.get("price"),
            "best_under_book": best_under.get("book"),
            "best_under_price": best_under.get("price"),
            "book_count": len({x["book"] for x in row["books"]}),
        })
        rows.append(row)

    output = {
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "target_date": target,
        "source": "the_odds_api_event_markets",
        "event_count": len(events),
        "row_count": len(rows),
        "rows": sorted(rows, key=lambda r: (r["game"], r["player"], r["stat"], r["line"])),
    }
    (DASH / "wnba_player_props.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    (RAW / f"wnba_player_props_{target}.json").write_text(json.dumps(raw_events, indent=2), encoding="utf-8")
    print(json.dumps({"target_date": target, "events": len(events), "rows": len(rows), "missing_team": sum(not r["team"] for r in rows)}, indent=2))


if __name__ == "__main__":
    main()
