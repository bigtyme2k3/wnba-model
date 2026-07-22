"""Sprint 5.5: match verified player game logs to Odds Warehouse V2 props.

The bridge never invents results. It matches a warehouse event to a player-game
record by date and both teams, then matches the wager participant to the player.
Supported full-game markets are graded into the canonical ``grades`` table so
Sprint 5 can consume them without a parallel analytics path.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
PLAYER_LOGS = Path("data/warehouse/wnba_player_game_logs.json")
REPORT = Path("data/warehouse/wnba_player_prop_grading_bridge.json")
DASHBOARD_REPORT = Path("data/dashboard/wnba_player_prop_grading_bridge.json")

STAT_MARKETS = {
    "player_points": "points",
    "player_rebounds": "rebounds",
    "player_assists": "assists",
    "player_threes": "threes",
    "player_three_pointers": "threes",
    "player_three_points_made": "threes",
    "player_blocks": "blocks",
    "player_steals": "steals",
    "player_turnovers": "turnovers",
    "player_points_rebounds_assists": "pra",
    "player_points_rebounds": "pr",
    "player_points_assists": "pa",
    "player_rebounds_assists": "ra",
}

TEAM_ALIASES = {
    "atlanta dream": "atlanta", "chicago sky": "chicago", "connecticut sun": "connecticut",
    "dallas wings": "dallas", "golden state valkyries": "goldenstate", "indiana fever": "indiana",
    "las vegas aces": "lasvegas", "los angeles sparks": "losangeles", "minnesota lynx": "minnesota",
    "new york liberty": "newyork", "phoenix mercury": "phoenix", "seattle storm": "seattle",
    "washington mystics": "washington",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def team_key(value: Any) -> str:
    raw = " ".join(str(value or "").lower().replace(".", " ").split())
    for label, key in TEAM_ALIASES.items():
        if label in raw or norm(label) == norm(raw):
            return key
    return norm(raw)


def date_key(value: Any) -> str:
    text = str(value or "")
    return text[:10] if len(text) >= 10 else text


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return [x for x in raw.get("records", []) if isinstance(x, dict)] if isinstance(raw, dict) else []


def actuals(record: dict[str, Any]) -> dict[str, float | None]:
    scoring = record.get("scoring") or {}
    box = record.get("boxscore") or {}
    derived = record.get("derived") or {}
    pts = number(scoring.get("total_pts"))
    reb = number(box.get("reb"))
    ast = number(box.get("ast"))
    return {
        "points": pts,
        "rebounds": reb,
        "assists": ast,
        "threes": number(scoring.get("three_pm")),
        "blocks": number(box.get("blk")),
        "steals": number(box.get("stl")),
        "turnovers": number(box.get("tov")),
        "pra": number(derived.get("pra")) if number(derived.get("pra")) is not None else (pts + reb + ast if None not in (pts, reb, ast) else None),
        "pr": number(derived.get("pr")) if number(derived.get("pr")) is not None else (pts + reb if None not in (pts, reb) else None),
        "pa": number(derived.get("pa")) if number(derived.get("pa")) is not None else (pts + ast if None not in (pts, ast) else None),
        "ra": number(derived.get("ra")) if number(derived.get("ra")) is not None else (reb + ast if None not in (reb, ast) else None),
    }


def market_stat(market: str) -> str | None:
    key = market.lower()
    for prefix in ("alternate_", "alt_"):
        if key.startswith(prefix):
            key = key[len(prefix):]
    # Quarter props require period data and are intentionally excluded here.
    if any(token in key for token in ("1q", "q1", "quarter", "first_half", "1h")):
        return None
    if key in STAT_MARKETS:
        return STAT_MARKETS[key]
    for market_key, stat in sorted(STAT_MARKETS.items(), key=lambda x: len(x[0]), reverse=True):
        if market_key in key:
            return stat
    return None


def selection_side(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"over", "under"}:
        return text
    if text.startswith("over "):
        return "over"
    if text.startswith("under "):
        return "under"
    return None


def profit(price: int | None, grade: str) -> float:
    if grade == "push":
        return 0.0
    if grade != "win":
        return -1.0
    if not price:
        return 1.0
    return round(price / 100.0 if price > 0 else 100.0 / abs(price), 6)


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS player_game_stats(
      event_id TEXT NOT NULL,
      player_key TEXT NOT NULL,
      player TEXT NOT NULL,
      team TEXT,
      opponent TEXT,
      game_date TEXT,
      points REAL, rebounds REAL, assists REAL, threes REAL,
      blocks REAL, steals REAL, turnovers REAL,
      pra REAL, pr REAL, pa REAL, ra REAL,
      source TEXT NOT NULL,
      imported_at_utc TEXT NOT NULL,
      PRIMARY KEY(event_id, player_key)
    );
    CREATE TABLE IF NOT EXISTS player_prop_grades(
      wager_id TEXT PRIMARY KEY,
      event_id TEXT NOT NULL,
      player TEXT NOT NULL,
      market_key TEXT NOT NULL,
      selection TEXT NOT NULL,
      line REAL NOT NULL,
      actual_stat REAL NOT NULL,
      grade TEXT NOT NULL,
      profit_units REAL NOT NULL,
      source TEXT NOT NULL,
      graded_at_utc TEXT NOT NULL
    );
    """)


def build_index(records: list[dict[str, Any]]) -> dict[tuple[str, frozenset[str]], list[dict[str, Any]]]:
    index: dict[tuple[str, frozenset[str]], list[dict[str, Any]]] = {}
    for record in records:
        day = date_key(record.get("game_date"))
        team = team_key(record.get("team"))
        opponent = team_key(record.get("opponent"))
        player = record.get("player")
        if not (day and team and opponent and player):
            continue
        index.setdefault((day, frozenset((team, opponent))), []).append(record)
    return index


