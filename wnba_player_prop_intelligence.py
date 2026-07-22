"""Sprint 5: player and prop intelligence for WNBA Odds Warehouse V2.

Builds persistent SQLite intelligence tables and dashboard JSON from player,
alternate-player, quarter-player, and team-prop wagers. The engine is safe when
no graded prop rows exist: it still creates the schema and publishes health data.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
DASHBOARD_OUT = Path("data/dashboard/wnba_player_prop_intelligence.json")
WAREHOUSE_OUT = Path("data/warehouse/wnba_player_prop_intelligence.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def pct(n: float, d: float) -> float | None:
    return None if not d else round(100.0 * n / d, 2)


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return None if not values else round(sum(values) / len(values), 4)


def confidence(sample: int) -> str:
    if sample >= 100:
        return "high"
    if sample >= 40:
        return "medium"
    return "low"


def prop_family(market: str) -> str:
    key = market.lower()
    for token, label in (
        ("points_rebounds_assists", "pra"),
        ("points_rebounds", "pr"),
        ("points_assists", "pa"),
        ("rebounds_assists", "ra"),
        ("three", "threes"),
        ("points", "points"),
        ("rebounds", "rebounds"),
        ("assists", "assists"),
        ("blocks", "blocks"),
        ("steals", "steals"),
        ("turnovers", "turnovers"),
        ("double_double", "double_double"),
    ):
        if token in key:
            return label
    if "team_total" in key:
        return "team_total"
    return key


def market_scope(market: str) -> str:
    key = market.lower()
    if "alternate" in key:
        return "alternate_player"
    if key.startswith("player_") or "player" in key:
        if any(x in key for x in ("1q", "q1", "1st_quarter")):
            return "quarter_player"
        return "player"
    if "team_total" in key or "team_prop" in key:
        return "team"
    return "other"


def is_prop_market(market: str) -> bool:
    return market_scope(market) != "other"


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS prop_market_intelligence(
      market TEXT PRIMARY KEY,
      scope TEXT NOT NULL,
      family TEXT NOT NULL,
      graded_bets INTEGER NOT NULL,
      wins INTEGER NOT NULL,
      losses INTEGER NOT NULL,
      pushes INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      avg_line REAL,
      avg_price REAL,
      avg_line_move REAL,
      avg_price_move REAL,
      beat_close_pct REAL,
      confidence TEXT NOT NULL,
      generated_at_utc TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS player_prop_intelligence(
      player TEXT NOT NULL,
      market TEXT NOT NULL,
      family TEXT NOT NULL,
      graded_bets INTEGER NOT NULL,
      wins INTEGER NOT NULL,
      losses INTEGER NOT NULL,
      pushes INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      avg_line REAL,
      avg_price REAL,
      confidence TEXT NOT NULL,
      generated_at_utc TEXT NOT NULL,
      PRIMARY KEY(player,market)
    );
    CREATE TABLE IF NOT EXISTS player_prop_line_intelligence(
      player TEXT NOT NULL,
      market TEXT NOT NULL,
      selection TEXT NOT NULL,
      line REAL NOT NULL,
      graded_bets INTEGER NOT NULL,
      wins INTEGER NOT NULL,
      losses INTEGER NOT NULL,
      pushes INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      avg_price REAL,
      confidence TEXT NOT NULL,
      generated_at_utc TEXT NOT NULL,
      PRIMARY KEY(player,market,selection,line)
    );
    CREATE TABLE IF NOT EXISTS player_prop_sportsbook_intelligence(
      player TEXT NOT NULL,
      market TEXT NOT NULL,
      sportsbook TEXT NOT NULL,
      graded_bets INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      avg_line REAL,
      avg_price REAL,
      generated_at_utc TEXT NOT NULL,
      PRIMARY KEY(player,market,sportsbook)
    );
    CREATE TABLE IF NOT EXISTS prop_sportsbook_intelligence(
      sportsbook TEXT NOT NULL,
      market TEXT NOT NULL,
      graded_bets INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      avg_line REAL,
      avg_price REAL,
      avg_line_move REAL,
      avg_price_move REAL,
      beat_close_pct REAL,
      generated_at_utc TEXT NOT NULL,
      PRIMARY KEY(sportsbook,market)
    );
    CREATE TABLE IF NOT EXISTS prop_trend_intelligence(
      trend_key TEXT PRIMARY KEY,
      category TEXT NOT NULL,
      label TEXT NOT NULL,
      sample_size INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      confidence TEXT NOT NULL,
      generated_at_utc TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS player_prop_profiles(
      player TEXT PRIMARY KEY,
      markets INTEGER NOT NULL,
      graded_bets INTEGER NOT NULL,
      wins INTEGER NOT NULL,
      losses INTEGER NOT NULL,
      pushes INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      best_market TEXT,
      best_sportsbook TEXT,
      generated_at_utc TEXT NOT NULL
    );
    """)


