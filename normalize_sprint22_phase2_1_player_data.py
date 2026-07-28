"""Normalize existing wehoop/ESPN player boxes into Sprint 22 player inputs."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")

ALIASES = {
    "athlete_id": "source_player_id", "player_id": "source_player_id",
    "athlete_display_name": "player", "player_name": "player",
    "team_name": "team", "team_abbreviation": "team_abbr", "team_abbr": "team_abbr",
    "athlete_position_abbreviation": "position", "pts": "points", "reb": "rebounds",
    "ast": "assists", "stl": "steals", "blk": "blocks", "tov": "turnovers",
    "fg_made": "field_goals_made", "fg_att": "field_goals_attempted",
    "threes_made": "three_points_made", "threes_att": "three_points_attempted",
    "three_point_field_goals_made": "three_points_made",
    "three_point_field_goals_attempted": "three_points_attempted",
    "ft_made": "free_throws_made", "ft_att": "free_throws_attempted",
}


def clean(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def season_from_path(path: Path) -> int | None:
    match = re.search(r"(20\d{2})", path.stem)
    return int(match.group(1)) if match else None


def normalize_file(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.columns = [ALIASES.get(clean(c), clean(c)) for c in frame.columns]
    if "season" not in frame.columns:
        frame["season"] = season_from_path(path)
    required = ["player", "team", "game_id", "game_date"]
    for col in required:
        if col not in frame.columns:
            frame[col] = pd.NA
    if "source_player_id" not in frame.columns:
        frame["source_player_id"] = pd.NA
    frame["game_date"] = pd.to_datetime(frame["game_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["source_file"] = path.name
    frame["source_system"] = "sportsdataverse" if "athlete_id" in [clean(c) for c in pd.read_csv(path, nrows=0).columns] else "espn_api"
    numeric = ["minutes", "points", "rebounds", "assists", "steals", "blocks", "turnovers",
               "field_goals_made", "field_goals_attempted", "three_points_made",
               "three_points_attempted", "free_throws_made", "free_throws_attempted", "plus_minus"]
    for col in numeric:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame[frame["player"].notna() & frame["game_id"].notna()].copy()
    return frame


def build(raw_dir: Path = RAW) -> dict:
    files = sorted(raw_dir.glob("wehoop_player_box_*.csv"))
    outputs = {}
    total_rows = 0
    total_players = set()
    for path in files:
        frame = normalize_file(path)
        if frame.empty:
            continue
        season = season_from_path(path) or int(pd.to_numeric(frame["season"], errors="coerce").dropna().iloc[0])
        frame = frame.drop_duplicates(["source_player_id", "game_id", "player"], keep="last")
        log_path = raw_dir / f"player_game_logs_{season}.csv"
        frame.to_csv(log_path, index=False)
        profile_cols = [c for c in ["source_player_id", "player", "team", "team_abbr", "position", "season", "source_system", "source_file"] if c in frame.columns]
        profiles = frame[profile_cols].drop_duplicates(["source_player_id", "player", "team"], keep="last")
        profile_path = raw_dir / f"player_profiles_{season}.csv"
        profiles.to_csv(profile_path, index=False)
        outputs[str(season)] = {"logs": len(frame), "profiles": len(profiles), "source": path.name}
        total_rows += len(frame)
        total_players.update(profiles["source_player_id"].fillna(profiles["player"]).astype(str))
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_files": [p.name for p in files],
        "seasons": outputs,
        "total_game_logs": total_rows,
        "unique_players": len(total_players),
        "status": "PASS" if total_rows > 0 else "WARN",
    }
    (raw_dir / "player_ingestion_catalog.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Sprint 22 Phase 2.1:", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=str(RAW))
    args = parser.parse_args()
    build(Path(args.raw))


if __name__ == "__main__":
    main()
