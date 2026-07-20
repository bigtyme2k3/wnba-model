"""
Build the canonical WNBA player intelligence database with current injury status.
"""
from __future__ import annotations

import argparse
import json
import math
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
        value = float(v)
        return value if math.isfinite(value) else default
    except Exception:
        return default


def json_safe(value: Any) -> Any:
    """Recursively convert pandas/numpy/NaN values into strict JSON values."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def load_points(target: str) -> pd.DataFrame:
    for path in [f"data/raw/player_points_{target}.csv", "data/raw/player_points_today.csv"]:
        if os.path.exists(path):
            try:
                return pd.read_csv(path)
            except Exception:
                pass
    return pd.DataFrame()


def injury_lookup(target: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    rows = load_json("data/warehouse/wnba_injuries.json", [])
    if isinstance(rows, list):
        for row in rows:
            name = norm(row.get("player"))
            if name:
                out[name] = row
    for path in [f"data/raw/injuries_{target}.csv", "data/raw/injuries_today.csv"]:
        if not os.path.exists(path):
            continue
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        if "game_date" in frame.columns:
            frame = frame[frame["game_date"].astype(str).str[:10] == target]
        for row in frame.to_dict("records"):
            name = norm(row.get("player"))
            if name:
                out[name] = json_safe(row)
        if not frame.empty:
            break
    return out


def canonical_status(injury: dict[str, Any]) -> str:
    raw = str(injury.get("severity") or injury.get("status") or "ACTIVE").upper()
    for status in ["OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE", "AVAILABLE", "ACTIVE"]:
        if status in raw:
            return status
    return "UNKNOWN" if raw else "ACTIVE"


def trend_label(season: float, recent: float) -> str:
    diff = recent - season
    if diff >= 3:
        return "UP"
    if diff <= -3:
        return "DOWN"
    return "STABLE"


def role_score(player: dict) -> float:
    mpg = safe_float(player.get("mpg"), 0)
    l5_mpg = safe_float(player.get("roll5_mpg"), mpg)
    usage = safe_float(player.get("usage"), 0.18)
    if usage <= 1:
        usage *= 100
    score = (mpg * 1.4) + (l5_mpg * 1.2) + usage
    return round(max(0, min(100, score)), 1)


def build(target: str) -> dict:
    players = load_json("data/raw/wnba_players_live.json", {})
    injuries = injury_lookup(target)
    injury_intelligence = load_json("data/warehouse/wnba_injury_intelligence.json", {})
    adjustment_map = {norm(row.get("player")): row for row in injury_intelligence.get("adjustments", []) if row.get("player")}
    points = load_points(target)
    point_lookup = {}
    if not points.empty and "player" in points.columns:
        for _, row in points.iterrows():
            point_lookup[norm(row.get("player"))] = json_safe(row.to_dict())

    records = []
    for name, player in players.items():
        if not isinstance(player, dict):
            continue
        key = norm(name)
        injury = injuries.get(key, {})
        adjustment = adjustment_map.get(key, {})
        point = point_lookup.get(key, {})
        ppg = safe_float(player.get("ppg"), 0)
        recent_points = safe_float(player.get("roll5_pts"), ppg)
        mpg = safe_float(player.get("mpg"), 0)
        recent_mpg = safe_float(player.get("roll5_mpg"), mpg)
        status = str(adjustment.get("severity") or canonical_status(injury)).upper()
        record = {
            "player": name,
            "team": player.get("team"),
            "position": player.get("pos"),
            "season": {
                "gp": safe_float(player.get("gp"), 0), "ppg": ppg,
                "reb": safe_float(player.get("reb"), safe_float(player.get("rpg"), 0)),
                "ast": safe_float(player.get("ast"), safe_float(player.get("apg"), 0)),
                "mpg": mpg, "usage": safe_float(player.get("usage"), 0),
                "ts_pct": safe_float(player.get("ts_pct"), safe_float(player.get("ts"), 0)),
            },
            "recent_form": {
                "last5_pts": recent_points,
                "last5_reb": safe_float(player.get("roll5_reb"), safe_float(player.get("reb"), safe_float(player.get("rpg"), 0))),
                "last5_ast": safe_float(player.get("roll5_ast"), safe_float(player.get("ast"), safe_float(player.get("apg"), 0))),
                "last5_mpg": recent_mpg,
                "last5_threes": safe_float(player.get("roll5_threes"), 0),
                "points_trend": trend_label(ppg, recent_points), "minutes_trend": trend_label(mpg, recent_mpg),
            },
            "injury": {
                "status": status,
                "detail": adjustment.get("detail") or injury.get("detail"),
                "source": adjustment.get("source") or injury.get("source"),
                "projected_minutes": safe_float(adjustment.get("projected_minutes"), 0) if adjustment.get("projected_minutes") is not None else None,
                "minutes_delta": safe_float(adjustment.get("minutes_delta"), 0) if adjustment.get("minutes_delta") is not None else None,
                "projection_factor": safe_float(adjustment.get("projection_factor"), 1) if adjustment.get("projection_factor") is not None else None,
                "confidence_penalty": safe_float(adjustment.get("confidence_penalty"), 0),
                "is_out": bool(adjustment.get("is_out")) or status in {"OUT", "DOUBTFUL"},
                "updated_at_utc": adjustment.get("updated_at_utc") or injury.get("scraped_at"),
            },
            "projection_snapshot": {
                "stat": point.get("stat"), "line": point.get("line"), "pred": point.get("pred"),
                "signal": point.get("signal"), "conf": point.get("conf"), "market_status": point.get("market_status"),
            },
            "intelligence": {
                "role_score": role_score(player), "is_rotation_core": role_score(player) >= 70,
                "is_recent_minutes_up": recent_mpg > mpg + 2, "is_recent_scoring_up": recent_points > ppg + 2,
                "injury_available": status not in {"OUT", "DOUBTFUL"},
            },
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        records.append(json_safe(record))

    records.sort(key=lambda row: row["intelligence"]["role_score"], reverse=True)
    report = json_safe({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target, "players": records,
        "summary": {
            "players": len(records),
            "injury_records_matched": sum(1 for row in records if row["injury"]["status"] not in {"ACTIVE", "AVAILABLE"}),
            "out_or_doubtful": sum(1 for row in records if row["injury"]["status"] in {"OUT", "DOUBTFUL"}),
            "questionable": sum(1 for row in records if row["injury"]["status"] == "QUESTIONABLE"),
            "projection_records_matched": sum(1 for row in records if row["projection_snapshot"]["pred"] is not None),
            "core_rotation_players": sum(1 for row in records if row["intelligence"]["is_rotation_core"]),
        },
    })
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for path in ["data/warehouse/wnba_player_intelligence.json", "data/dashboard/wnba_player_intelligence.json"]:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    print(f"Player intelligence built: {build(args.date)['summary']}")


if __name__ == "__main__":
    main()
