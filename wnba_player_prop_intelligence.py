"""Derived player/prop intelligence from the canonical WNBA odds warehouse.

This module is intentionally consumer-only. It opens the canonical SQLite warehouse
read-only, derives player/market summaries in memory, and publishes JSON views only.
It must never create, delete, or update warehouse tables.
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


def connect_read_only(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise SystemExit(f"Warehouse not found: {db}")
    uri = f"file:{db.resolve().as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        con.close()
        raise SystemExit(f"Warehouse integrity check failed: {integrity}")
    return con


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
    for row in rows:
        market = str(row["market_key"] or "")
        if is_prop_market(market):
            grouped[(row["event_id"], row["bookmaker_key"], market, row["outcome_key"])].append(row)

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
            "sportsbook": key[1],
            "market": key[2],
            "player": str(closing["participant"] or "Unknown"),
            "selection": side,
            "line_move": line_move,
            "price_move": price_move,
            "beat_close": beat_close,
        })
    return out


def summarize(rows: list[sqlite3.Row], key_fn) -> list[dict[str, Any]]:
    groups: dict[Any, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    output: list[dict[str, Any]] = []
    for key, items in groups.items():
        wins = sum(r["grade"] == "win" for r in items)
        losses = sum(r["grade"] == "loss" for r in items)
        pushes = sum(r["grade"] == "push" for r in items)
        bets = len(items)
        units = round(sum(float(r["profit_units"] or 0) for r in items), 4)
        lines = [float(r["point"]) for r in items if r["point"] is not None]
        prices = [float(r["american_price"]) for r in items if r["american_price"] is not None]
        output.append({
            "key": key,
            "bets": bets,
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "win_pct": pct(wins, wins + losses),
            "units": units,
            "roi_pct": pct(units, bets),
            "avg_line": mean(lines),
            "avg_price": mean(prices),
            "confidence": confidence(bets),
        })
    return sorted(
        output,
        key=lambda x: ((x["roi_pct"] if x["roi_pct"] is not None else -math.inf), x["bets"]),
        reverse=True,
    )


def movement_summary(rows: list[dict[str, Any]], key_fn) -> dict[Any, dict[str, Any]]:
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    out: dict[Any, dict[str, Any]] = {}
    for key, items in groups.items():
        known = [r for r in items if r["beat_close"] is not None]
        out[key] = {
            "observations": len(items),
            "avg_line_move": mean(float(r["line_move"]) for r in items if r["line_move"] is not None),
            "avg_price_move": mean(float(r["price_move"]) for r in items if r["price_move"] is not None),
            "beat_close_pct": pct(sum(bool(r["beat_close"]) for r in known), len(known)),
        }
    return out


def serializable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row, key=list(row["key"]) if isinstance(row.get("key"), tuple) else row.get("key")) for row in rows]


def build(db: Path, target_date: str | None = None) -> dict[str, Any]:
    con = connect_read_only(db)
    try:
        graded = fetch_graded(con)
        moves = fetch_movements(con)
    finally:
        con.close()

    stamp = utc_now()
    by_market = summarize(graded, lambda r: str(r["market_key"]))
    by_player_market = summarize(graded, lambda r: (str(r["participant"] or "Unknown"), str(r["market_key"])))
    by_line = summarize(
        [r for r in graded if r["point"] is not None],
        lambda r: (
            str(r["participant"] or "Unknown"),
            str(r["market_key"]),
            str(r["selection"] or ""),
            float(r["point"]),
        ),
    )
    by_player_book = summarize(
        graded,
        lambda r: (str(r["participant"] or "Unknown"), str(r["market_key"]), str(r["bookmaker_key"])),
    )
    by_book_market = summarize(graded, lambda r: (str(r["bookmaker_key"]), str(r["market_key"])))
    market_moves = movement_summary(moves, lambda r: r["market"])
    book_market_moves = movement_summary(moves, lambda r: (r["sportsbook"], r["market"]))

    for row in by_market:
        row.update(market_moves.get(row["key"], {}))
        row["scope"] = market_scope(str(row["key"]))
        row["family"] = prop_family(str(row["key"]))
    for row in by_book_market:
        row.update(book_market_moves.get(row["key"], {}))

    trends: list[dict[str, Any]] = []
    for category, items in (
        ("prop_market", by_market),
        ("player_market", by_player_market),
        ("player_line", by_line),
        ("sportsbook_market", by_book_market),
    ):
        for row in items:
            if row["bets"] < 10:
                continue
            label = " | ".join(map(str, row["key"])) if isinstance(row["key"], tuple) else str(row["key"])
            trends.append({
                "trend_key": f"{category}|{label}",
                "category": category,
                "label": label,
                "sample_size": row["bets"],
                "win_pct": row["win_pct"],
                "units": row["units"],
                "roi_pct": row["roi_pct"],
                "confidence": row["confidence"],
            })
    trends.sort(
        key=lambda x: ((x["roi_pct"] if x["roi_pct"] is not None else -math.inf), x["sample_size"]),
        reverse=True,
    )

    players: dict[str, list[dict[str, Any]]] = defaultdict(list)
    player_books: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in by_player_market:
        players[row["key"][0]].append(row)
    for row in by_player_book:
        player_books[row["key"][0]].append(row)

    profiles: list[dict[str, Any]] = []
    for player, items in players.items():
        bets = sum(x["bets"] for x in items)
        wins = sum(x["wins"] for x in items)
        losses = sum(x["losses"] for x in items)
        pushes = sum(x["pushes"] for x in items)
        units = round(sum(x["units"] for x in items), 4)
        best_market_row = max(
            items,
            key=lambda x: ((x["roi_pct"] if x["roi_pct"] is not None else -math.inf), x["bets"]),
        )
        books = player_books.get(player, [])
        best_book = None
        if books:
            best_book = max(
                books,
                key=lambda x: ((x["roi_pct"] if x["roi_pct"] is not None else -math.inf), x["bets"]),
            )["key"][2]
        profiles.append({
            "player": player,
            "markets": len(items),
            "graded_bets": bets,
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "win_pct": pct(wins, wins + losses),
            "units": units,
            "roi_pct": pct(units, bets),
            "best_market": best_market_row["key"][1],
            "best_sportsbook": best_book,
        })
    profiles.sort(
        key=lambda x: ((x["roi_pct"] if x["roi_pct"] is not None else -math.inf), x["graded_bets"]),
        reverse=True,
    )

    payload = {
        "sprint": 5,
        "generated_at_utc": stamp,
        "target_date": target_date,
        "database": str(db),
        "source_only": True,
        "warehouse_mode": "read_only",
        "warehouse_mutated": False,
        "graded_prop_wagers": len(graded),
        "prop_movement_series": len(moves),
        "market_intelligence": serializable(by_market),
        "player_profiles": profiles[:250],
        "player_market_intelligence": serializable(by_player_market[:500]),
        "player_line_intelligence": serializable(by_line[:500]),
        "sportsbook_market_intelligence": serializable(by_book_market[:250]),
        "top_prop_trends": trends[:250],
        "health": {
            "consumer_only": True,
            "warehouse_read_only": True,
            "has_graded_props": bool(graded),
            "has_prop_line_movement": bool(moves),
            "markets_analyzed": len(by_market),
            "players_analyzed": len(profiles),
        },
    }
    for path in (DASHBOARD_OUT, WAREHOUSE_OUT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--date", dest="target_date", default=None)
    args = parser.parse_args()
    report = build(args.db, args.target_date)
    print(json.dumps({
        "status": "DERIVED_CONSUMER_READY",
        "target_date": report.get("target_date"),
        "graded_prop_wagers": report.get("graded_prop_wagers"),
        "prop_movement_series": report.get("prop_movement_series"),
        "warehouse_mode": report.get("warehouse_mode"),
    }, indent=2))


if __name__ == "__main__":
    main()
