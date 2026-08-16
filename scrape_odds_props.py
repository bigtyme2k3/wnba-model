"""Fetch WNBA player props from The Odds API.

Standard markets continue feeding the existing props pipeline. Alternate markets
are additionally written at bookmaker/outcome granularity so FanDuel,
DraftKings, Fanatics, and other books retain their own exact thresholds.

Current event IDs are always refreshed from The Odds API before player-market
requests. Cached schedule files are never trusted as the event-ID authority,
because event identifiers can become stale and return 404s even when the slate
itself is still correct.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API_KEY = os.getenv("ODDS_API_KEY")
MIN_REMAINING = int(os.getenv("ODDS_API_MIN_REMAINING", "1500"))
SPORT = "basketball_wnba"
REGIONS = "us"
ODDS_FMT = "american"
PLAYER_PROP_BOOKS = {"draftkings", "fanduel", "fanatics"}
PLAYER_PROP_BOOKMAKERS = ",".join(sorted(PLAYER_PROP_BOOKS))
BASE_URL = "https://api.the-odds-api.com/v4/sports"
ET = ZoneInfo("America/New_York")


def enforce_credit_reserve(response, label: str) -> None:
    """Stop additional paid market calls before the monthly reserve is spent."""
    raw = response.headers.get("x-requests-remaining")
    try:
        remaining = int(raw)
    except (TypeError, ValueError):
        return
    if remaining <= MIN_REMAINING:
        raise RuntimeError(
            f"Odds API credit reserve reached after {label}: {remaining} remaining "
            f"(minimum reserve {MIN_REMAINING}). Refusing additional market calls."
        )

PROP_MARKETS = {
    "player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "threes",
    "player_points_rebounds_assists": "pra", "player_points_assists": "pa",
    "player_points_rebounds": "pr", "player_rebounds_assists": "ra",
    "player_points_q1": "q1_pts",
}
ALT_PROP_MARKETS = {
    "player_points_alternate": "PTS", "player_rebounds_alternate": "REB",
    "player_assists_alternate": "AST", "player_threes_alternate": "3PM",
    "player_points_rebounds_assists_alternate": "PRA", "player_points_assists_alternate": "PA",
    "player_points_rebounds_alternate": "PR", "player_rebounds_assists_alternate": "RA",
}

RAW_COLUMNS = [
    "game_date", "event_id", "player", "team", "position", "opp_team", "is_home",
    "stat_raw", "stat", "line", "over_price", "under_price", "yes_price", "no_price",
    "num_books", "sportsbooks", "odds_type", "game_time", "home_team", "away_team", "source", "scraped_at",
]
ALT_COLUMNS = [
    "game_date", "event_id", "game", "game_time", "home_team", "away_team", "player", "team",
    "stat", "side", "threshold", "odds", "sportsbook", "sportsbook_key", "market_key", "source", "scraped_at",
]


def avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def empty_df():
    return pd.DataFrame(columns=RAW_COLUMNS)


def empty_alt_df():
    return pd.DataFrame(columns=ALT_COLUMNS)


def load_events_from_odds(raw_dir: str, target: str) -> list[dict]:
    """Compatibility-only cached slate reader.

    Cached game IDs are deliberately not used as live event IDs. This helper is
    retained for diagnostics and team/date comparison only.
    """
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
            print(f"  Cached slate contains {len(events)} event IDs in {path} (diagnostic only)")
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
    enforce_credit_reserve(resp, "events refresh")
    payload = resp.json()
    return payload if isinstance(payload, list) else []


def event_et_date(event: dict) -> str | None:
    raw = str(event.get("commence_time") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ET).date().isoformat()
    except Exception:
        return None


def fetch_current_target_events(target: str, raw_dir: str) -> list[dict]:
    """Return fresh event IDs for the requested Eastern-time slate date."""
    fresh = fetch_events()
    target_events = [e for e in fresh if isinstance(e, dict) and event_et_date(e) == target and e.get("id")]
    cached = load_events_from_odds(raw_dir, target)
    cached_ids = {str(e.get("id")) for e in cached if e.get("id")}
    fresh_ids = {str(e.get("id")) for e in target_events if e.get("id")}
    stale_ids = sorted(cached_ids - fresh_ids)
    print(f"  Fresh target-date events: {len(target_events)}")
    if stale_ids:
        print(f"  Rejected {len(stale_ids)} stale cached event IDs: {', '.join(stale_ids[:8])}{' ...' if len(stale_ids) > 8 else ''}")
    if not target_events:
        raise RuntimeError(f"No fresh The Odds API WNBA events found for Eastern slate date {target}; refusing cached event-ID fallback")
    return target_events


def fetch_event_markets(event_id: str, markets: list[str], label: str) -> dict:
    if not API_KEY:
        raise ValueError("ODDS_API_KEY not set")
    url = f"{BASE_URL}/{SPORT}/events/{event_id}/odds"
    # The model's supported book universe is deliberately narrow. Supplying
    # bookmakers here reduces upstream response volume as well as preventing
    # unsupported books from entering consensus prices.
    params = {"apiKey": API_KEY, "bookmakers": PLAYER_PROP_BOOKMAKERS, "markets": ",".join(markets), "oddsFormat": ODDS_FMT}
    resp = requests.get(url, params=params, timeout=25)
    print(f"  Event {event_id} {label}: HTTP {resp.status_code} | used {resp.headers.get('x-requests-used','?')} remaining {resp.headers.get('x-requests-remaining','?')}")
    if resp.status_code in (404, 422):
        return {}
    resp.raise_for_status()
    enforce_credit_reserve(resp, f"event market {event_id}")
    return resp.json()


def parse_event_props(event_data: dict, target: str) -> list[dict]:
    if not event_data:
        return []
    event_id = event_data.get("id", ""); home = event_data.get("home_team", ""); away = event_data.get("away_team", "")
    game_time = event_data.get("commence_time", ""); scraped_at = datetime.now(timezone.utc).isoformat()
    grouped = defaultdict(lambda: {"over_prices": [], "under_prices": [], "yes_prices": [], "no_prices": [], "lines": [], "books": set()})
    for book in event_data.get("bookmakers", []) or []:
        book_key = str(book.get("key") or "").lower()
        if book_key not in PLAYER_PROP_BOOKS:
            continue
        for market in book.get("markets", []) or []:
            mkey = market.get("key"); stat = PROP_MARKETS.get(mkey)
            if not stat:
                continue
            for outcome in market.get("outcomes", []) or []:
                player = outcome.get("description") or outcome.get("name") or ""; side = str(outcome.get("name", "")).lower()
                point = outcome.get("point"); price = outcome.get("price")
                if not player or price is None or point is None:
                    continue
                point_key = float(point); key = (player, mkey, stat, point_key)
                grouped[key]["lines"].append(point_key); grouped[key]["books"].add(book_key)
                if side == "over": grouped[key]["over_prices"].append(price)
                elif side == "under": grouped[key]["under_prices"].append(price)
    rows = []
    for (player, mkey, stat, point), info in grouped.items():
        rows.append({
            "game_date": target, "event_id": event_id, "player": player, "team": "", "position": "",
            "opp_team": f"{away} @ {home}", "is_home": "", "stat_raw": mkey, "stat": stat,
            "line": avg(info["lines"]), "over_price": avg(info["over_prices"]), "under_price": avg(info["under_prices"]),
            "yes_price": None, "no_price": None, "num_books": len(info["books"]),
            "sportsbooks": ",".join(sorted(info["books"])), "odds_type": "sportsbook",
            "game_time": game_time, "home_team": home, "away_team": away, "source": "the-odds-api", "scraped_at": scraped_at,
        })
    return rows


def parse_alt_props(event_data: dict, target: str) -> list[dict]:
    if not event_data:
        return []
    event_id = event_data.get("id", ""); home = event_data.get("home_team", ""); away = event_data.get("away_team", "")
    game_time = event_data.get("commence_time", ""); scraped_at = datetime.now(timezone.utc).isoformat(); rows = []
    for book in event_data.get("bookmakers", []) or []:
        book_key = str(book.get("key") or ""); book_title = str(book.get("title") or book_key or "book")
        if book_key.lower() not in PLAYER_PROP_BOOKS:
            continue
        for market in book.get("markets", []) or []:
            market_key = str(market.get("key") or ""); stat = ALT_PROP_MARKETS.get(market_key)
            if not stat:
                continue
            for outcome in market.get("outcomes", []) or []:
                player = str(outcome.get("description") or "").strip(); side = str(outcome.get("name") or "").upper()
                threshold = outcome.get("point"); odds = outcome.get("price")
                if not player or side not in {"OVER", "UNDER"} or threshold is None or odds is None:
                    continue
                rows.append({
                    "game_date": target, "event_id": event_id, "game": f"{away} @ {home}", "game_time": game_time,
                    "home_team": home, "away_team": away, "player": player, "team": "", "stat": stat, "side": side,
                    "threshold": float(threshold), "odds": odds, "sportsbook": book_title, "sportsbook_key": book_key,
                    "market_key": market_key, "source": "the-odds-api", "scraped_at": scraped_at,
                })
    return rows


def audit_alt_payload(event_data: dict) -> dict[str, object]:
    """Describe raw upstream alternate outcomes before local filtering.

    The Odds API does not accept separate OVER/UNDER market parameters. Both
    sides, when offered by a book, are outcomes inside the requested
    ``*_alternate`` market. This audit proves which sides arrived upstream.
    """
    sides = {"OVER": 0, "UNDER": 0, "OTHER": 0}
    by_market: dict[str, dict[str, int]] = {}
    bookmakers = 0
    for book in (event_data or {}).get("bookmakers", []) or []:
        bookmakers += 1
        for market in book.get("markets", []) or []:
            key = str(market.get("key") or "")
            if key not in ALT_PROP_MARKETS:
                continue
            bucket = by_market.setdefault(key, {"OVER": 0, "UNDER": 0, "OTHER": 0})
            for item in market.get("outcomes", []) or []:
                side = str(item.get("name") or "").upper()
                label = side if side in {"OVER", "UNDER"} else "OTHER"
                sides[label] += 1
                bucket[label] += 1
    return {"bookmakers": bookmakers, "outcome_sides": sides, "by_market": by_market}


def save_outputs(df: pd.DataFrame, alt_df: pd.DataFrame, target: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    if df.empty: df = empty_df()
    if alt_df.empty: alt_df = empty_alt_df()
    for path in (os.path.join(out_dir, "props_today.csv"), os.path.join(out_dir, f"props_raw_{target}.csv")):
        df.to_csv(path, index=False)
    for path in (os.path.join(out_dir, "alt_props_bookmakers_today.csv"), os.path.join(out_dir, f"alt_props_bookmakers_{target}.csv")):
        alt_df.to_csv(path, index=False)
    hist_path = os.path.join(out_dir, "props_historical.csv")
    if not df.empty:
        hist = pd.read_csv(hist_path) if os.path.exists(hist_path) else pd.DataFrame()
        if not hist.empty and "game_date" in hist.columns: hist = hist[hist["game_date"] != target]
        pd.concat([hist, df], ignore_index=True).to_csv(hist_path, index=False)
    print(f"  Standard rows: {len(df)} | exact ALT rows: {len(alt_df)}")


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); parser.add_argument("--out", default="data/raw"); parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument("--skip-alt", action="store_true", help="Skip alternate-market API requests to conserve credits")
    args = parser.parse_args()
    print(f"\n═══ THE ODDS API WNBA PLAYER PROPS — {args.date} ═══\n")
    status = {"status": "unknown", "target_date": args.date, "source": "the-odds-api", "checked_at_utc": datetime.now(timezone.utc).isoformat(), "events": 0, "rows": 0, "alt_rows": 0, "sportsbooks": sorted(PLAYER_PROP_BOOKS), "markets": list(PROP_MARKETS), "alt_markets": list(ALT_PROP_MARKETS), "alt_request_contract": "OVER and UNDER are outcomes returned inside each *_alternate market; there is no separate side request parameter", "raw_alt_api_audit": [], "event_id_policy": "fresh_api_only", "error": None}
    try:
        events = fetch_current_target_events(args.date, args.out)
        status["events"] = len(events); standard_rows = []; alt_rows = []
        valid_event_requests = 0
        for event in events:
            event_id = event.get("id")
            if not event_id: continue
            standard_payload = fetch_event_markets(event_id, list(PROP_MARKETS), "standard")
            alt_payload = {} if args.skip_alt else fetch_event_markets(event_id, list(ALT_PROP_MARKETS), "alternate")
            if not args.skip_alt:
                raw_audit = audit_alt_payload(alt_payload)
                raw_audit["event_id"] = event_id
                status["raw_alt_api_audit"].append(raw_audit)
                print(f"  Raw ALT upstream side audit {event_id}: {raw_audit['outcome_sides']}")
            if standard_payload or alt_payload:
                valid_event_requests += 1
            standard_rows.extend(parse_event_props(standard_payload, args.date))
            if not args.skip_alt:
                alt_rows.extend(parse_alt_props(alt_payload, args.date))
            time.sleep(args.delay)
        if valid_event_requests == 0:
            raise RuntimeError(f"Fresh event IDs were found for {args.date}, but all player-market requests failed or returned empty payloads")
        df = pd.DataFrame(standard_rows, columns=RAW_COLUMNS) if standard_rows else empty_df()
        alt_df = pd.DataFrame(alt_rows, columns=ALT_COLUMNS) if alt_rows else empty_alt_df()
        status["rows"] = len(df); status["alt_rows"] = len(alt_df); status["status"] = "ok" if (not df.empty or not alt_df.empty) else "empty"
        save_outputs(df, alt_df, args.date, args.out)
    except Exception as exc:
        status["status"] = "error"; status["error"] = str(exc); print(f"  [ERROR] {exc}"); save_outputs(empty_df(), empty_alt_df(), args.date, args.out)
    with open(os.path.join(args.out, "odds_props_status.json"), "w") as handle: json.dump(status, handle, indent=2)
    print("✅ Odds props scrape complete.")


if __name__ == "__main__":
    main()
