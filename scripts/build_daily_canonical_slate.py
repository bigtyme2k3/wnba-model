from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "data" / "dashboard"
MANIFEST = DASH / "wnba_daily_canonical_manifest.json"


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run(script: str, target: str, required: bool = True) -> dict[str, Any]:
    path = ROOT / script
    if not path.exists():
        result = {"script": script, "status": "missing"}
        if required:
            raise SystemExit(f"Required generator missing: {script}")
        return result
    proc = subprocess.run(
        [sys.executable, str(path), "--date", target],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    result = {
        "script": script,
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }
    if proc.returncode and required:
        print(json.dumps(result, indent=2))
        raise SystemExit(f"Generator failed: {script}")
    return result


def rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    for key in ("rows", "props", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    target = args.date

    DASH.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []

    # The slate is always first. Every downstream source is required to agree
    # with this target date and its exact current-game set.
    steps.append(run("wnba_current_slate.py", target, required=True))
    master = load(DASH / "wnba_master.json", {})
    today_games = master.get("today_games") if isinstance(master, dict) else []
    if not isinstance(today_games, list):
        today_games = []
    games = [str(x.get("game") or "").strip() for x in today_games if isinstance(x, dict) and x.get("game")]
    teams = sorted({str(x.get(k) or "").strip() for x in today_games if isinstance(x, dict) for k in ("away_team", "home_team") if x.get(k)})

    # An empty slate must actively clear yesterday's props instead of leaving
    # stale rows available to the dashboard.
    if games:
        steps.append(run("wnba_player_props_ingestion.py", target, required=True))
    else:
        empty = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "target_date": target,
            "source": "confirmed_empty_slate",
            "event_count": 0,
            "row_count": 0,
            "rows": [],
        }
        dump(DASH / "wnba_player_props.json", empty)
        steps.append({"script": "wnba_player_props_ingestion.py", "status": "cleared_empty_slate"})

    props = load(DASH / "wnba_player_props.json", {})
    prop_rows = rows(props)
    stale_props = [r for r in prop_rows if str(r.get("target_date") or props.get("target_date") or "") != target]
    off_slate = [r for r in prop_rows if games and str(r.get("game") or "") not in games]
    missing_team = [r for r in prop_rows if not str(r.get("team") or "").strip()]

    failures: list[str] = []
    if master.get("target_date") != target:
        failures.append("master target_date mismatch")
    if props.get("target_date") != target:
        failures.append("player props target_date mismatch")
    if stale_props:
        failures.append(f"{len(stale_props)} stale player-prop rows")
    if off_slate:
        failures.append(f"{len(off_slate)} off-slate player-prop rows")
    if missing_team:
        failures.append(f"{len(missing_team)} player-prop rows missing team")
    if not games and prop_rows:
        failures.append("confirmed empty slate still contains player props")

    manifest = {
        "schema_version": "daily-canonical-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "PASS" if not failures else "FAIL",
        "games": games,
        "teams": teams,
        "game_count": len(games),
        "player_prop_rows": len(prop_rows),
        "sources": {
            "slate": "data/dashboard/wnba_master.json",
            "player_props": "data/dashboard/wnba_player_props.json",
        },
        "steps": steps,
        "failures": failures,
    }
    dump(MANIFEST, manifest)
    print(json.dumps(manifest, indent=2))
    if failures:
        raise SystemExit("Canonical daily build failed validation")


if __name__ == "__main__":
    main()
