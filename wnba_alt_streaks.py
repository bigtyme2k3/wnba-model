"""Build an auditable WNBA alternate-line streak board.

Exact sportsbook alternate ladders are read from the ALT market warehouse.
Standard props remain available from the daily prop feed. Sportsbook lines are
never averaged or inferred.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ALT_WAREHOUSE = Path("data/dashboard/wnba_alt_market_warehouse.json")


def load(path: str | Path, default: Any) -> Any:
    try:
        path = Path(path)
        if path.exists():
            return json.load(path.open(encoding="utf-8"))
    except Exception:
        pass
    return default


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def list_rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def parse_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    for parser in (json.loads, ast.literal_eval):
        try:
            result = parser(value)
            return result if isinstance(result, list) else []
        except Exception:
            pass
    return []


def load_csv_props(target: str) -> list[dict[str, Any]]:
    for path in (Path(f"data/raw/player_points_{target}.csv"), Path("data/raw/player_points_today.csv")):
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows = [dict(row) for row in csv.DictReader(handle)]
            if rows:
                for row in rows:
                    row["last5_vals"] = parse_array(row.get("last5_vals"))
                    row["last5_opps"] = parse_array(row.get("last5_opps"))
                    row["h2h_last5"] = parse_array(row.get("h2h_last5"))
                    row["best_over_price"] = row.get("best_over_price") or row.get("over_price")
                    row["best_under_price"] = row.get("best_under_price") or row.get("under_price")
                    row["best_over_book"] = row.get("best_over_book") or row.get("book")
                    row["best_under_book"] = row.get("best_under_book") or row.get("book")
                return rows
        except Exception:
            pass
    return []


def stat_value(game: dict[str, Any], stat: str) -> float | None:
    stat = stat.upper()
    pts = num(game.get("pts", game.get("PTS")))
    reb = num(game.get("reb", game.get("REB")))
    ast = num(game.get("ast", game.get("AST")))
    threes = num(game.get("3pm", game.get("3PM", game.get("fg3m"))))
    mapping = {
        "PTS": pts, "REB": reb, "AST": ast, "3PM": threes,
        "PRA": None if None in (pts, reb, ast) else pts + reb + ast,
        "PR": None if None in (pts, reb) else pts + reb,
        "PA": None if None in (pts, ast) else pts + ast,
        "RA": None if None in (reb, ast) else reb + ast,
    }
    return mapping.get(stat, num(game.get(stat.lower(), game.get(stat))))


def history_from_prop(prop: dict[str, Any], stat: str) -> tuple[list[float], list[str]]:
    for key in ("last10", "recent_values", "history", "game_log", "game_logs", "last5_vals"):
        value = parse_array(prop.get(key))
        if not value:
            continue
        output: list[float] = []
        for item in value:
            result = stat_value(item, stat) if isinstance(item, dict) else num(item)
            if result is not None:
                output.append(result)
        if output:
            opponents = [str(x) for x in parse_array(prop.get("last5_opps"))][:len(output)]
            return output[:10], opponents
    return [], []


def hit(value: float, line: float, side: str) -> bool:
    return value < line if side == "UNDER" else value >= line


def consecutive(values: list[float], line: float, side: str) -> int:
    count = 0
    for value in values:
        if not hit(value, line, side):
            break
        count += 1
    return count


def exact_alt_rows(target: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = load(ALT_WAREHOUSE, {})
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    markets = list_rows(payload, "rows")
    output: list[dict[str, Any]] = []
    for market in markets:
        if str(market.get("target_date") or target) != target:
            continue
        player = str(market.get("player") or "").strip()
        stat = str(market.get("stat") or "").upper()
        side = str(market.get("side") or "OVER").upper()
        line = num(market.get("threshold"))
        recent_games = market.get("recent_games") if isinstance(market.get("recent_games"), list) else []
        values = [num(g.get("value")) for g in recent_games if isinstance(g, dict)]
        values = [v for v in values if v is not None]
        if not player or not stat or line is None or len(values) < 3:
            continue
        streak = consecutive(values, line, side)
        if streak < 3:
            continue
        recent_hits = sum(hit(v, line, side) for v in values)
        season = market.get("season") if isinstance(market.get("season"), dict) else {}
        output.append(clean({
            "player": player,
            "team": market.get("team"),
            "game": market.get("game"),
            "opponent": market.get("opponent"),
            "stat": stat,
            "side": side,
            "alt_line": line,
            "line_type": "alternate",
            "streak": streak,
            "last10_hits": recent_hits,
            "last10_games": len(values),
            "last10_pct": round(recent_hits / len(values), 4),
            "season_hits": season.get("hits"),
            "season_games": season.get("games"),
            "season_pct": season.get("rate"),
            "average": round(sum(values) / len(values), 2),
            "recent_values": values,
            "recent_opponents": [g.get("opponent") for g in recent_games if isinstance(g, dict)][:len(values)],
            "opponent_rank": None,
            "opponent_label": None,
            "best_odds": market.get("odds"),
            "best_book": market.get("sportsbook"),
            "market_id": market.get("market_id"),
            "market_key": market.get("market_key"),
        }))
    return output, summary


def standard_rows(target: str) -> tuple[list[dict[str, Any]], int, int, int]:
    master = load("data/dashboard/wnba_master.json", {})
    master_props = list_rows(master, "props")
    csv_props = load_csv_props(target)
    props = csv_props or master_props
    intelligence = load("data/warehouse/wnba_player_intelligence.json", {})
    intel_map = {str(r.get("player") or "").strip().lower(): r for r in list_rows(intelligence, "players")}
    rows_out: list[dict[str, Any]] = []
    omitted_no_history = omitted_no_streak = 0
    for prop in props:
        player = str(prop.get("player") or "").strip()
        stat = str(prop.get("stat") or "").upper().replace("THREES", "3PM")
        line = num(prop.get("line", prop.get("consensus_line")))
        side = str(prop.get("signal") or prop.get("side") or "OVER").upper()
        if not player or not stat or line is None:
            continue
        values, opponents = history_from_prop(prop, stat)
        if len(values) < 3:
            omitted_no_history += 1
            continue
        streak = consecutive(values, line, side)
        if streak < 3:
            omitted_no_streak += 1
            continue
        intel = intel_map.get(player.lower(), {})
        season = intel.get("season", {}) if isinstance(intel.get("season"), dict) else {}
        season_games = int(num(season.get("gp")) or len(values))
        recent_hits = sum(hit(v, line, side) for v in values)
        season_rate = num(prop.get("last10_hit"))
        season_hits = round(season_rate * season_games) if season_rate is not None and season_games else None
        rows_out.append(clean({
            "player": player, "team": prop.get("team") or intel.get("team"), "game": prop.get("game"),
            "opponent": prop.get("opp") or prop.get("opponent"), "stat": stat, "side": side,
            "alt_line": line, "line_type": "standard", "streak": streak,
            "last10_hits": recent_hits, "last10_games": len(values), "last10_pct": round(recent_hits / len(values), 4),
            "season_hits": season_hits, "season_games": season_games,
            "season_pct": round(season_hits / season_games, 4) if season_hits is not None and season_games else None,
            "average": round(sum(values) / len(values), 2), "recent_values": values,
            "recent_opponents": opponents, "opponent_rank": num(prop.get("opp_rank")), "opponent_label": None,
            "best_odds": prop.get("best_over_price") if side == "OVER" else prop.get("best_under_price"),
            "best_book": prop.get("best_over_book") if side == "OVER" else prop.get("best_under_book"),
        }))
    return rows_out, len(props), omitted_no_history, omitted_no_streak


def build(target: str) -> dict[str, Any]:
    alt_rows, alt_summary = exact_alt_rows(target)
    std_rows, source_rows, omitted_no_history, omitted_no_streak = standard_rows(target)
    rows_out = alt_rows + std_rows
    unique: dict[tuple[str, str, str, float, str, str], dict[str, Any]] = {}
    for row in rows_out:
        key = (str(row.get("player")), str(row.get("stat")), str(row.get("side")), float(row.get("alt_line")), str(row.get("best_book") or ""), str(row.get("line_type")))
        unique[key] = row
    rows_out = list(unique.values())
    rows_out.sort(key=lambda r: (r.get("streak", 0), r.get("last10_pct", 0), r.get("season_pct") or 0), reverse=True)
    alt_count = sum(r.get("line_type") == "alternate" for r in rows_out)
    warehouse_markets = int(num(alt_summary.get("markets")) or 0)
    status = "ok"
    qa_warning = None
    if warehouse_markets > 0 and alt_count == 0:
        status = "degraded"
        qa_warning = "ALT warehouse contains markets but no active alternate streak rows met the minimum streak/history rules."
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target,
        "status": status, "source": "exact_alt_warehouse+daily_standard_props",
        "summary": {
            "source_rows": source_rows, "alt_warehouse_markets": warehouse_markets,
            "rows": len(rows_out), "players": len({r["player"] for r in rows_out}),
            "alternate_rows": alt_count, "standard_rows": sum(r.get("line_type") == "standard" for r in rows_out),
            "alternate_players": len({r["player"] for r in rows_out if r.get("line_type") == "alternate"}),
            "alternate_books": sorted({r.get("best_book") for r in rows_out if r.get("line_type") == "alternate" and r.get("best_book")}),
            "alternate_stats": sorted({r.get("stat") for r in rows_out if r.get("line_type") == "alternate" and r.get("stat")}),
            "omitted_without_real_history": omitted_no_history, "omitted_without_active_streak": omitted_no_streak,
            "minimum_streak": 3, "qa_warning": qa_warning,
        },
        "rows": rows_out,
        "data_policy": "Exact sportsbook alternate thresholds plus real recent-game history; no synthetic lines, odds, or streaks.",
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in ("data/warehouse/wnba_alt_streaks.json", "data/dashboard/wnba_alt_streaks.json"):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    print("Alt Streaks:", build(args.date)["summary"])


if __name__ == "__main__":
    main()
