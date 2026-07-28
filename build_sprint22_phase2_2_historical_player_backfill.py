"""Audit and summarize the historical player backfill after collection and normalization."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/warehouse/sprint22/player")
REPORT = OUT / "historical_backfill_catalog.json"


def season_from_name(path: Path) -> int | None:
    try:
        return int(path.stem.rsplit("_", 1)[-1])
    except ValueError:
        return None


def inspect(raw_dir: Path = RAW, out_dir: Path = OUT, minimum_seasons: int = 5) -> dict:
    files = sorted(raw_dir.glob("player_game_logs_*.csv"))
    seasons = {}
    total_rows = 0
    players = set()
    duplicate_keys = 0
    missing_dates = 0

    for path in files:
        season = season_from_name(path)
        if season is None:
            continue
        frame = pd.read_csv(path)
        rows = int(len(frame))
        total_rows += rows
        id_col = "source_player_id" if "source_player_id" in frame.columns else "player"
        if id_col in frame.columns:
            players.update(frame[id_col].dropna().astype(str))
        if {"game_id", id_col}.issubset(frame.columns):
            duplicate_keys += int(frame.duplicated([id_col, "game_id"]).sum())
        if "game_date" in frame.columns:
            missing_dates += int(pd.to_datetime(frame["game_date"], errors="coerce").isna().sum())
        seasons[str(season)] = {
            "rows": rows,
            "players": int(frame[id_col].nunique(dropna=True)) if id_col in frame.columns else 0,
            "date_min": str(frame["game_date"].dropna().min()) if "game_date" in frame.columns and frame["game_date"].notna().any() else None,
            "date_max": str(frame["game_date"].dropna().max()) if "game_date" in frame.columns and frame["game_date"].notna().any() else None,
            "source_file": path.name,
        }

    warehouse_catalog_path = out_dir / "player_catalog.json"
    warehouse = json.loads(warehouse_catalog_path.read_text()) if warehouse_catalog_path.exists() else {}
    season_numbers = sorted(int(s) for s in seasons)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "backfill_version": "sprint22_phase2_2_v1",
        "seasons": seasons,
        "season_count": len(seasons),
        "season_min": season_numbers[0] if season_numbers else None,
        "season_max": season_numbers[-1] if season_numbers else None,
        "total_game_logs": total_rows,
        "unique_players": len(players),
        "duplicate_player_game_keys": duplicate_keys,
        "missing_game_dates": missing_dates,
        "warehouse_tables": {k: v.get("rows", 0) for k, v in warehouse.get("tables", {}).items()},
        "minimum_seasons_required": minimum_seasons,
    }
    required_tables = report["warehouse_tables"]
    report["status"] = "PASS" if (
        len(seasons) >= minimum_seasons
        and total_rows > 0
        and duplicate_keys == 0
        and required_tables.get("player_profile", 0) > 0
        and required_tables.get("player_game_logs", 0) > 0
        and required_tables.get("player_rolling_metrics", 0) > 0
    ) else "WARN"
    out_dir.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Sprint 22 Phase 2.2:", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=str(RAW))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--minimum-seasons", type=int, default=5)
    args = parser.parse_args()
    inspect(Path(args.raw), Path(args.out), args.minimum_seasons)


if __name__ == "__main__":
    main()
