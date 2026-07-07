"""
wnba_player_intelligence.py
---------------------------
Builds the first canonical WNBA player intelligence database.

Sources:
- data/raw/wnba_players_live.json from stats.wnba.com scraper
- data/warehouse/wnba_injuries.json from sports-skills warehouse
- data/raw/player_points_<date>.csv or player_points_today.csv

Outputs:
- data/warehouse/wnba_player_intelligence.json
- data/dashboard/wnba_player_intelligence.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from typing import Any, Dict

import pandas as pd


def load_json(path: str, default: Any = None) -> Any:
    if default is None:
        default = {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return default
        return float(v)
    except Exception:
        return default


def load_points(target: str) -> pd.DataFrame:
    for path in [f"data/raw/player_points_{target}.csv", "data/raw/player_points_today.csv"]:
        if os.path.exists(path):
            try:
                return pd.read_csv(path)
            except Exception:
                pass
    return pd.DataFrame()


def injury_lookup() -> Dict[str, dict]:
    rows = load_json("data/warehouse/wnba_injuries.json", [])
    out = {}
    if isinstance(rows, list):
        for r in rows:
            name = str(r.get("player", "")).strip()
            if name:
                out[name.lower()] = r
    return out


def trend_label(season: float, recent: float) -> str:
    diff = recent - season
    if diff >= 3:
        return "UP"
    if diff <= -3:
        return "DOWN"
    return "STABLE"


def role_score(p: dict) -> float:
    mpg = safe_float(p.get("mpg"), 0)
    l5_mpg = safe_float(p.get("roll5_mpg"), mpg)
    usage = safe_float(p.get("usage"), 0.18)
    score = (mpg * 1.4) + (l5_mpg * 1.2) + (usage * 100)
    return round(max(0, min(100, score)), 1)


def build(target: str) -> dict:
    players = load_json("data/raw/wnba_players_live.json", {})
    injuries = injury_lookup()
    points = load_points(target)
    point_lookup = {}
    if not points.empty and "player" in points.columns:
        for _, row in points.iterrows():
            point_lookup[str(row.get("player", "")).lower()] = row.to_dict()

    records = []
    for name, p in players.items():
        key = str(name).lower()
        inj = injuries.get(key, {})
        pp = point_lookup.get(key, {})
        ppg = safe_float(p.get("ppg"), 0)
        r5 = safe_float(p.get("roll5_pts"), ppg)
        mpg = safe_float(p.get("mpg"), 0)
        r5_mpg = safe_float(p.get("roll5_mpg"), mpg)
        rec = {
            "player": name,
            "team": p.get("team"),
            "position": p.get("pos"),
            "season": {
                "gp": safe_float(p.get("gp"), 0),
                "ppg": ppg,
                "reb": safe_float(p.get("reb"), 0),
                "ast": safe_float(p.get("ast"), 0),
                "mpg": mpg,
                "usage": safe_float(p.get("usage"), 0),
                "ts_pct": safe_float(p.get("ts_pct"), safe_float(p.get("ts"), 0)),
            },
            "recent_form": {
                "last5_pts": r5,
                "last5_reb": safe_float(p.get("roll5_reb"), safe_float(p.get("reb"), 0)),
                "last5_ast": safe_float(p.get("roll5_ast"), safe_float(p.get("ast"), 0)),
                "last5_mpg": r5_mpg,
                "last5_threes": safe_float(p.get("roll5_threes"), 0),
                "points_trend": trend_label(ppg, r5),
                "minutes_trend": trend_label(mpg, r5_mpg),
            },
            "injury": {
                "status": str(inj.get("status", "ACTIVE")).upper() if inj else "ACTIVE",
                "detail": inj.get("detail") if inj else None,
                "source": inj.get("source") if inj else None,
            },
            "projection_snapshot": {
                "stat": pp.get("stat"),
                "line": pp.get("line"),
                "pred": pp.get("pred"),
                "signal": pp.get("signal"),
                "conf": pp.get("conf"),
                "market_status": pp.get("market_status"),
            },
            "intelligence": {
                "role_score": role_score(p),
                "is_rotation_core": role_score(p) >= 70,
                "is_recent_minutes_up": r5_mpg > mpg + 2,
                "is_recent_scoring_up": r5 > ppg + 2,
            },
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        records.append(rec)

    records.sort(key=lambda r: r["intelligence"]["role_score"], reverse=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "players": records,
        "summary": {
            "players": len(records),
            "injury_records_matched": sum(1 for r in records if r["injury"]["status"] != "ACTIVE"),
            "projection_records_matched": sum(1 for r in records if r["projection_snapshot"]["pred"] is not None),
            "core_rotation_players": sum(1 for r in records if r["intelligence"]["is_rotation_core"]),
        },
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    with open("data/warehouse/wnba_player_intelligence.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    with open("data/dashboard/wnba_player_intelligence.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    report = build(args.date)
    print(f"✅ Player intelligence built: {report['summary']}")


if __name__ == "__main__":
    main()
