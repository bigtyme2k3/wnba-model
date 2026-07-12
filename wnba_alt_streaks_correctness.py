"""Correct ALT Streaks display semantics after the base board is built.

The current source exposes five recent values, not ten full game results. It
also does not expose verified season hit counts or a documented stat-specific
opponent defensive rank. Those fields remain null until their source contracts
are implemented.
"""
from __future__ import annotations

import json
from pathlib import Path

PATHS = [
    Path("data/warehouse/wnba_alt_streaks.json"),
    Path("data/dashboard/wnba_alt_streaks.json"),
]


def main() -> None:
    updated = 0
    for path in PATHS:
        if not path.exists():
            continue
        payload = json.load(path.open(encoding="utf-8"))
        for row in payload.get("rows", []):
            games = int(row.get("last10_games") or len(row.get("recent_values") or []))
            row["recent_hits"] = row.pop("last10_hits", None)
            row["recent_games"] = games
            row["recent_pct"] = row.pop("last10_pct", None)
            row["recent_label"] = f"L{games}" if games else "Recent"
            row.pop("last10_games", None)
            # Do not convert a recent hit-rate field into a season record.
            row["season_hits"] = None
            row["season_games"] = None
            row["season_pct"] = None
            row["season_source"] = None
            # The upstream opp_rank field is not documented as stat-specific.
            # Suppress it until a verified opponent-vs-stat ranking is available.
            row["opponent_rank"] = None
            row["opponent_label"] = None
            row["opponent_rank_source"] = None
            updated += 1
        payload.setdefault("summary", {})["recent_sample_size"] = max(
            [int(r.get("recent_games") or 0) for r in payload.get("rows", [])] or [0]
        )
        payload["data_policy"] = (
            "Recent column reflects the exact verified sample size (currently L5). "
            "Season hit rate and opponent-vs-stat rank remain blank until verified source data is available."
        )
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
    print(f"ALT Streaks correctness applied to {updated} rows")


if __name__ == "__main__":
    main()
