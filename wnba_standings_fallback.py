"""Build WNBA standings from owned completed-game score files when primary standings are empty."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

OUT = Path("data/warehouse/wnba_standings.json")
DASH = Path("data/dashboard/wnba_standings.json")


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def team_name(row: dict[str, Any], side: str) -> str:
    for key in (f"{side}_team", side, f"{side}_name", f"team_{side}"):
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("name") or value.get("display_name")
        if str(value or "").strip():
            return str(value).strip()
    return ""


def score(row: dict[str, Any], side: str) -> float | None:
    for key in (f"{side}_score", f"{side}_points", f"score_{side}"):
        value = number(row.get(key))
        if value is not None:
            return value
    value = row.get(side)
    if isinstance(value, dict):
        return number(value.get("score") or value.get("points"))
    return None


def completed(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or row.get("state") or row.get("game_status") or "").upper()
    return status.endswith("FINAL") or status.startswith("FINAL") or status in {"COMPLETED", "POST"} or bool(row.get("final"))


def read_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    paths = sorted(Path("data/raw").glob("scores_*.csv")) + sorted(Path("data/raw").glob("wnba_scores*.csv"))
    for path in paths:
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows.extend(dict(row) for row in csv.DictReader(handle))
        except Exception:
            continue
    for path in (Path("data/dashboard/wnba_master.json"), Path("data/master/wnba_master.json")):
        try:
            payload = json.load(path.open(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("games"), list):
                rows.extend(x for x in payload["games"] if isinstance(x, dict))
        except Exception:
            pass
    return rows


def existing_valid() -> bool:
    try:
        payload = json.load(OUT.open(encoding="utf-8"))
        rows = payload.get("standings", payload) if isinstance(payload, dict) else payload
        return isinstance(rows, list) and len(rows) >= 10
    except Exception:
        return False


def build(force: bool = False) -> dict[str, Any]:
    if existing_valid() and not force:
        payload = json.load(OUT.open(encoding="utf-8"))
        print("Primary standings retained")
        return payload if isinstance(payload, dict) else {"standings": payload}

    records: dict[str, dict[str, Any]] = defaultdict(lambda: {"wins": 0, "losses": 0, "points_for": 0.0, "points_against": 0.0, "games": 0})
    seen: set[str] = set()
    for row in read_rows():
        away = team_name(row, "away")
        home = team_name(row, "home")
        away_score = score(row, "away")
        home_score = score(row, "home")
        if not away or not home or away_score is None or home_score is None:
            continue
        if not completed(row) and not (away_score > 0 and home_score > 0):
            continue
        game_id = str(row.get("game_id") or row.get("id") or f"{row.get('game_date') or row.get('date')}|{away}|{home}")
        if game_id in seen:
            continue
        seen.add(game_id)
        records[away]["games"] += 1
        records[home]["games"] += 1
        records[away]["points_for"] += away_score
        records[away]["points_against"] += home_score
        records[home]["points_for"] += home_score
        records[home]["points_against"] += away_score
        if away_score > home_score:
            records[away]["wins"] += 1
            records[home]["losses"] += 1
        elif home_score > away_score:
            records[home]["wins"] += 1
            records[away]["losses"] += 1

    standings = []
    for team, rec in records.items():
        games = rec["games"]
        if games <= 0:
            continue
        standings.append({
            "team": team,
            "wins": rec["wins"],
            "losses": rec["losses"],
            "win_pct": round(rec["wins"] / max(1, rec["wins"] + rec["losses"]), 4),
            "games": games,
            "points_for_avg": round(rec["points_for"] / games, 2),
            "points_against_avg": round(rec["points_against"] / games, 2),
            "net_points_avg": round((rec["points_for"] - rec["points_against"]) / games, 2),
            "source": "owned_score_files_fallback",
        })
    standings.sort(key=lambda x: (x["win_pct"], x["net_points_avg"]), reverse=True)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": str(date.today()),
        "status": "ok" if len(standings) >= 10 else "degraded",
        "summary": {"teams": len(standings), "games": len(seen), "source": "owned_score_files_fallback"},
        "standings": standings,
    }
    for path in (OUT, DASH):
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(payload, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print("Standings fallback:", payload["summary"])
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = build(args.force)
    if result.get("summary", {}).get("teams", 0) < 10:
        raise SystemExit("Insufficient team history to build trustworthy game projections")


if __name__ == "__main__":
    main()
