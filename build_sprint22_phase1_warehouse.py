"""Sprint 22 Phase 1: normalize existing WNBA sources into intelligence warehouse layers."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/warehouse/sprint22")
CATALOG = OUT / "warehouse_catalog.json"

LAYERS = {
    "team_season": ["team_advanced_*.csv", "team_stats_*.csv"],
    "player_season": ["player_advanced_*.csv", "player_stats_*.csv"],
    "game_context": ["schedule_*.csv", "game_logs_*.csv", "scores_*.csv"],
    "market_snapshot": ["odds_*.csv", "odds_consensus.csv", "odds_historical.csv"],
}
KEY_CANDIDATES = {
    "team_season": ["season", "team"],
    "player_season": ["season", "player", "team"],
    "game_context": ["season", "game_date", "home_team", "away_team"],
    "market_snapshot": [
        "game_date", "home_team", "away_team", "sportsbook", "market",
        "selection", "outcome_name", "point", "snapshot_time",
    ],
}
COALESCE_LAYERS = {"team_season", "player_season", "game_context"}


def clean_name(value: object) -> str:
    text = str(value).strip().lower().replace("%", "_pct")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unnamed"


def season_from_path(path: Path):
    match = re.search(r"(20\d{2})", path.stem)
    return int(match.group(1)) if match else None


def source_type(path: Path) -> str:
    stem = re.sub(r"_20\d{2}$", "", path.stem)
    return clean_name(stem)


def read_source(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.columns = [clean_name(col) for col in frame.columns]
    if "season" not in frame.columns and season_from_path(path) is not None:
        frame["season"] = season_from_path(path)
    frame["source_file"] = path.name
    frame["source_type"] = source_type(path)
    frame["source_system"] = "repository_raw"
    return frame


def discover(patterns: Iterable[str]) -> List[Path]:
    found: List[Path] = []
    for pattern in patterns:
        found.extend(RAW.glob(pattern))
    return sorted(set(found))


def normalize_dates(frame: pd.DataFrame) -> pd.DataFrame:
    for candidate in ["game_date", "date", "start_time", "commence_time"]:
        if candidate not in frame.columns:
            continue
        parsed = pd.to_datetime(frame[candidate], errors="coerce", utc=True)
        if candidate == "game_date" or "game_date" not in frame.columns:
            frame["game_date"] = parsed.dt.strftime("%Y-%m-%d")
        if candidate in {"start_time", "commence_time"} and "snapshot_time" not in frame.columns:
            frame["snapshot_time"] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Historical aggregate files often omit season. Derive it from the normalized
    # game date so identical observations from yearly and historical files share
    # the same business identity during deduplication.
    if "game_date" in frame.columns:
        date_year = pd.to_datetime(frame["game_date"], errors="coerce").dt.year
        if "season" not in frame.columns:
            frame["season"] = date_year
        else:
            frame["season"] = pd.to_numeric(frame["season"], errors="coerce").fillna(date_year)
            frame["season"] = frame["season"].astype("Int64")
    return frame


def first_present(series: pd.Series):
    values = series.dropna()
    if values.empty:
        return pd.NA
    strings = values.astype(str).str.strip()
    valid = values.loc[strings.ne("")]
    return valid.iloc[-1] if not valid.empty else pd.NA


def join_provenance(series: pd.Series) -> str:
    values = sorted({str(value) for value in series.dropna() if str(value).strip()})
    return "|".join(values)


def coalesce_records(frame: pd.DataFrame, keys: List[str]) -> pd.DataFrame:
    if not keys:
        return frame.drop_duplicates().reset_index(drop=True)
    aggregations = {}
    for column in frame.columns:
        if column in keys:
            continue
        aggregations[column] = join_provenance if column in {"source_file", "source_type", "source_system"} else first_present
    return frame.groupby(keys, dropna=False, as_index=False).agg(aggregations)


def dedupe_market(frame: pd.DataFrame, keys: List[str]) -> pd.DataFrame:
    provenance = {"source_file", "source_type", "source_system"}
    before = len(frame)
    if not keys:
        business_columns = [column for column in frame.columns if column not in provenance]
        frame = frame.drop_duplicates(subset=business_columns, keep="last").reset_index(drop=True)
    else:
        # Coalesce duplicate observations at the declared market grain. This
        # preserves fields and multi-file provenance instead of keeping an
        # arbitrary source row.
        frame = coalesce_records(frame, keys)
    frame.attrs["duplicates_removed"] = before - len(frame)
    return frame


def build_layer(name: str, files: List[Path]) -> Tuple[pd.DataFrame, Dict]:
    frames = []
    errors = []
    input_rows = 0
    for path in files:
        try:
            source = read_source(path)
            input_rows += len(source)
            frames.append(source)
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})
    if not frames:
        return pd.DataFrame(), {
            "layer": name, "rows": 0, "input_rows": 0, "columns": 0,
            "files": [], "keys_present": [], "duplicates_removed": 0,
            "grain_unique": True, "errors": errors,
        }

    frame = normalize_dates(pd.concat(frames, ignore_index=True, sort=False))
    keys = [key for key in KEY_CANDIDATES[name] if key in frame.columns]
    before = len(frame)
    if name in COALESCE_LAYERS:
        frame = coalesce_records(frame, keys)
        duplicates_removed = before - len(frame)
    else:
        frame = dedupe_market(frame, keys)
        duplicates_removed = int(frame.attrs.get("duplicates_removed", 0))

    ordered = keys + sorted(column for column in frame.columns if column not in keys)
    frame = frame[ordered]
    coverage = {column: round(float(frame[column].notna().mean()), 6) for column in frame.columns}
    grain_unique = not keys or not frame.duplicated(subset=keys).any()
    return frame, {
        "layer": name,
        "rows": int(len(frame)),
        "input_rows": int(input_rows),
        "columns": int(len(frame.columns)),
        "files": [path.name for path in files],
        "keys_present": keys,
        "duplicates_removed": int(duplicates_removed),
        "grain_unique": bool(grain_unique),
        "column_coverage": coverage,
        "errors": errors,
    }


def build(raw_dir: Path = RAW, out_dir: Path = OUT) -> Dict:
    global RAW, OUT, CATALOG
    RAW, OUT, CATALOG = raw_dir, out_dir, out_dir / "warehouse_catalog.json"
    OUT.mkdir(parents=True, exist_ok=True)
    layer_reports = {}
    total_rows = 0
    total_input_rows = 0
    for name, patterns in LAYERS.items():
        files = discover(patterns)
        frame, report = build_layer(name, files)
        layer_reports[name] = report
        total_rows += report["rows"]
        total_input_rows += report["input_rows"]
        frame.to_csv(OUT / f"{name}.csv", index=False)

    has_errors = any(report["errors"] for report in layer_reports.values())
    bad_grain = any(not report["grain_unique"] for report in layer_reports.values())
    catalog = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warehouse_version": "sprint22_phase1_v2",
        "raw_directory": str(RAW),
        "output_directory": str(OUT),
        "layers": layer_reports,
        "total_input_rows": total_input_rows,
        "total_rows": total_rows,
        "status": "WARN" if total_rows == 0 or has_errors or bad_grain else "PASS",
        "next_sources": ["injuries", "lineups", "play_by_play", "referees", "travel_distance"],
    }
    CATALOG.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print("Sprint 22 Phase 1 warehouse:", {
        "total_input_rows": total_input_rows,
        "total_rows": total_rows,
        "status": catalog["status"],
        "layers": {key: value["rows"] for key, value in layer_reports.items()},
    })
    return catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=str(RAW))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    build(Path(args.raw), Path(args.out))


if __name__ == "__main__":
    main()
