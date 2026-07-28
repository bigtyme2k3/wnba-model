"""Collect only historical WNBA player box scores for Sprint 22 Phase 2.2.

This intentionally bypasses team-box and schedule downloads so a legacy failure in
an unrelated dataset cannot prevent valid player data from being written.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import collect_wehoop as base
from collect_wehoop_compatible import read_rds_url_compatible


def collect_season(season: int, out_dir: Path) -> dict:
    url = base.SDV_URLS["player_box"].format(year=season)
    print(f"Season {season}: downloading player box...", end="", flush=True)
    frame = read_rds_url_compatible(url)
    if frame.empty:
        raise RuntimeError(f"season {season}: player release is missing or empty")

    columns = [column for column in base.PLAYER_BOX_COLS if column in frame.columns]
    frame = frame[columns].copy()
    has_player = any(column in frame.columns for column in ("athlete_id", "athlete_display_name"))
    if "game_id" not in frame.columns or not has_player:
        raise RuntimeError(
            f"season {season}: invalid recovered player schema; columns={list(frame.columns)}"
        )

    frame = frame[frame["game_id"].notna()].copy()
    if "athlete_id" in frame.columns and "athlete_display_name" in frame.columns:
        frame = frame[
            frame["athlete_id"].notna() | frame["athlete_display_name"].notna()
        ].copy()
    if frame.empty:
        raise RuntimeError(f"season {season}: no valid player-game rows after validation")

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"wehoop_player_box_{season}.csv"
    frame.to_csv(path, index=False)
    result = {
        "season": season,
        "rows": int(len(frame)),
        "players": int(
            frame["athlete_id"].nunique(dropna=True)
            if "athlete_id" in frame.columns
            else frame["athlete_display_name"].nunique(dropna=True)
        ),
        "columns": list(frame.columns),
        "path": str(path),
    }
    print(f" {result['rows']} rows -> {path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--out", default=base.OUT_DIR)
    args = parser.parse_args()

    if args.end < args.start:
        raise SystemExit("end season must be greater than or equal to start season")

    out_dir = Path(args.out)
    results = []
    failures = []
    for season in range(args.start, args.end + 1):
        try:
            results.append(collect_season(season, out_dir))
        except Exception as exc:
            failures.append(f"{season}: {exc}")
            print(f" ERROR: {exc}")

    if failures:
        raise SystemExit("Historical player collection failed:\n" + "\n".join(failures))

    print("Historical player-only collection complete:", {
        "seasons": len(results),
        "rows": sum(item["rows"] for item in results),
    })


if __name__ == "__main__":
    main()
