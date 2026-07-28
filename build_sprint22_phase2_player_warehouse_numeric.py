"""Compatibility entrypoint that enforces numeric player stats before aggregation."""
from __future__ import annotations

import pandas as pd

import build_sprint22_phase2_player_warehouse as warehouse

NUMERIC_STATS = [
    "minutes", "points", "rebounds", "assists", "steals", "blocks", "turnovers",
    "field_goals_made", "field_goals_attempted", "three_points_made",
    "three_points_attempted", "free_throws_made", "free_throws_attempted",
]

_original_build_logs = warehouse.build_logs


def build_logs_numeric(files):
    """Build logs and restore numeric dtypes after coalescing."""
    logs = _original_build_logs(files)
    for column in NUMERIC_STATS:
        if column in logs.columns:
            logs[column] = pd.to_numeric(logs[column], errors="coerce")
    return logs


def main() -> None:
    warehouse.build_logs = build_logs_numeric
    warehouse.main()


if __name__ == "__main__":
    main()