def run(db: Path, logs: Path) -> dict[str, Any]:
    if not db.exists():
        raise SystemExit(f"Warehouse not found: {db}")
    records = load_records(logs)
    index = build_index(records)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    ensure_schema(con)
    stamp = now()

    events = con.execute("SELECT event_id,home_team,away_team,game_date_utc,commence_time_utc FROM events").fetchall()
    event_records: dict[str, list[dict[str, Any]]] = {}
    matched_events = 0
    for event in events:
        day = date_key(event["game_date_utc"] or event["commence_time_utc"])
        key = (day, frozenset((team_key(event["home_team"]), team_key(event["away_team"]))))
        candidates = index.get(key, [])
        if candidates:
            event_records[event["event_id"]] = candidates
            matched_events += 1
            for record in candidates:
                stats = actuals(record)
                con.execute("""INSERT INTO player_game_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(event_id,player_key) DO UPDATE SET
                  player=excluded.player,team=excluded.team,opponent=excluded.opponent,game_date=excluded.game_date,
                  points=excluded.points,rebounds=excluded.rebounds,assists=excluded.assists,threes=excluded.threes,
                  blocks=excluded.blocks,steals=excluded.steals,turnovers=excluded.turnovers,pra=excluded.pra,
                  pr=excluded.pr,pa=excluded.pa,ra=excluded.ra,source=excluded.source,imported_at_utc=excluded.imported_at_utc""",
                  (event["event_id"], norm(record.get("player")), str(record.get("player")), record.get("team"), record.get("opponent"),
                   date_key(record.get("game_date")), stats["points"], stats["rebounds"], stats["assists"], stats["threes"],
                   stats["blocks"], stats["steals"], stats["turnovers"], stats["pra"], stats["pr"], stats["pa"], stats["ra"],
                   "verified_player_game_logs", stamp))

    wagers = con.execute("""SELECT wager_id,event_id,market_key,participant,selection,point,american_price
                             FROM wagers WHERE participant IS NOT NULL AND point IS NOT NULL""").fetchall()
    counts = {"candidate_prop_wagers": 0, "graded": 0, "unmatched_event": 0, "unmatched_player": 0,
              "unsupported_market": 0, "missing_actual": 0, "invalid_side": 0}
    for wager in wagers:
        stat = market_stat(str(wager["market_key"] or ""))
        if stat is None:
            if "player" in str(wager["market_key"] or "").lower():
                counts["unsupported_market"] += 1
            continue
        counts["candidate_prop_wagers"] += 1
        side = selection_side(wager["selection"])
        if side is None:
            counts["invalid_side"] += 1
            continue
        candidates = event_records.get(wager["event_id"])
        if not candidates:
            counts["unmatched_event"] += 1
            continue
        target = norm(wager["participant"])
        record = next((r for r in candidates if norm(r.get("player")) == target), None)
        if record is None:
            # Safe fallback for Odds API suffixes/initial punctuation; require unique containment.
            possible = [r for r in candidates if target and (target in norm(r.get("player")) or norm(r.get("player")) in target)]
            record = possible[0] if len(possible) == 1 else None
        if record is None:
            counts["unmatched_player"] += 1
            continue
        actual = actuals(record).get(stat)
        line = number(wager["point"])
        if actual is None or line is None:
            counts["missing_actual"] += 1
            continue
        grade = "push" if actual == line else "win" if (actual > line if side == "over" else actual < line) else "loss"
        units = profit(wager["american_price"], grade)
        con.execute("""INSERT INTO grades(wager_id,actual_result,grade,profit_units,graded_at_utc,grading_source,notes)
          VALUES(?,?,?,?,?,?,?) ON CONFLICT(wager_id) DO UPDATE SET actual_result=excluded.actual_result,
          grade=excluded.grade,profit_units=excluded.profit_units,graded_at_utc=excluded.graded_at_utc,
          grading_source=excluded.grading_source,notes=excluded.notes""",
          (wager["wager_id"], actual, grade, units, stamp, "player_prop_grading_bridge", f"{stat} verified player box score"))
        con.execute("""INSERT INTO player_prop_grades VALUES(?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(wager_id) DO UPDATE SET actual_stat=excluded.actual_stat,grade=excluded.grade,
          profit_units=excluded.profit_units,source=excluded.source,graded_at_utc=excluded.graded_at_utc""",
          (wager["wager_id"], wager["event_id"], str(record.get("player")), wager["market_key"], side,
           line, actual, grade, units, "verified_player_game_logs", stamp))
        counts["graded"] += 1

    con.commit()
    report = {
        "generated_at_utc": stamp, "database": str(db), "player_log_records": len(records),
        "events_in_warehouse": len(events), "events_matched_to_player_logs": matched_events,
        **counts,
        "player_game_stats_rows": con.execute("SELECT COUNT(*) FROM player_game_stats").fetchone()[0],
        "player_prop_grade_rows": con.execute("SELECT COUNT(*) FROM player_prop_grades").fetchone()[0],
        "health": {
            "schema_created": True,
            "has_player_logs": bool(records),
            "has_candidate_prop_wagers": counts["candidate_prop_wagers"] > 0,
            "has_graded_props": counts["graded"] > 0,
        },
    }
    for path in (REPORT, DASHBOARD_REPORT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--player-logs", type=Path, default=PLAYER_LOGS)
    args = parser.parse_args()
    run(args.db, args.player_logs)


if __name__ == "__main__":
    main()
