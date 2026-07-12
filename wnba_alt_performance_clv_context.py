"""Attach certified ALT closing-line metrics to the performance report."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

HISTORY = Path("data/history/wnba_alt_streak_history.jsonl")
PERFORMANCE_PATHS = [
    Path("data/warehouse/wnba_alt_performance.json"),
    Path("data/dashboard/wnba_alt_performance.json"),
]


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


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    certified = [row for row in rows if row.get("clv_status") == "CERTIFIED_PREGAME"]
    line_values = [num(row.get("line_clv")) for row in certified]
    line_values = [value for value in line_values if value is not None]
    price_values = [num(row.get("price_clv")) for row in certified]
    price_values = [value for value in price_values if value is not None]
    positive = sum(bool(row.get("clv_positive")) for row in certified)
    return {
        "candidates": len(rows),
        "certified": len(certified),
        "positive": positive,
        "positive_rate": round(positive / len(certified), 4) if certified else None,
        "average_line_clv": round(sum(line_values) / len(line_values), 4) if line_values else None,
        "average_price_clv": round(sum(price_values) / len(price_values), 6) if price_values else None,
    }


def grouped(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(field) or "Unknown")].append(row)
    output = [{"group": name, **summarize(items)} for name, items in groups.items()]
    output.sort(key=lambda row: (row.get("certified", 0), row.get("positive_rate") or -1), reverse=True)
    return output


def main() -> None:
    rows = read_jsonl(HISTORY)
    overall = summarize(rows)
    context = {
        "summary": overall,
        "by_grade": grouped(rows, "streak_grade"),
        "by_score_band": grouped(rows, "score_band"),
        "by_stat": grouped(rows, "stat"),
        "by_side": grouped(rows, "side"),
        "by_sportsbook": grouped(rows, "best_book"),
        "policy": {
            "certification": "latest captured market at or before verified game start",
            "post_start_lines": "excluded",
            "missing_start_time": "uncertified",
            "positive_line_clv": "frozen line was better for the selected side",
            "positive_price_clv": "closing implied probability was higher than at snapshot",
        },
    }
    for path in PERFORMANCE_PATHS:
        payload = load(path, {"status": "ok", "summary": {}})
        payload["clv"] = context
        payload.setdefault("summary", {}).update({
            "certified_clv": overall["certified"],
            "positive_clv": overall["positive"],
            "positive_clv_rate": overall["positive_rate"],
            "average_line_clv": overall["average_line_clv"],
            "average_price_clv": overall["average_price_clv"],
        })
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
    print("ALT Performance CLV context:", overall)


if __name__ == "__main__":
    main()
