"""Build an auditable WNBA alternate-line streak board.

Only real historical arrays and real sportsbook lines are used. The module does
not fabricate game logs, alternate lines, odds, or opponent rankings. Rows with
insufficient history are omitted and summarized in the output metadata.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def load(path: str, default: Any) -> Any:
    try:
        if Path(path).exists():
            return json.load(open(path, encoding="utf-8"))
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
    try:
        if hasattr(value, "item"):
            return clean(value.item())
    except Exception:
        pass
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


def stat_value(game: dict[str, Any], stat: str) -> float | None:
    stat = stat.upper()
    pts = num(game.get("pts", game.get("PTS")))
    reb = num(game.get("reb", game.get("REB")))
    ast = num(game.get("ast", game.get("AST")))
    threes = num(game.get("3pm", game.get("3PM", game.get("fg3m"))))
    steals = num(game.get("stl", game.get("STL")))
    blocks = num(game.get("blk", game.get("BLK")))
    mapping = {
        "PTS": pts, "REB": reb, "AST": ast, "3PM": threes,
        "STL": steals, "BLK": blocks,
        "PRA": None if None in (pts, reb, ast) else pts + reb + ast,
        "PR": None if None in (pts, reb) else pts + reb,
        "PA": None if None in (pts, ast) else pts + ast,
        "RA": None if None in (reb, ast) else reb + ast,
    }
    direct = num(game.get(stat.lower(), game.get(stat)))
    return mapping.get(stat, direct)


def history_from_prop(prop: dict[str, Any], stat: str) -> list[float]:
    for key in ("last10", "recent_values", "history", "game_log", "game_logs"):
        value = prop.get(key)
        if not isinstance(value, list):
            continue
        output: list[float] = []
        for item in value:
            result = stat_value(item, stat) if isinstance(item, dict) else num(item)
            if result is not None:
                output.append(result)
        if output:
            return output[:10]
    return []


def candidate_lines(prop: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for key in ("alt_lines", "alternate_lines", "lines"):
        value = prop.get(key)
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                line = num(item.get("line"))
                if line is None:
                    continue
                output.append({
                    "line": line,
                    "side": str(item.get("side") or item.get("signal") or "OVER").upper(),
                    "odds": item.get("odds") or item.get("price"),
                    "book": item.get("book") or item.get("sportsbook"),
                    "line_type": "alternate",
                })
    line = num(prop.get("line", prop.get("consensus_line")))
    if line is not None:
        side = str(prop.get("signal") or prop.get("side") or "OVER").upper()
        odds = prop.get("best_over_price") if side == "OVER" else prop.get("best_under_price")
        output.append({"line": line, "side": side, "odds": odds, "book": prop.get("best_over_book") if side == "OVER" else prop.get("best_under_book"), "line_type": "standard"})
    unique: dict[tuple[float, str, str], dict[str, Any]] = {}
    for row in output:
        unique[(row["line"], row["side"], str(row.get("book") or ""))] = row
    return list(unique.values())


def hit(value: float, line: float, side: str) -> bool:
    return value < line if side == "UNDER" else value > line


def consecutive(values: list[float], line: float, side: str) -> int:
    count = 0
    for value in values:
        if hit(value, line, side):
            count += 1
        else:
            break
    return count


def build(target: str) -> dict[str, Any]:
    master = load("data/dashboard/wnba_master.json", {})
    props = list_rows(master, "props")
    intelligence = load("data/warehouse/wnba_player_intelligence.json", {})
    intel_map = {str(r.get("player") or "").strip().lower(): r for r in list_rows(intelligence, "players")}
    rows_out: list[dict[str, Any]] = []
    omitted_no_history = 0

    for prop in props:
        player = str(prop.get("player") or "").strip()
        stat = str(prop.get("stat") or "").upper().replace("THREES", "3PM")
        if not player or not stat:
            continue
        values = history_from_prop(prop, stat)
        if len(values) < 3:
            omitted_no_history += 1
            continue
        intel = intel_map.get(player.lower(), {})
        season = intel.get("season", {}) if isinstance(intel.get("season"), dict) else {}
        season_avg = {
            "PTS": season.get("ppg"), "REB": season.get("reb"), "AST": season.get("ast")
        }.get(stat, prop.get("season_avg"))
        season_games = int(num(season.get("gp")) or len(values))
        for market in candidate_lines(prop):
            line = market["line"]
            side = market["side"]
            streak = consecutive(values, line, side)
            if streak < 3:
                continue
            l10_hits = sum(hit(v, line, side) for v in values[:10])
            season_hits = prop.get("season_hits")
            if not isinstance(season_hits, int):
                season_hits = None
            rows_out.append(clean({
                "player": player,
                "team": prop.get("team") or intel.get("team"),
                "game": prop.get("game"),
                "opponent": prop.get("opponent") or prop.get("opp"),
                "stat": stat,
                "side": side,
                "alt_line": line,
                "line_type": market.get("line_type"),
                "streak": streak,
                "last10_hits": l10_hits,
                "last10_games": min(10, len(values)),
                "last10_pct": round(l10_hits / min(10, len(values)), 4),
                "season_hits": season_hits,
                "season_games": season_games,
                "season_pct": round(season_hits / season_games, 4) if season_hits is not None and season_games else None,
                "average": round(sum(values[:10]) / min(10, len(values)), 2),
                "recent_values": values[:10],
                "opponent_rank": prop.get("opponent_rank") or prop.get("opp_rank"),
                "opponent_label": prop.get("opponent_label"),
                "best_odds": market.get("odds"),
                "best_book": market.get("book"),
            }))

    rows_out.sort(key=lambda r: (r.get("streak", 0), r.get("last10_pct", 0), r.get("season_pct") or 0), reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "summary": {
            "rows": len(rows_out),
            "players": len({r["player"] for r in rows_out}),
            "alternate_rows": sum(r.get("line_type") == "alternate" for r in rows_out),
            "standard_rows": sum(r.get("line_type") == "standard" for r in rows_out),
            "omitted_without_real_history": omitted_no_history,
            "minimum_streak": 3,
        },
        "rows": rows_out,
        "data_policy": "Real historical arrays and supplied sportsbook lines only; no synthetic streaks, odds, or rankings.",
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
