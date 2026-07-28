"""Sprint 22 Phase 2: build player intelligence warehouse from repository sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/warehouse/sprint22/player")

PROFILE_PATTERNS = ["player_stats_*.csv", "player_advanced_*.csv", "players_*.csv", "roster_*.csv"]
LOG_PATTERNS = ["player_game_logs_*.csv", "player_gamelogs_*.csv", "boxscores_players_*.csv", "player_boxscores_*.csv"]
AVAILABILITY_PATTERNS = ["injuries_*.csv", "player_availability_*.csv", "inactive_*.csv"]

ALIASES = {
    "name": "player", "player_name": "player", "athlete": "player",
    "athlete_id": "source_player_id", "person_id": "source_player_id",
    "tm": "team", "team_name": "team", "date": "game_date",
    "opp": "opponent", "min": "minutes", "mp": "minutes",
    "trb": "rebounds", "reb": "rebounds", "ast": "assists",
    "pts": "points", "stl": "steals", "blk": "blocks", "tov": "turnovers",
    "fg": "field_goals_made", "fga": "field_goals_attempted",
    "3p": "three_points_made", "3pa": "three_points_attempted",
    "ft": "free_throws_made", "fta": "free_throws_attempted",
}


def clean_name(value: object) -> str:
    text = str(value).strip().lower().replace("%", "_pct")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "unnamed"


def normalize_identity(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def discover(root: Path, patterns: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(root.glob(pattern))
    return sorted(set(files))


def season_from_path(path: Path):
    match = re.search(r"(20\d{2})", path.stem)
    return int(match.group(1)) if match else pd.NA


def stable_player_id(player: object, source_player_id: object = "") -> str:
    source = normalize_identity(source_player_id)
    key = f"source:{source}" if source else f"name:{normalize_identity(player)}"
    return "pl_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def assign_player_ids(frame: pd.DataFrame) -> pd.DataFrame:
    source_ids = frame["source_player_id"] if "source_player_id" in frame.columns else pd.Series("", index=frame.index)
    frame["player_id"] = [stable_player_id(player, source_id) for player, source_id in zip(frame["player"], source_ids)]
    return frame


def read_source(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    original = [clean_name(c) for c in frame.columns]
    frame.columns = [ALIASES.get(c, c) for c in original]
    if "player_id" in frame.columns and "source_player_id" not in frame.columns:
        frame = frame.rename(columns={"player_id": "source_player_id"})
    if "season" not in frame.columns:
        frame["season"] = season_from_path(path)
    frame["source_file"] = path.name
    return frame


def coalesce(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame

    def last_present(series: pd.Series):
        values = series.dropna()
        if values.empty:
            return pd.NA
        values = values[values.astype(str).str.strip().ne("")]
        return values.iloc[-1] if not values.empty else pd.NA

    def sources(series: pd.Series):
        return "|".join(sorted(set(series.dropna().astype(str))))

    agg = {c: (sources if c == "source_file" else last_present) for c in frame.columns if c not in keys}
    return frame.groupby(keys, dropna=False, as_index=False).agg(agg)


def build_profiles(files: list[Path]) -> pd.DataFrame:
    frames = [read_source(path) for path in files]
    if not frames:
        return pd.DataFrame(columns=["player_id", "player", "team", "season", "source_file"])
    frame = pd.concat(frames, ignore_index=True, sort=False)
    if "player" not in frame.columns:
        return pd.DataFrame(columns=["player_id", "player", "team", "season", "source_file"])
    if "team" not in frame.columns:
        frame["team"] = ""
    frame = assign_player_ids(frame)
    keys = [c for c in ["player_id", "season", "team"] if c in frame.columns]
    profile = coalesce(frame, keys)
    ordered = keys + [c for c in profile.columns if c not in keys]
    return profile[ordered]


def build_logs(files: list[Path]) -> pd.DataFrame:
    frames = [read_source(path) for path in files]
    if not frames:
        return pd.DataFrame(columns=["player_id", "game_id", "game_date", "player", "team", "opponent"])
    frame = pd.concat(frames, ignore_index=True, sort=False)
    if "player" not in frame.columns:
        return pd.DataFrame(columns=["player_id", "game_id", "game_date", "player", "team", "opponent"])
    if "team" not in frame.columns:
        frame["team"] = ""
    if "opponent" not in frame.columns:
        frame["opponent"] = ""
    if "game_date" in frame.columns:
        frame["game_date"] = pd.to_datetime(frame["game_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    else:
        frame["game_date"] = pd.NA
    frame = assign_player_ids(frame)
    frame["game_id"] = [
        hashlib.sha1(f"{d}|{min(str(t), str(o))}|{max(str(t), str(o))}".encode()).hexdigest()[:16]
        for d, t, o in zip(frame["game_date"], frame["team"], frame["opponent"])
    ]
    numeric = ["minutes", "points", "rebounds", "assists", "steals", "blocks", "turnovers", "field_goals_made", "field_goals_attempted", "three_points_made", "three_points_attempted", "free_throws_made", "free_throws_attempted"]
    for col in numeric:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return coalesce(frame, ["player_id", "game_id"]).sort_values(["player_id", "game_date"], na_position="last")


def build_rolling(logs: pd.DataFrame) -> pd.DataFrame:
    if logs.empty:
        return pd.DataFrame(columns=["player_id", "game_id", "game_date"])
    stats = [c for c in ["minutes", "points", "rebounds", "assists", "steals", "blocks", "turnovers"] if c in logs.columns]
    ordered = logs.sort_values(["player_id", "game_date"]).copy()
    output = ordered[[c for c in ["player_id", "game_id", "game_date", "player", "team", "opponent", "season"] if c in ordered.columns]].copy()
    for window in (3, 5, 10):
        for stat in stats:
            output[f"{stat}_avg_l{window}"] = ordered.groupby("player_id")[stat].transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
    if "points" in ordered.columns:
        output["points_volatility_l10"] = ordered.groupby("player_id")["points"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).std())
    if "minutes" in ordered.columns:
        output["minutes_trend_l5"] = ordered.groupby("player_id")["minutes"].transform(lambda s: s.shift(1).rolling(5, min_periods=2).mean())
    return output


def build_matchups(logs: pd.DataFrame) -> pd.DataFrame:
    if logs.empty or "opponent" not in logs.columns:
        return pd.DataFrame(columns=["player_id", "opponent", "games"])
    stats = [c for c in ["minutes", "points", "rebounds", "assists", "steals", "blocks", "turnovers"] if c in logs.columns]
    agg = {stat: "mean" for stat in stats}
    agg["game_id"] = "nunique"
    return logs.groupby(["player_id", "opponent"], dropna=False).agg(agg).reset_index().rename(columns={"game_id": "games"})


def build_availability(files: list[Path]) -> pd.DataFrame:
    frames = [read_source(path) for path in files]
    if not frames:
        return pd.DataFrame(columns=["player_id", "snapshot_date", "player", "team", "status", "source_file"])
    frame = pd.concat(frames, ignore_index=True, sort=False)
    if "player" not in frame.columns:
        return pd.DataFrame(columns=["player_id", "snapshot_date", "player", "team", "status", "source_file"])
    if "team" not in frame.columns:
        frame["team"] = ""
    date_col = next((c for c in ["snapshot_date", "game_date", "date"] if c in frame.columns), None)
    frame["snapshot_date"] = pd.to_datetime(frame[date_col], errors="coerce").dt.strftime("%Y-%m-%d") if date_col else pd.NA
    frame = assign_player_ids(frame)
    if "status" not in frame.columns:
        frame["status"] = "unknown"
    return coalesce(frame, ["player_id", "snapshot_date"])


def build(raw_dir: Path = RAW, out_dir: Path = OUT) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "profile": discover(raw_dir, PROFILE_PATTERNS),
        "game_logs": discover(raw_dir, LOG_PATTERNS),
        "availability": discover(raw_dir, AVAILABILITY_PATTERNS),
    }
    profile = build_profiles(sources["profile"])
    logs = build_logs(sources["game_logs"])
    rolling = build_rolling(logs)
    availability = build_availability(sources["availability"])
    matchups = build_matchups(logs)
    tables = {"player_profile": profile, "player_game_logs": logs, "player_rolling_metrics": rolling, "player_availability": availability, "player_matchups": matchups}
    for name, frame in tables.items():
        frame.to_csv(out_dir / f"{name}.csv", index=False)

    profile_ids = set(profile.get("player_id", pd.Series(dtype=str)).dropna())
    log_ids = set(logs.get("player_id", pd.Series(dtype=str)).dropna())
    availability_ids = set(availability.get("player_id", pd.Series(dtype=str)).dropna())
    all_ids = profile_ids | log_ids | availability_ids
    log_only_ids = log_ids - profile_ids
    availability_only_ids = availability_ids - profile_ids
    linked_log_rows = int(logs["player_id"].isin(profile_ids).sum()) if not logs.empty else 0

    duplicate_keys = int(logs.duplicated(["player_id", "game_id"]).sum()) if not logs.empty else 0
    status = "PASS" if len(profile) > 0 and duplicate_keys == 0 and not log_only_ids and not availability_only_ids else "WARN"
    catalog = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warehouse_version": "sprint22_phase2_v2",
        "tables": {name: {"rows": int(len(frame)), "columns": int(len(frame.columns))} for name, frame in tables.items()},
        "sources": {name: [p.name for p in paths] for name, paths in sources.items()},
        "stable_player_ids": int(len(all_ids)),
        "identity_policy": "Prefer source player ID; otherwise hash normalized player name. Team is never part of player_id.",
        "duplicate_game_keys": duplicate_keys,
        "profile_linked_game_log_rows": linked_log_rows,
        "log_only_player_ids": sorted(log_only_ids),
        "availability_only_player_ids": sorted(availability_only_ids),
        "rolling_is_pregame_lagged": True,
        "status": status,
        "notes": ["Empty game-log or availability tables are valid until matching raw sources are collected.", "WARN identifies unresolved cross-table identities without discarding their records."],
    }
    (out_dir / "player_catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print("Sprint 22 Phase 2:", {"status": catalog["status"], "tables": {k: v["rows"] for k, v in catalog["tables"].items()}})
    return catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=str(RAW))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    build(Path(args.raw), Path(args.out))


if __name__ == "__main__":
    main()
