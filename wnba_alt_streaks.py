"""Build an auditable WNBA alternate-line streak board.

Uses verified recent-game arrays and supplied sportsbook lines. It never
fabricates game logs, alternate lines, odds, or opponent rankings.
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
                    if not row.get("best_over_price"):
                        row["best_over_price"] = row.get("over_price")
                    if not row.get("best_under_price"):
                        row["best_under_price"] = row.get("under_price")
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


def candidate_lines(prop: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for key in ("alt_lines", "alternate_lines", "lines"):
        for item in parse_array(prop.get(key)):
            if not isinstance(item, dict):
                continue
            line = num(item.get("line"))
            if line is not None:
                output.append({"line": line, "side": str(item.get("side") or item.get("signal") or "OVER").upper(), "odds": item.get("odds") or item.get("price"), "book": item.get("book") or item.get("sportsbook"), "line_type": "alternate"})
    line = num(prop.get("line", prop.get("consensus_line")))
    if line is not None:
        side = str(prop.get("signal") or prop.get("side") or "OVER").upper()
        output.append({"line": line, "side": side, "odds": prop.get("best_over_price") if side == "OVER" else prop.get("best_under_price"), "book": prop.get("best_over_book") if side == "OVER" else prop.get("best_under_book"), "line_type": "standard"})
    unique: dict[tuple[float, str, str], dict[str, Any]] = {}
    for row in output:
        unique[(row["line"], row["side"], str(row.get("book") or ""))] = row
    return list(unique.values())


def hit(value: float, line: float, side: str) -> bool:
    return value < line if side == "UNDER" else value > line


def consecutive(values: list[float], line: float, side: str) -> int:
    count = 0
    for value in values:
        if not hit(value, line, side):
            break
        count += 1
    return count


def build(target: str) -> dict[str, Any]:
    master = load("data/dashboard/wnba_master.json", {})
    master_props = list_rows(master, "props")
    csv_props = load_csv_props(target)
    props = csv_props or master_props
    source = "player_points_csv" if csv_props else "wnba_master"
    intelligence = load("data/warehouse/wnba_player_intelligence.json", {})
    intel_map = {str(r.get("player") or "").strip().lower(): r for r in list_rows(intelligence, "players")}
    rows_out: list[dict[str, Any]] = []
    omitted_no_history = 0
    omitted_no_streak = 0

    for prop in props:
        player = str(prop.get("player") or "").strip()
        stat = str(prop.get("stat") or "").upper().replace("THREES", "3PM")
        if not player or not stat:
            continue
        values, opponents = history_from_prop(prop, stat)
        if len(values) < 3:
            omitted_no_history += 1
            continue
        intel = intel_map.get(player.lower(), {})
        season = intel.get("season", {}) if isinstance(intel.get("season"), dict) else {}
        season_games = int(num(season.get("gp")) or len(values))
        produced = False
        for market in candidate_lines(prop):
            line, side = market["line"], market["side"]
            streak = consecutive(values, line, side)
            if streak < 3:
                continue
            produced = True
            recent_hits = sum(hit(v, line, side) for v in values)
            season_rate = num(prop.get("last10_hit"))
            season_hits = round(season_rate * season_games) if season_rate is not None and season_games else None
            rows_out.append(clean({
                "player": player,
                "team": prop.get("team") if str(prop.get("team") or "").lower() != "nan" else intel.get("team"),
                "game": prop.get("game"),
                "opponent": prop.get("opp") or prop.get("opponent"),
                "stat": stat,
                "side": side,
                "alt_line": line,
                "line_type": market.get("line_type"),
                "streak": streak,
                "last10_hits": recent_hits,
                "last10_games": len(values),
                "last10_pct": round(recent_hits / len(values), 4),
                "season_hits": season_hits,
                "season_games": season_games,
                "season_pct": round(season_hits / season_games, 4) if season_hits is not None and season_games else None,
                "average": round(sum(values) / len(values), 2),
                "recent_values": values,
                "recent_opponents": opponents,
                "opponent_rank": num(prop.get("opp_rank")),
                "opponent_label": None,
                "best_odds": market.get("odds"),
                "best_book": market.get("book"),
            }))
        if not produced:
            omitted_no_streak += 1

    rows_out.sort(key=lambda r: (r.get("streak", 0), r.get("last10_pct", 0), r.get("season_pct") or 0), reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "source": source,
        "summary": {
            "source_rows": len(props),
            "rows": len(rows_out),
            "players": len({r["player"] for r in rows_out}),
            "alternate_rows": sum(r.get("line_type") == "alternate" for r in rows_out),
            "standard_rows": sum(r.get("line_type") == "standard" for r in rows_out),
            "omitted_without_real_history": omitted_no_history,
            "omitted_without_active_streak": omitted_no_streak,
            "minimum_streak": 3,
        },
        "rows": rows_out,
        "data_policy": "Real recent-game arrays and supplied sportsbook lines only; no synthetic streaks, odds, or rankings.",
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
