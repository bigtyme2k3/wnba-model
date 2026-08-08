"""Reconstruct current-slate ALT scoring rows from the canonical props feed.

This is a safety/fallback bridge for deployments where the exact alternate-market
API feed is unavailable. It intentionally mirrors the ALT table's ladder rule:
player/game/stat groups with at least two distinct current lines are treated as
an alternate ladder. Each visible line is evaluated against verified player game
logs and written as line_type=alternate so the score renderer and table share the
same player/stat/side/line keys.

Exact sportsbook alternate rows remain authoritative when they exist; this file
only fills the alternate set when the current streak source has zero exact ALT
rows.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PROPS = Path("data/dashboard/wnba_player_props.json")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
OUTS = [Path("data/dashboard/wnba_alt_streaks.json"), Path("data/warehouse/wnba_alt_streaks.json")]
MIN_HISTORY = 3


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
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


def stat_value(record: dict[str, Any], stat: str) -> float | None:
    scoring = record.get("scoring") or {}
    box = record.get("boxscore") or {}
    derived = record.get("derived") or {}
    stat = stat.upper()
    values = {
        "PTS": scoring.get("total_pts"),
        "REB": box.get("reb"),
        "AST": box.get("ast"),
        "3PM": scoring.get("three_pm"),
        "STL": box.get("stl"),
        "BLK": box.get("blk"),
        "PRA": derived.get("pra"),
        "PR": derived.get("pr"),
        "PA": derived.get("pa"),
        "RA": derived.get("ra"),
    }
    return num(values.get(stat))


def history_index() -> dict[str, list[dict[str, Any]]]:
    payload = load(LOGS, {"records": []})
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("records", []) if isinstance(payload, dict) else []:
        if not isinstance(row, dict) or row.get("did_not_play") is True:
            continue
        if (num(row.get("minutes")) or 0) <= 0:
            continue
        groups[norm(row.get("player"))].append(row)
    for rows in groups.values():
        rows.sort(key=lambda r: (str(r.get("game_date") or ""), str(r.get("game_id") or r.get("game") or "")), reverse=True)
    return groups


def best_price(prop: dict[str, Any]) -> tuple[str, float | None, str | None]:
    choices: list[tuple[str, float, str | None]] = []
    for side, price_key, book_key in (
        ("OVER", "best_over_price", "best_over_book"),
        ("UNDER", "best_under_price", "best_under_book"),
    ):
        price = num(prop.get(price_key))
        if price is not None:
            choices.append((side, price, prop.get(book_key)))
    if not choices:
        return "OVER", None, None
    choices.sort(key=lambda item: item[1], reverse=True)
    return choices[0]


def hit(value: float, line: float, side: str) -> bool:
    return value < line if side == "UNDER" else value >= line


def window(values: list[float], line: float, side: str, size: int) -> tuple[int, int, float | None]:
    sample = values[:size]
    hits = sum(hit(v, line, side) for v in sample)
    return hits, len(sample), round(hits / len(sample), 4) if sample else None


def streak(values: list[float], line: float, side: str) -> int:
    count = 0
    for value in values:
        if not hit(value, line, side):
            break
        count += 1
    return count


def build_rows(target: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    props_payload = load(PROPS, {})
    if str(props_payload.get("target_date") or "") != target:
        return [], {"canonical_rows": 0, "ladder_rows": 0, "eligible_rows": 0, "missing_history": 0}
    props = [r for r in props_payload.get("rows", []) if isinstance(r, dict)]
    histories = history_index()
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for prop in props:
        key = (str(prop.get("game") or ""), str(prop.get("player") or ""), str(prop.get("stat") or "").upper())
        groups[key].append(prop)

    ladder_rows: list[dict[str, Any]] = []
    eligible_rows: list[dict[str, Any]] = []
    missing_history = 0
    for (_, player, stat), group in groups.items():
        distinct_lines = {num(r.get("line")) for r in group}
        distinct_lines.discard(None)
        if len(distinct_lines) < 2:
            continue
        for prop in group:
            line = num(prop.get("line"))
            if line is None:
                continue
            side, odds, book = best_price(prop)
            ladder_rows.append(prop)
            records = histories.get(norm(player), [])
            values: list[float] = []
            recent_opponents: list[str] = []
            for record in records:
                value = stat_value(record, stat)
                if value is None:
                    continue
                values.append(value)
                recent_opponents.append(str(record.get("opponent") or ""))
            if len(values) < MIN_HISTORY:
                missing_history += 1
                continue
            current_streak = streak(values, line, side)
            l5_hits, l5_games, l5_pct = window(values, line, side, 5)
            l10_hits, l10_games, l10_pct = window(values, line, side, 10)
            season_hits = sum(hit(v, line, side) for v in values)
            season_games = len(values)
            eligible_rows.append({
                "player": player,
                "team": prop.get("team"),
                "game": prop.get("game"),
                "opponent": prop.get("opponent") or prop.get("opp_team"),
                "stat": stat,
                "side": side,
                "alt_line": line,
                "line_type": "alternate",
                "alt_source": "canonical-ladder-fallback",
                "streak": current_streak,
                "active_streak": current_streak >= 3,
                "l5_hits": l5_hits,
                "l5_games": l5_games,
                "l5_pct": l5_pct,
                "l10_hits": l10_hits,
                "l10_games": l10_games,
                "l10_pct": l10_pct,
                "last10_hits": l10_hits,
                "last10_games": l10_games,
                "last10_pct": l10_pct,
                "season_hits": season_hits,
                "season_games": season_games,
                "season_pct": round(season_hits / season_games, 4) if season_games else None,
                "average": round(sum(values) / len(values), 2),
                "recent_values": values[:10],
                "recent_opponents": recent_opponents[:10],
                "opponent_rank": None,
                "opponent_label": None,
                "best_odds": odds,
                "best_book": book,
                "event_id": prop.get("event_id"),
                "book_count": prop.get("book_count"),
            })
    return eligible_rows, {
        "canonical_rows": len(props),
        "ladder_rows": len(ladder_rows),
        "eligible_rows": len(eligible_rows),
        "missing_history": missing_history,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    target = args.date
    current = load(OUTS[0], {})
    summary = current.get("summary") if isinstance(current.get("summary"), dict) else {}
    exact_count = int(num(summary.get("alternate_rows")) or 0)
    if str(current.get("target_date") or "") == target and exact_count > 0:
        print({"status": "PASS", "target": target, "mode": "exact-alt", "alternate_rows": exact_count, "fallback_used": False})
        return

    fallback_rows, diagnostics = build_rows(target)
    standard_rows = [r for r in current.get("rows", []) if isinstance(r, dict) and r.get("line_type") == "standard"] if isinstance(current, dict) else []
    merged = fallback_rows + standard_rows
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok" if fallback_rows else "degraded",
        "source": "canonical-ladder-fallback+daily_standard_props",
        "summary": {
            **(summary if isinstance(summary, dict) else {}),
            **diagnostics,
            "rows": len(merged),
            "alternate_rows": len(fallback_rows),
            "active_alternate_streak_rows": sum(bool(r.get("active_streak")) for r in fallback_rows),
            "standard_rows": len(standard_rows),
            "fallback_used": True,
            "qa_warning": None if fallback_rows else "No current canonical ALT ladder rows had the minimum verified history sample.",
        },
        "rows": merged,
        "data_policy": "Exact ALT feed is preferred. When unavailable, current canonical multi-line player/game/stat ladders are scored against verified game logs using the exact visible line and side selected by the table's best-price rule.",
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print({"status": report["status"], "target": target, "mode": "canonical-ladder-fallback", **diagnostics})


if __name__ == "__main__":
    main()