def fetch_graded(con: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = con.execute("""
      SELECT w.*, g.grade, g.profit_units,
             e.home_team, e.away_team, e.game_date_utc,
             e.commence_time_utc, s.returned_at_utc
      FROM wagers w
      JOIN grades g ON g.wager_id=w.wager_id
      JOIN events e ON e.event_id=w.event_id
      JOIN snapshots s ON s.snapshot_id=w.snapshot_id
      WHERE g.grade IN ('win','loss','push')
    """).fetchall()
    return [r for r in rows if is_prop_market(str(r["market_key"] or ""))]


def fetch_movements(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute("""
      SELECT w.event_id,w.bookmaker_key,w.market_key,w.outcome_key,w.selection,
             w.participant,w.point,w.american_price,s.returned_at_utc,
             e.commence_time_utc
      FROM wagers w
      JOIN snapshots s ON s.snapshot_id=w.snapshot_id
      JOIN events e ON e.event_id=w.event_id
      WHERE s.returned_at_utc<=e.commence_time_utc
      ORDER BY w.event_id,w.bookmaker_key,w.market_key,w.outcome_key,s.returned_at_utc
    """).fetchall()
    grouped: dict[tuple[str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        market = str(r["market_key"] or "")
        if is_prop_market(market):
            grouped[(r["event_id"], r["bookmaker_key"], market, r["outcome_key"])].append(r)
    out: list[dict[str, Any]] = []
    for key, series in grouped.items():
        opening, closing = series[0], series[-1]
        op, cp = opening["point"], closing["point"]
        oo, co = opening["american_price"], closing["american_price"]
        line_move = None if op is None or cp is None else float(cp) - float(op)
        price_move = None if oo is None or co is None else int(co) - int(oo)
        side = str(closing["selection"] or "")
        beat_close = None
        if line_move is not None:
            beat_close = line_move > 0 if side.lower() == "over" else line_move < 0 if side.lower() == "under" else None
        elif price_move is not None:
            beat_close = price_move > 0
        out.append({
            "sportsbook": key[1], "market": key[2],
            "player": str(closing["participant"] or "Unknown"),
            "selection": side, "line_move": line_move,
            "price_move": price_move, "beat_close": beat_close,
        })
    return out


def summarize(rows: list[sqlite3.Row], key_fn) -> list[dict[str, Any]]:
    groups: dict[Any, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    output = []
    for key, rs in groups.items():
        wins = sum(r["grade"] == "win" for r in rs)
        losses = sum(r["grade"] == "loss" for r in rs)
        pushes = sum(r["grade"] == "push" for r in rs)
        bets = len(rs)
        units = round(sum(float(r["profit_units"] or 0) for r in rs), 4)
        lines = [float(r["point"]) for r in rs if r["point"] is not None]
        prices = [float(r["american_price"]) for r in rs if r["american_price"] is not None]
        output.append({
            "key": key, "bets": bets, "wins": wins, "losses": losses,
            "pushes": pushes, "win_pct": pct(wins, wins + losses),
            "units": units, "roi_pct": pct(units, bets),
            "avg_line": mean(lines), "avg_price": mean(prices),
            "confidence": confidence(bets),
        })
    return sorted(output, key=lambda x: ((x["roi_pct"] if x["roi_pct"] is not None else -math.inf), x["bets"]), reverse=True)


def movement_summary(rows: list[dict[str, Any]], key_fn) -> dict[Any, dict[str, Any]]:
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    out = {}
    for key, rs in groups.items():
        known = [r for r in rs if r["beat_close"] is not None]
        out[key] = {
            "observations": len(rs),
            "avg_line_move": mean(float(r["line_move"]) for r in rs if r["line_move"] is not None),
            "avg_price_move": mean(float(r["price_move"]) for r in rs if r["price_move"] is not None),
            "beat_close_pct": pct(sum(bool(r["beat_close"]) for r in known), len(known)),
        }
    return out


def build(db: Path) -> dict[str, Any]:
    if not db.exists():
        raise SystemExit(f"Warehouse not found: {db}")
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    ensure_schema(con)
    stamp = utc_now()
    graded = fetch_graded(con)
    moves = fetch_movements(con)

    by_market = summarize(graded, lambda r: str(r["market_key"]))
    by_player_market = summarize(graded, lambda r: (str(r["participant"] or "Unknown"), str(r["market_key"])))
    by_line = summarize(
        [r for r in graded if r["point"] is not None],
        lambda r: (str(r["participant"] or "Unknown"), str(r["market_key"]), str(r["selection"] or ""), float(r["point"])),
    )
    by_player_book = summarize(graded, lambda r: (str(r["participant"] or "Unknown"), str(r["market_key"]), str(r["bookmaker_key"])))
    by_book_market = summarize(graded, lambda r: (str(r["bookmaker_key"]), str(r["market_key"])))
    market_moves = movement_summary(moves, lambda r: r["market"])
    book_market_moves = movement_summary(moves, lambda r: (r["sportsbook"], r["market"]))

    for table in (
        "prop_market_intelligence", "player_prop_intelligence",
        "player_prop_line_intelligence", "player_prop_sportsbook_intelligence",
        "prop_sportsbook_intelligence", "prop_trend_intelligence",
        "player_prop_profiles",
    ):
        con.execute(f"DELETE FROM {table}")

    for x in by_market:
        m = market_moves.get(x["key"], {})
        con.execute("INSERT INTO prop_market_intelligence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            x["key"], market_scope(x["key"]), prop_family(x["key"]), x["bets"], x["wins"], x["losses"], x["pushes"],
            x["win_pct"], x["units"], x["roi_pct"], x["avg_line"], x["avg_price"],
            m.get("avg_line_move"), m.get("avg_price_move"), m.get("beat_close_pct"), x["confidence"], stamp,
        ))
    for x in by_player_market:
        player, market = x["key"]
        con.execute("INSERT INTO player_prop_intelligence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            player, market, prop_family(market), x["bets"], x["wins"], x["losses"], x["pushes"],
            x["win_pct"], x["units"], x["roi_pct"], x["avg_line"], x["avg_price"], x["confidence"], stamp,
        ))
    for x in by_line:
        player, market, selection, line = x["key"]
        con.execute("INSERT INTO player_prop_line_intelligence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            player, market, selection, line, x["bets"], x["wins"], x["losses"], x["pushes"],
            x["win_pct"], x["units"], x["roi_pct"], x["avg_price"], x["confidence"], stamp,
        ))
    for x in by_player_book:
        player, market, sportsbook = x["key"]
        con.execute("INSERT INTO player_prop_sportsbook_intelligence VALUES(?,?,?,?,?,?,?,?,?,?)", (
            player, market, sportsbook, x["bets"], x["win_pct"], x["units"], x["roi_pct"], x["avg_line"], x["avg_price"], stamp,
        ))
    for x in by_book_market:
        sportsbook, market = x["key"]
        m = book_market_moves.get(x["key"], {})
        con.execute("INSERT INTO prop_sportsbook_intelligence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
            sportsbook, market, x["bets"], x["win_pct"], x["units"], x["roi_pct"], x["avg_line"], x["avg_price"],
            m.get("avg_line_move"), m.get("avg_price_move"), m.get("beat_close_pct"), stamp,
        ))

    trends: list[dict[str, Any]] = []
    for category, items in (
        ("prop_market", by_market), ("player_market", by_player_market),
        ("player_line", by_line), ("sportsbook_market", by_book_market),
    ):
        for x in items:
            if x["bets"] < 10:
                continue
            label = " | ".join(map(str, x["key"])) if isinstance(x["key"], tuple) else str(x["key"])
            trend = {"trend_key": f"{category}|{label}", "category": category, "label": label,
                     "sample_size": x["bets"], "win_pct": x["win_pct"], "units": x["units"],
                     "roi_pct": x["roi_pct"], "confidence": x["confidence"]}
            trends.append(trend)
    trends.sort(key=lambda x: ((x["roi_pct"] if x["roi_pct"] is not None else -math.inf), x["sample_size"]), reverse=True)
    for x in trends:
        con.execute("INSERT INTO prop_trend_intelligence VALUES(?,?,?,?,?,?,?,?,?)", (
            x["trend_key"], x["category"], x["label"], x["sample_size"], x["win_pct"],
            x["units"], x["roi_pct"], x["confidence"], stamp,
        ))

    players: dict[str, list[dict[str, Any]]] = defaultdict(list)
    player_books: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for x in by_player_market:
        players[x["key"][0]].append(x)
    for x in by_player_book:
        player_books[x["key"][0]].append(x)
    profiles = []
    for player, items in players.items():
        bets = sum(x["bets"] for x in items)
        wins = sum(x["wins"] for x in items)
        losses = sum(x["losses"] for x in items)
        pushes = sum(x["pushes"] for x in items)
        units = round(sum(x["units"] for x in items), 4)
        best_market = max(items, key=lambda x: (x["roi_pct"] if x["roi_pct"] is not None else -math.inf, x["bets"]))["key"][1]
        books = player_books.get(player, [])
        best_book = max(books, key=lambda x: (x["roi_pct"] if x["roi_pct"] is not None else -math.inf, x["bets"]))["key"][2] if books else None
        profile = {"player": player, "markets": len(items), "graded_bets": bets, "wins": wins, "losses": losses,
                   "pushes": pushes, "win_pct": pct(wins, wins + losses), "units": units,
                   "roi_pct": pct(units, bets), "best_market": best_market, "best_sportsbook": best_book}
        profiles.append(profile)
        con.execute("INSERT INTO player_prop_profiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
            player, len(items), bets, wins, losses, pushes, profile["win_pct"], units,
            profile["roi_pct"], best_market, best_book, stamp,
        ))
    profiles.sort(key=lambda x: ((x["roi_pct"] if x["roi_pct"] is not None else -math.inf), x["graded_bets"]), reverse=True)
    con.commit()

    payload = {
        "sprint": 5,
        "generated_at_utc": stamp,
        "database": str(db),
        "graded_prop_wagers": len(graded),
        "prop_movement_series": len(moves),
        "market_intelligence": by_market,
        "player_profiles": profiles[:250],
        "player_market_intelligence": [dict(x, key=list(x["key"])) for x in by_player_market[:500]],
        "player_line_intelligence": [dict(x, key=list(x["key"])) for x in by_line[:500]],
        "sportsbook_market_intelligence": [dict(x, key=list(x["key"])) for x in by_book_market[:250]],
        "top_prop_trends": trends[:250],
        "health": {
            "schema_created": True,
            "has_graded_props": bool(graded),
            "has_prop_line_movement": bool(moves),
            "tables_built": 7,
            "markets_analyzed": len(by_market),
            "players_analyzed": len(profiles),
        },
    }
    for path in (DASHBOARD_OUT, WAREHOUSE_OUT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    args = parser.parse_args()
    print(json.dumps(build(args.db), indent=2))


if __name__ == "__main__":
    main()
