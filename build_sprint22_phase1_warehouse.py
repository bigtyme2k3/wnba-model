"""Sprint 22 Phase 1: normalize existing WNBA sources into intelligence warehouse layers."""
from __future__ import annotations
import argparse, json, re
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
    "market_snapshot": ["game_date", "home_team", "away_team", "sportsbook", "market"],
}

def clean_name(value: object) -> str:
    text = str(value).strip().lower().replace("%", "_pct")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unnamed"

def season_from_path(path: Path):
    match = re.search(r"(20\d{2})", path.stem)
    return int(match.group(1)) if match else None

def read_source(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.columns = [clean_name(col) for col in frame.columns]
    if "season" not in frame.columns and season_from_path(path) is not None:
        frame["season"] = season_from_path(path)
    frame["source_file"] = path.name
    frame["source_system"] = "repository_raw"
    return frame

def discover(patterns: Iterable[str]) -> List[Path]:
    found: List[Path] = []
    for pattern in patterns:
        found.extend(RAW.glob(pattern))
    return sorted(set(found))

def normalize_dates(frame: pd.DataFrame) -> pd.DataFrame:
    for candidate in ["game_date", "date", "start_time", "commence_time"]:
        if candidate in frame.columns:
            parsed = pd.to_datetime(frame[candidate], errors="coerce", utc=True)
            if candidate != "game_date" and "game_date" not in frame.columns:
                frame["game_date"] = parsed.dt.strftime("%Y-%m-%d")
            elif candidate == "game_date":
                frame["game_date"] = parsed.dt.strftime("%Y-%m-%d")
    return frame

def build_layer(name: str, files: List[Path]) -> Tuple[pd.DataFrame, Dict]:
    frames = []
    errors = []
    for path in files:
        try:
            frames.append(read_source(path))
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})
    if not frames:
        return pd.DataFrame(), {"layer": name, "rows": 0, "columns": 0, "files": [], "errors": errors}
    frame = pd.concat(frames, ignore_index=True, sort=False)
    frame = normalize_dates(frame)
    keys = [key for key in KEY_CANDIDATES[name] if key in frame.columns]
    if keys:
        frame = frame.drop_duplicates(subset=keys + (["source_file"] if "source_file" in frame else []), keep="last")
    ordered = keys + sorted(col for col in frame.columns if col not in keys)
    frame = frame[ordered]
    coverage = {col: round(float(frame[col].notna().mean()), 6) for col in frame.columns}
    return frame, {
        "layer": name, "rows": int(len(frame)), "columns": int(len(frame.columns)),
        "files": [path.name for path in files], "keys_present": keys,
        "column_coverage": coverage, "errors": errors,
    }

def build(raw_dir: Path = RAW, out_dir: Path = OUT) -> Dict:
    global RAW, OUT, CATALOG
    RAW, OUT, CATALOG = raw_dir, out_dir, out_dir / "warehouse_catalog.json"
    OUT.mkdir(parents=True, exist_ok=True)
    layer_reports = {}
    total_rows = 0
    for name, patterns in LAYERS.items():
        files = discover(patterns)
        frame, report = build_layer(name, files)
        layer_reports[name] = report
        total_rows += report["rows"]
        frame.to_csv(OUT / f"{name}.csv", index=False)
    catalog = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warehouse_version": "sprint22_phase1_v1",
        "raw_directory": str(RAW), "output_directory": str(OUT),
        "layers": layer_reports, "total_rows": total_rows,
        "status": "PASS" if total_rows > 0 else "WARN",
        "next_sources": ["injuries", "lineups", "play_by_play", "referees", "travel_distance"],
    }
    CATALOG.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print("Sprint 22 Phase 1 warehouse:", {"total_rows": total_rows, "status": catalog["status"], "layers": {k:v["rows"] for k,v in layer_reports.items()}})
    return catalog

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=str(RAW)); parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(); build(Path(args.raw), Path(args.out))

if __name__ == "__main__": main()
