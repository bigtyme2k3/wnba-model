"""Upgrade ALT Streaks from the cumulative player game-log warehouse.

The script preserves real sportsbook lines from the daily prop feed while
replacing five-game placeholders with true warehouse-derived recent and season
samples. It also supports quarter points, free-throw points, attempts, and
personal-foul markets when those lines are present.
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

import wnba_alt_streaks as base

WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")
OUTS = [Path("data/warehouse/wnba_alt_streaks.json"), Path("data/dashboard/wnba_alt_streaks.json")]


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


def parse_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def candidate_lines(prop: dict[str, Any]) -> list[dict[str, Any]]:
    """Compatibility parser for daily standard/alternate prop rows.

    The base ALT streak builder now reads exact ladders directly from the ALT
    warehouse and no longer exposes candidate_lines(). This upgrade still needs
    to parse the legacy daily prop feed, so keep that contract local.
    """
    output: list[dict[str, Any]] = []
    for key in ("alt_lines", "alternate_lines", "lines"):
        for item in parse_array(prop.get(key)):
            if not isinstance(item, dict):
                continue
            line = num(item.get("line", item.get("threshold")))
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
        output.append({
            "line": line,
            "side": side,
            "odds": prop.get("best_over_price") if side == "OVER" else prop.get("best_under_price"),
            "book": prop.get("best_over_book") if side == "OVER" else prop.get("best_under_book"),
            "line_type": "standard",
        })
    unique: dict[tuple[float, str, str, str], dict[str, Any]] = {}
    for row in output:
        unique[(row["line"], row["side"], str(row.get("book") or ""), row["line_type"])] = row
    return list(unique.values())


def load_props(target: str) -> list[dict[str, Any]]:
    for path in (Path(f"data/raw/player_points_{target}.csv"), Path("data/raw/player_points_today.csv")):
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows = [dict(row) for row in csv.DictReader(handle)]
            if rows:
                for row in rows:
                    row["best_over_price"] = row.get("best_over_price") or row.get("over_price")
                    row["best_under_price"] = row.get("best_under_price") or row.get("under_price")
                    row["best_over_book"] = row.get("best_over_book") or row.get("book")
                    row["best_under_book"] = row.get("best_under_book") or row.get("book")
                return rows
        except Exception:
            pass
    master = load(Path("data/dashboard/wnba_master.json"), {})
    return [r for r in master.get("props", []) if isinstance(r, dict)]


def stat_value(record: dict[str, Any], stat: str) -> float | None:
    stat = stat.upper().replace("THREES", "3PM").replace(" ", "_")
    scoring = record.get("scoring", {}) if isinstance(record.get("scoring"), dict) else {}
    fouls = record.get("fouls", {}) if isinstance(record.get("fouls"), dict) else {}
    box = record.get("boxscore", {}) if isinstance(record.get("boxscore"), dict) else {}
    derived = record.get("derived", {}) if isinstance(record.get("derived"), dict) else {}
    aliases = {
        "PTS": scoring.get("total_pts"),
        "Q1_PTS": scoring.get("q1_pts"), "1Q_PTS": scoring.get("q1_pts"),
        "Q2_PTS": scoring.get("q2_pts"), "2Q_PTS": scoring.get("q2_pts"),
        "Q3_PTS": scoring.get("q3_pts"), "3Q_PTS": scoring.get("q3_pts"),
        "Q4_PTS": scoring.get("q4_pts"), "4Q_PTS": scoring.get("q4_pts"),
        "1H_PTS": scoring.get("first_half_pts"), "FIRST_HALF_PTS": scoring.get("first_half_pts"),
        "2H_PTS": scoring.get("second_half_pts"), "SECOND_HALF_PTS": scoring.get("second_half_pts"),
        "FTM": scoring.get("ftm"), "FT_PTS": scoring.get("free_throw_points"), "FREE_THROW_POINTS": scoring.get("free_throw_points"),
        "FTA": scoring.get("fta"), "3PM": scoring.get("three_pm"),
        "REB": box.get("reb"), "OREB": box.get("oreb"), "DREB": box.get("dreb"),
        "AST": box.get("ast"), "STL": box.get("stl"), "BLK": box.get("blk"), "TOV": box.get("tov"),
        "PF": fouls.get("total_committed"), "FOULS": fouls.get("total_committed"),
        "SHOOTING_FOULS": fouls.get("shooting"), "OFFENSIVE_FOULS": fouls.get("offensive"),
        "TECHNICAL_FOULS": fouls.get("technical"), "FLAGRANT_FOULS": fouls.get("flagrant"),
        "PRA": derived.get("pra"), "PR": derived.get("pr"), "PA": derived.get("pa"), "RA": derived.get("ra"),
    }
    return num(aliases.get(stat))


def sort_key(record: dict[str, Any]) -> tuple[str, str]:
    return str(record.get("game_date") or ""), str(record.get("game") or "")


def hit(value: float, line: float, side: str) -> bool:
    return value < line if side == "UNDER" else value > line


def streak(values: list[float], line: float, side: str) -> int:
    count = 0
    for value in values:
        if not hit(value, line, side):
            break
        count += 1
    return count


def record_quality_ok(record: dict[str, Any], stat: str) -> bool:
    stat_key = stat.upper().replace(" ", "_")
    if stat_key in {"Q1_PTS", "1Q_PTS", "Q2_PTS", "2Q_PTS", "Q3_PTS", "3Q_PTS", "Q4_PTS", "4Q_PTS", "1H_PTS", "2H_PTS", "FIRST_HALF_PTS", "SECOND_HALF_PTS"}:
        return record.get("data_quality", {}).get("quarter_data_status") == "complete"
    return True


def build(target: str) -> dict[str, Any]:
    payload = load(WAREHOUSE, {"records": []})
    records = [r for r in payload.get("records", []) if isinstance(r, dict)]
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("player"):
            by_player[norm(record.get("player"))].append(record)
    for player_records in by_player.values():
        player_records.sort(key=sort_key, reverse=True)

    props = load_props(target)
    output: list[dict[str, Any]] = []
    missing_player_history = 0
    insufficient_samples = 0
    no_active_streak = 0

    for prop in props:
        player = str(prop.get("player") or "").strip()
        stat = str(prop.get("stat") or "").upper().replace("THREES", "3PM")
        if not player or not stat:
            continue
        history = [r for r in by_player.get(norm(player), []) if record_quality_ok(r, stat)]
        if not history:
            missing_player_history += 1
            continue
        values: list[float] = []
        opponents: list[str] = []
        dates: list[str] = []
        for record in history:
            value = stat_value(record, stat)
            if value is None:
                continue
            values.append(value)
            opponents.append(str(record.get("opponent") or ""))
            dates.append(str(record.get("game_date") or ""))
        if len(values) < 3:
            insufficient_samples += 1
            continue
        produced = False
        for market in candidate_lines(prop):
            line = num(market.get("line"))
            if line is None:
                continue
            side = str(market.get("side") or "OVER").upper()
            current = streak(values, line, side)
            if current < 3:
                continue
            produced = True
            l5 = values[:5]
            l10 = values[:10]
            season = values
            l5_hits = sum(hit(v, line, side) for v in l5)
            l10_hits = sum(hit(v, line, side) for v in l10)
            season_hits = sum(hit(v, line, side) for v in season)
            output.append({
                "player": player,
                "team": None if str(prop.get("team") or "").lower() == "nan" else prop.get("team"),
                "game": prop.get("game"),
                "opponent": prop.get("opp") or prop.get("opponent"),
                "stat": stat,
                "side": side,
                "alt_line": line,
                "line_type": market.get("line_type"),
                "streak": current,
                "l5_hits": l5_hits, "l5_games": len(l5), "l5_pct": round(l5_hits / len(l5), 4),
                "l10_hits": l10_hits, "l10_games": len(l10), "l10_pct": round(l10_hits / len(l10), 4),
                "season_hits": season_hits, "season_games": len(season), "season_pct": round(season_hits / len(season), 4),
                "average": round(sum(season) / len(season), 2),
                "l5_average": round(sum(l5) / len(l5), 2),
                "l10_average": round(sum(l10) / len(l10), 2),
                "recent_values": l10,
                "recent_opponents": opponents[:10],
                "recent_dates": dates[:10],
                "opponent_rank": None,
                "opponent_label": None,
                "best_odds": market.get("odds"),
                "best_book": market.get("book"),
                "history_source": "player_game_log_warehouse",
                "quarter_data_required": stat.replace(" ", "_") in {"Q1_PTS","1Q_PTS","Q2_PTS","2Q_PTS","Q3_PTS","3Q_PTS","Q4_PTS","4Q_PTS","1H_PTS","2H_PTS"},
            })
        if not produced:
            no_active_streak += 1

    output.sort(key=lambda r: (r["streak"], r["l10_pct"], r["season_pct"]), reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "source": "player_game_log_warehouse+daily_prop_market",
        "summary": {
            "warehouse_records": len(records),
            "warehouse_players": len(by_player),
            "source_props": len(props),
            "rows": len(output),
            "players": len({r["player"] for r in output}),
            "alternate_rows": sum(r.get("line_type") == "alternate" for r in output),
            "standard_rows": sum(r.get("line_type") == "standard" for r in output),
            "missing_player_history": missing_player_history,
            "insufficient_samples": insufficient_samples,
            "without_active_streak": no_active_streak,
            "minimum_streak": 3,
        },
        "rows": output,
        "supported_history_stats": [
            "PTS","Q1 PTS","Q2 PTS","Q3 PTS","Q4 PTS","1H PTS","2H PTS",
            "FTM","FTA","FT PTS","3PM","REB","OREB","DREB","AST","STL","BLK","TOV",
            "PF","SHOOTING FOULS","OFFENSIVE FOULS","TECHNICAL FOULS","FLAGRANT FOULS","PRA","PR","PA","RA"
        ],
        "data_policy": "L5, L10, and season records come only from cumulative verified player game logs. Opponent rank remains blank until a documented stat-specific defense model is available.",
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    print("ALT Streaks warehouse upgrade:", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
