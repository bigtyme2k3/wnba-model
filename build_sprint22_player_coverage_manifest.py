"""Build an explicit coverage manifest for the Sprint 22 player warehouse."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/warehouse/sprint22/player/player_coverage_manifest.json")
VERIFIED_START = 2024
LEGACY_START = 2015
LEGACY_END = 2023


def main() -> None:
    seasons: dict[str, dict] = {}
    for path in sorted(RAW.glob("player_game_logs_*.csv")):
        try:
            season = int(path.stem.rsplit("_", 1)[-1])
            frame = pd.read_csv(path, low_memory=False)
        except Exception:
            continue
        rows = int(len(frame))
        if rows <= 0:
            continue
        seasons[str(season)] = {
            "rows": rows,
            "status": "VERIFIED" if season >= VERIFIED_START else "UNVERIFIED_LEGACY",
            "source_file": path.name,
        }

    verified = sorted(int(s) for s, v in seasons.items() if v["status"] == "VERIFIED")
    legacy_present = sorted(int(s) for s, v in seasons.items() if v["status"] == "UNVERIFIED_LEGACY")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_status": "PASS" if verified else "FAIL",
        "verified_seasons": verified,
        "verified_season_count": len(verified),
        "legacy_recovery_range": [LEGACY_START, LEGACY_END],
        "legacy_recovery_status": "IN_PROGRESS",
        "legacy_seasons_present_but_unverified": legacy_present,
        "seasons": seasons,
        "model_usage_policy": {
            "allow_verified": True,
            "allow_unverified_legacy": False,
            "minimum_verified_season": VERIFIED_START,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=2) + "\n")
    if not verified:
        raise SystemExit("No verified player seasons found")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
