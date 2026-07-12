"""Track verified opening and closing markets for ALT Streak candidates.

Every workflow refresh stores the currently available line and price. A closing
snapshot is certified only when a game start time is known; it is the latest
captured market at or before that start time. No post-start line is used.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ALT = Path("data/dashboard/wnba_alt_streaks.json")
MASTER = Path("data/dashboard/wnba_master.json")
HISTORY = Path("data/history/wnba_alt_streak_history.jsonl")
SNAPSHOTS = Path("data/history/wnba_alt_market_snapshots.jsonl")
OUTS = [Path("data/warehouse/wnba_alt_clv.json"), Path("data/dashboard/wnba_alt_clv.json")]


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if path.exists():
        for line in path.open(encoding="utf-8"):
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except Exception:
                pass
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(clean(row), separators=(",", ":"), allow_nan=False) + "\n")


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


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def implied(odds: Any) -> float | None:
    price = num(odds)
    if price is None or price == 0:
        return None
    return (-price / (-price + 100.0)) if price < 0 else (100.0 / (price + 100.0))


def market_key(row: dict[str, Any], target: str) -> str:
    return "|".join(norm(v) for v in (
        target, row.get("player"), row.get("game"), row.get("stat"),
        row.get("side"), row.get("best_book"),
    ))


def game_start_map() -> dict[str, str]:
    master = load(MASTER, {})
    output: dict[str, str] = {}
    for game in master.get("games", []) if isinstance(master, dict) else []:
        if not isinstance(game, dict):
            continue
        label = game.get("game") or " @ ".join(filter(None, (game.get("away_team"), game.get("home_team"))))
        start = game.get("start_time") or game.get("commence_time") or game.get("game_time")
        parsed = parse_time(start)
        if label and parsed:
            output[norm(label)] = parsed.isoformat()
    return output


def snapshot(target: str) -> dict[str, int]:
    payload = load(ALT, {"rows": []})
    existing = read_jsonl(SNAPSHOTS)
    seen = {str(row.get("snapshot_id")) for row in existing}
    starts = game_start_map()
    now = datetime.now(timezone.utc)
    added = duplicates = post_start_skipped = 0
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        key = market_key(row, target)
        start_text = starts.get(norm(row.get("game")))
        start = parse_time(start_text)
        if start is not None and now > start:
            post_start_skipped += 1
            continue
        line = num(row.get("alt_line"))
        odds = num(row.get("best_odds"))
        state = f"{line}|{odds}|{norm(row.get('best_book'))}"
        snapshot_id = f"{key}|{now.strftime('%Y-%m-%dT%H')}|{state}"
        if snapshot_id in seen:
            duplicates += 1
            continue
        existing.append({
            "snapshot_id": snapshot_id,
            "market_key": key,
            "date": target,
            "captured_at_utc": now.isoformat(),
            "game_start_utc": start_text,
            "pregame_verified": start is not None and now <= start,
            "player": row.get("player"),
            "game": row.get("game"),
            "stat": row.get("stat"),
            "side": row.get("side"),
            "line": line,
            "odds": odds,
            "sportsbook": row.get("best_book"),
            "line_type": row.get("line_type"),
            "source": "alt_streaks_daily_market",
        })
        seen.add(snapshot_id)
        added += 1
    write_jsonl(SNAPSHOTS, existing)
    return {"added": added, "duplicates": duplicates, "post_start_skipped": post_start_skipped, "total": len(existing)}


def line_clv(open_line: float | None, close_line: float | None, side: str) -> float | None:
    if open_line is None or close_line is None:
        return None
    return close_line - open_line if str(side).upper() == "OVER" else open_line - close_line


def resolve(target: str) -> dict[str, int]:
    history = read_jsonl(HISTORY)
    snapshots = read_jsonl(SNAPSHOTS)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in snapshots:
        grouped.setdefault(str(row.get("market_key") or ""), []).append(row)
    updated = certified = missing_start = missing_snapshots = 0
    for candidate in history:
        if str(candidate.get("date")) != target:
            continue
        key = market_key({
            "player": candidate.get("player"), "game": candidate.get("game"),
            "stat": candidate.get("stat"), "side": candidate.get("side"),
            "best_book": candidate.get("best_book"),
        }, target)
        options = grouped.get(key, [])
        if not options:
            missing_snapshots += 1
            continue
        options.sort(key=lambda row: str(row.get("captured_at_utc") or ""))
        opening = options[0]
        starts = [parse_time(row.get("game_start_utc")) for row in options]
        start = next((value for value in starts if value is not None), None)
        if start is None:
            candidate["clv_status"] = "UNCERTIFIED_NO_GAME_START"
            missing_start += 1
            continue
        pregame = [row for row in options if (parse_time(row.get("captured_at_utc")) or datetime.max.replace(tzinfo=timezone.utc)) <= start]
        if not pregame:
            candidate["clv_status"] = "UNCERTIFIED_NO_PREGAME_SNAPSHOT"
            continue
        closing = pregame[-1]
        open_line = num(candidate.get("alt_line"))
        if open_line is None:
            open_line = num(opening.get("line"))
        close_line = num(closing.get("line"))
        open_odds = num(candidate.get("best_odds"))
        if open_odds is None:
            open_odds = num(opening.get("odds"))
        close_odds = num(closing.get("odds"))
        lclv = line_clv(open_line, close_line, str(candidate.get("side") or ""))
        open_prob, close_prob = implied(open_odds), implied(close_odds)
        pclv = None if open_prob is None or close_prob is None else close_prob - open_prob
        candidate.update({
            "opening_line": open_line,
            "opening_odds": open_odds,
            "closing_line": close_line,
            "closing_odds": close_odds,
            "closing_sportsbook": closing.get("sportsbook"),
            "closing_captured_at_utc": closing.get("captured_at_utc"),
            "game_start_utc": start.isoformat(),
            "line_clv": round(lclv, 4) if lclv is not None else None,
            "price_clv": round(pclv, 6) if pclv is not None else None,
            "clv_positive": bool((lclv or 0) > 0 or (pclv or 0) > 0),
            "clv_status": "CERTIFIED_PREGAME",
            "clv_source": "wnba_alt_market_snapshots",
        })
        updated += 1
        certified += 1
    write_jsonl(HISTORY, history)
    return {"updated": updated, "certified": certified, "missing_start": missing_start, "missing_snapshots": missing_snapshots}


def report(target: str) -> dict[str, Any]:
    history = [row for row in read_jsonl(HISTORY) if str(row.get("date")) == target]
    certified = [row for row in history if row.get("clv_status") == "CERTIFIED_PREGAME"]
    line_values = [num(row.get("line_clv")) for row in certified]
    line_values = [value for value in line_values if value is not None]
    price_values = [num(row.get("price_clv")) for row in certified]
    price_values = [value for value in price_values if value is not None]
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "summary": {
            "candidates": len(history),
            "certified_clv": len(certified),
            "positive_clv": sum(bool(row.get("clv_positive")) for row in certified),
            "positive_clv_rate": round(sum(bool(row.get("clv_positive")) for row in certified) / len(certified), 4) if certified else None,
            "average_line_clv": round(sum(line_values) / len(line_values), 4) if line_values else None,
            "average_price_clv": round(sum(price_values) / len(price_values), 6) if price_values else None,
        },
        "records": certified,
        "methodology": {
            "opening": "candidate's frozen pregame line and price",
            "closing": "latest captured market at or before verified game start",
            "post_start_policy": "never used",
            "line_clv_direction": "positive means the frozen line was better for the selected side",
            "price_clv_direction": "positive means the market's closing implied probability was higher than at snapshot",
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(clean(payload), handle, indent=2, allow_nan=False)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("snapshot", "resolve", "report", "all"))
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    if args.mode in {"snapshot", "all"}:
        print("ALT CLV snapshot:", snapshot(args.date))
    if args.mode in {"resolve", "all"}:
        print("ALT CLV resolve:", resolve(args.date))
    if args.mode in {"report", "all"}:
        print("ALT CLV report:", report(args.date)["summary"])


if __name__ == "__main__":
    main()
