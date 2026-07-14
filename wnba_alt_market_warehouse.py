"""Build a sportsbook-specific WNBA alternate-prop ladder warehouse.

Input is the bookmaker-level CSV written by scrape_odds_props.py. Every
sportsbook/player/stat/threshold remains a distinct market; lines are never
averaged across books. Historical hit rates come from the canonical player game
log warehouse and are calculated against the exact threshold.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

RAW = Path("data/raw")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
OUTS = [Path("data/warehouse/wnba_alt_market_warehouse.json"), Path("data/dashboard/wnba_alt_market_warehouse.json")]
SUPPORTED = {"PTS", "REB", "AST", "3PM", "PRA", "PR", "PA", "RA", "STL", "BLK"}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def american_decimal(odds: Any) -> float | None:
    value = num(odds)
    if value is None or value == 0:
        return None
    return 1 + 100 / -value if value < 0 else 1 + value / 100


def implied_probability(odds: Any) -> float | None:
    decimal = american_decimal(odds)
    return None if decimal is None else 1 / decimal


def stat_value(record: dict[str, Any], stat: str) -> float | None:
    scoring = record.get("scoring") or {}
    box = record.get("boxscore") or {}
    derived = record.get("derived") or {}
    values = {
        "PTS": scoring.get("total_pts"), "REB": box.get("reb"), "AST": box.get("ast"),
        "3PM": scoring.get("three_pm"), "STL": box.get("stl"), "BLK": box.get("blk"),
        "PRA": derived.get("pra"), "PR": derived.get("pr"), "PA": derived.get("pa"), "RA": derived.get("ra"),
    }
    return num(values.get(stat))


def history_index() -> dict[str, list[dict[str, Any]]]:
    payload = load(LOGS, {"records": []})
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("records", []):
        if not isinstance(row, dict) or row.get("did_not_play") is True:
            continue
        if (num(row.get("minutes")) or 0) <= 0:
            continue
        groups[norm(row.get("player"))].append(row)
    for rows in groups.values():
        rows.sort(key=lambda r: (str(r.get("game_date") or ""), str(r.get("game_id") or r.get("game") or "")), reverse=True)
    return groups


def hit_summary(records: list[dict[str, Any]], stat: str, threshold: float) -> dict[str, Any]:
    values: list[float] = []
    games: list[dict[str, Any]] = []
    for record in records:
        value = stat_value(record, stat)
        if value is None:
            continue
        values.append(value)
        games.append({"date": record.get("game_date"), "opponent": record.get("opponent"), "value": value, "hit": value >= threshold})
    def window(size: int) -> dict[str, Any]:
        sample = values[:size]
        hits = sum(value >= threshold for value in sample)
        return {"hits": hits, "games": len(sample), "rate": round(hits / len(sample), 4) if sample else None}
    season_hits = sum(value >= threshold for value in values)
    streak = 0
    for value in values:
        if value >= threshold:
            streak += 1
        else:
            break
    return {
        "l5": window(5), "l10": window(10),
        "season": {"hits": season_hits, "games": len(values), "rate": round(season_hits / len(values), 4) if values else None},
        "current_hit_streak": streak, "recent_games": games[:10], "history_games_available": len(values),
    }


def input_path(target: str) -> Path:
    dated = RAW / f"alt_props_bookmakers_{target}.csv"
    return dated if dated.exists() else RAW / "alt_props_bookmakers_today.csv"


def read_markets(target: str) -> list[dict[str, Any]]:
    path = input_path(target)
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def build(target: str) -> dict[str, Any]:
    raw = read_markets(target)
    histories = history_index()
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for source in raw:
        stat = str(source.get("stat") or "").upper()
        side = str(source.get("side") or "").upper()
        threshold = num(source.get("threshold") or source.get("line"))
        odds = num(source.get("odds") or source.get("price"))
        player = str(source.get("player") or "").strip()
        sportsbook = str(source.get("sportsbook") or source.get("book") or "").strip()
        if stat not in SUPPORTED or side not in {"OVER", "UNDER"} or threshold is None or odds is None or not player or not sportsbook:
            continue
        key = (str(source.get("event_id") or ""), norm(player), stat, side, str(threshold), norm(sportsbook))
        if key in seen:
            continue
        seen.add(key)
        history = hit_summary(histories.get(norm(player), []), stat, threshold)
        probability = history["l10"]["rate"] if history["l10"]["games"] >= 5 else history["season"]["rate"]
        if side == "UNDER" and probability is not None:
            pushes = sum(game["value"] == threshold for game in history["recent_games"])
            probability = max(0, min(1, 1 - probability - pushes / max(1, len(history["recent_games"]))))
        decimal = american_decimal(odds)
        ev = probability * decimal - 1 if probability is not None and decimal is not None else None
        rows.append({
            "market_id": "|".join(key), "target_date": target, "event_id": source.get("event_id"),
            "game": source.get("game") or f"{source.get('away_team','')} @ {source.get('home_team','')}",
            "game_time": source.get("game_time"), "player": player, "team": source.get("team"),
            "stat": stat, "side": side, "threshold": threshold, "display_threshold": f"{threshold:g}+" if side == "OVER" else f"Under {threshold:g}",
            "odds": odds, "sportsbook": sportsbook, "sportsbook_key": source.get("sportsbook_key"),
            "market_key": source.get("market_key"), "market_type": "alternate",
            "scraped_at_utc": source.get("scraped_at"), "implied_probability": round(implied_probability(odds), 4) if implied_probability(odds) is not None else None,
            "historical_probability": round(probability, 4) if probability is not None else None,
            "expected_value_per_unit": round(ev, 4) if ev is not None else None,
            **history,
        })
    rows.sort(key=lambda r: (norm(r["player"]), r["stat"], norm(r["sportsbook"]), r["threshold"], r["side"]))
    ladders: dict[str, Any] = {}
    for row in rows:
        player = ladders.setdefault(row["player"], {"player": row["player"], "game": row["game"], "stats": {}})
        stat = player["stats"].setdefault(row["stat"], {"stat": row["stat"], "sportsbooks": {}})
        book = stat["sportsbooks"].setdefault(row["sportsbook"], {"sportsbook": row["sportsbook"], "lines": []})
        book["lines"].append(row)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target,
        "status": "ok" if rows else "empty", "summary": {
            "raw_rows": len(raw), "markets": len(rows), "players": len(ladders),
            "sportsbooks": sorted({r["sportsbook"] for r in rows}),
            "stats": sorted({r["stat"] for r in rows}),
            "book_player_stat_groups": len({(r["sportsbook"], r["player"], r["stat"]) for r in rows}),
        },
        "rows": rows, "players": list(ladders.values()),
        "data_contract": {
            "book_specific_lines_preserved": True, "cross_book_line_averaging": False,
            "threshold_rule": "exact sportsbook outcome point", "dd_td_supported": False,
            "history_source": str(LOGS), "future_markets": ["PLAYER_1Q_POINTS", "PLAYER_FIRST_3_MIN_POINTS"],
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(payload, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print("ALT market warehouse:", payload["summary"])
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
