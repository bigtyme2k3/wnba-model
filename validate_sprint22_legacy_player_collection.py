"""Fail fast when requested historical player seasons were not collected correctly."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REQUIRED_IDENTITY = {"athlete_id", "athlete_display_name", "player_id", "player_name"}


def validate(raw_dir: Path, start: int, end: int) -> dict:
    failures: list[str] = []
    seasons: dict[str, dict] = {}

    for season in range(start, end + 1):
        path = raw_dir / f"wehoop_player_box_{season}.csv"
        if not path.exists():
            failures.append(f"{season}: missing {path}")
            continue

        try:
            frame = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            failures.append(f"{season}: unreadable CSV: {exc}")
            continue

        columns = list(frame.columns)
        has_game = "game_id" in frame.columns
        identity = sorted(REQUIRED_IDENTITY.intersection(frame.columns))
        seasons[str(season)] = {
            "rows": int(len(frame)),
            "columns": columns,
            "identity_columns": identity,
        }

        if frame.empty or not has_game or not identity:
            failures.append(
                f"{season}: invalid player table rows={len(frame)} "
                f"has_game_id={has_game} identity={identity} columns={columns[:40]}"
            )

    if failures:
        raise RuntimeError(
            "Historical player collection validation failed:\n- " + "\n- ".join(failures)
        )

    result = {"status": "PASS", "season_count": len(seasons), "seasons": seasons}
    print("Historical player collection verified:", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    args = parser.parse_args()
    validate(Path(args.raw), args.start, args.end)


if __name__ == "__main__":
    main()
