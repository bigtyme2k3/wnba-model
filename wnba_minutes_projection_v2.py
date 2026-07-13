"""Projection Engine v2 — player minutes foundation.

Builds transparent pregame minute distributions from the cumulative player-game
warehouse. The engine uses verified history first and only applies an adjustment
when its source is present. Missing factors remain neutral.

Outputs:
- data/warehouse/wnba_minutes_projection_v2.json
- data/dashboard/wnba_minutes_projection_v2.json
- projected minute fields attached to current master props
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

LOGS = Path("data/warehouse/wnba_player_game_logs.json")
MASTER_PATHS = [Path("data/dashboard/wnba_master.json"), Path("data/master/wnba_master.json")]
INJURY = Path("data/dashboard/wnba_injury_intelligence.json")
OUTS = [Path("data/warehouse/wnba_minutes_projection_v2.json"), Path("data/dashboard/wnba_minutes_projection_v2.json")]

STATUS_FACTORS = {"OUT": 0.0, "DOUBTFUL": 0.25, "QUESTIONABLE": 0.82, "GTD": 0.78, "PROBABLE": 0.96, "ACTIVE": 1.0, "BENEFICIARY": 1.0, "UNKNOWN": 0.92}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    location = (len(ordered) - 1) * probability
    lower = math.floor(location)
    upper = math.ceil(location)
    if lower == upper:
        return ordered[lower]
    weight = location - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def game_rows(master: dict[str, Any], target: str) -> list[dict[str, Any]]:
    rows = master.get("games", []) or master.get("today_games", []) or []
    return [row for row in rows if not str(row.get("game_date") or target)[:10] or str(row.get("game_date") or target)[:10] == target]


def team_context(master: dict[str, Any], target: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for game in game_rows(master, target):
        home = str(game.get("home_team") or game.get("home") or "").strip()
        away = str(game.get("away_team") or game.get("away") or "").strip()
        spread = num(game.get("spread") or game.get("consensus_spread") or game.get("home_spread"))
        blowout = num(game.get("blowout_probability") or game.get("blowout_risk"))
        if blowout is not None and blowout > 1:
            blowout /= 100.0
        if blowout is None and spread is not None:
            blowout = min(0.45, abs(spread) / 28.0)
        for team, opponent, home_away in ((home, away, "home"), (away, home, "away")):
            if team:
                output[norm(team)] = {"team": team, "opponent": opponent or None, "home_away": home_away, "spread": spread, "blowout_probability": blowout}
    return output


def injury_index() -> dict[str, dict[str, Any]]:
    payload = load(INJURY, {})
    output: dict[str, dict[str, Any]] = {}
    for row in payload.get("adjustments", []) if isinstance(payload, dict) else []:
        if isinstance(row, dict) and row.get("player"):
            output[norm(row.get("player"))] = row
    return output


def history_index() -> dict[str, list[dict[str, Any]]]:
    payload = load(LOGS, {"records": []})
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("records", []):
        if not isinstance(row, dict) or not row.get("player"):
            continue
        minutes = num(row.get("minutes"))
        if minutes is None or minutes <= 0 or row.get("did_not_play") is True:
            continue
        output[norm(row.get("player"))].append(row)
    for rows in output.values():
        rows.sort(key=lambda row: (str(row.get("game_date") or ""), str(row.get("game_id") or row.get("game") or "")), reverse=True)
    return output


def rest_days(rows: list[dict[str, Any]], target: str) -> int | None:
    try:
        target_date = datetime.fromisoformat(target).date()
    except Exception:
        return None
    for row in rows:
        try:
            played = datetime.fromisoformat(str(row.get("game_date"))[:10]).date()
            return max(0, (target_date - played).days - 1)
        except Exception:
            continue
    return None


def weighted_baseline(minutes: list[float]) -> tuple[float, dict[str, Any]]:
    season = average(minutes)
    l10 = average(minutes[:10])
    l5 = average(minutes[:5])
    l3 = average(minutes[:3])
    available = [(season, 0.20), (l10, 0.25), (l5, 0.35), (l3, 0.20)]
    valid = [(value, weight) for value, weight in available if value is not None]
    total_weight = sum(weight for _, weight in valid) or 1.0
    baseline = sum(value * weight for value, weight in valid) / total_weight
    return baseline, {
        "season_average": round(season, 2) if season is not None else None,
        "l10_average": round(l10, 2) if l10 is not None else None,
        "l5_average": round(l5, 2) if l5 is not None else None,
        "l3_average": round(l3, 2) if l3 is not None else None,
        "games": len(minutes),
    }


def starter_profile(rows: list[dict[str, Any]]) -> tuple[bool | None, float]:
    recent = rows[:10]
    flags = [row.get("starter") for row in recent if row.get("starter") is not None]
    if not flags:
        return None, 0.0
    starter_rate = sum(bool(value) for value in flags) / len(flags)
    current = starter_rate >= 0.6
    adjustment = 1.2 if current and starter_rate >= 0.8 else -1.0 if not current and starter_rate <= 0.2 else 0.0
    return current, adjustment


def home_away_adjustment(rows: list[dict[str, Any]], home_away: str | None) -> tuple[float, dict[str, Any]]:
    if not home_away:
        return 0.0, {"sample": 0, "average": None}
    matching = [num(row.get("minutes")) for row in rows if str(row.get("home_away") or "").lower() == home_away]
    matching = [value for value in matching if value is not None]
    all_minutes = [num(row.get("minutes")) for row in rows]
    all_minutes = [value for value in all_minutes if value is not None]
    if len(matching) < 5 or not all_minutes:
        return 0.0, {"sample": len(matching), "average": round(average(matching), 2) if matching else None}
    delta = clamp((average(matching) or 0) - (average(all_minutes) or 0), -1.5, 1.5)
    return delta, {"sample": len(matching), "average": round(average(matching), 2)}


def project_player(player: str, rows: list[dict[str, Any]], target: str, context: dict[str, Any], injury: dict[str, Any] | None) -> dict[str, Any]:
    minute_values = [num(row.get("minutes")) for row in rows]
    minute_values = [value for value in minute_values if value is not None and value > 0]
    baseline, samples = weighted_baseline(minute_values)
    starter, role_adjustment = starter_profile(rows)
    home_adj, split = home_away_adjustment(rows, context.get("home_away"))
    rest = rest_days(rows, target)
    rest_adjustment = -1.0 if rest == 0 else 0.35 if rest is not None and rest >= 2 else 0.0
    blowout = num(context.get("blowout_probability"))
    blowout_adjustment = -4.0 * blowout if blowout is not None else 0.0

    status = str((injury or {}).get("severity") or "ACTIVE").upper()
    injury_adjustment = 0.0
    beneficiary_adjustment = 0.0
    if injury:
        supplied = num(injury.get("projected_minutes"))
        minutes_delta = num(injury.get("minutes_delta"))
        if status == "BENEFICIARY" and minutes_delta is not None:
            beneficiary_adjustment = clamp(minutes_delta, 0.0, 5.0)
        elif supplied is not None:
            injury_adjustment = supplied - baseline
        else:
            injury_adjustment = baseline * (STATUS_FACTORS.get(status, STATUS_FACTORS["UNKNOWN"]) - 1.0)

    raw_projection = baseline + role_adjustment + home_adj + rest_adjustment + blowout_adjustment + injury_adjustment + beneficiary_adjustment
    median = clamp(raw_projection, 0.0, 40.0)

    recent = minute_values[:10]
    observed_stdev = statistics.pstdev(recent) if len(recent) >= 2 else 4.5
    uncertainty = clamp(observed_stdev, 2.0, 8.0)
    if status in {"QUESTIONABLE", "GTD", "DOUBTFUL", "UNKNOWN"}:
        uncertainty += 2.0
    if starter is None:
        uncertainty += 0.8
    if len(recent) < 5:
        uncertainty += 1.2
    uncertainty = clamp(uncertainty, 2.0, 10.0)

    p10 = clamp(median - 1.2816 * uncertainty, 0.0, 40.0)
    p90 = clamp(median + 1.2816 * uncertainty, 0.0, 40.0)
    if status == "OUT":
        p10 = median = p90 = 0.0

    confidence = 42.0
    confidence += min(25.0, len(minute_values) * 1.5)
    confidence += 10.0 if len(recent) >= 10 else 5.0 if len(recent) >= 5 else 0.0
    confidence += 8.0 if starter is not None else 0.0
    confidence += clamp(12.0 - uncertainty, 0.0, 10.0)
    confidence -= {"OUT": 0, "DOUBTFUL": 30, "QUESTIONABLE": 18, "GTD": 22, "PROBABLE": 5, "UNKNOWN": 10}.get(status, 0)
    if context.get("blowout_probability") is None:
        confidence -= 3
    confidence = clamp(confidence, 0.0, 100.0)

    reasons = [
        f"Weighted baseline {baseline:.1f} from {len(minute_values)} games",
        f"L5 minutes {samples['l5_average']:.1f}" if samples.get("l5_average") is not None else "L5 minutes unavailable",
    ]
    if role_adjustment:
        reasons.append(f"Recent role adjustment {role_adjustment:+.1f}")
    if home_adj:
        reasons.append(f"{context.get('home_away','split').title()} split adjustment {home_adj:+.1f}")
    if rest_adjustment:
        reasons.append(f"Rest adjustment {rest_adjustment:+.1f}")
    if blowout_adjustment:
        reasons.append(f"Blowout adjustment {blowout_adjustment:+.1f}")
    if injury_adjustment:
        reasons.append(f"{status} availability adjustment {injury_adjustment:+.1f}")
    if beneficiary_adjustment:
        reasons.append(f"Injury redistribution boost {beneficiary_adjustment:+.1f}")

    data_status = "complete" if len(minute_values) >= 10 and starter is not None else "partial" if len(minute_values) >= 3 else "limited"
    if status in {"QUESTIONABLE", "GTD", "DOUBTFUL", "UNKNOWN"}:
        data_status = "volatile"

    latest = rows[0] if rows else {}
    return {
        "player": player,
        "team": latest.get("team"),
        "opponent": context.get("opponent"),
        "home_away": context.get("home_away"),
        "starter_projection": starter,
        "injury_status": status,
        "rest_days": rest,
        "projected_minutes": round(median, 1),
        "minutes_p10": round(p10, 1),
        "minutes_p50": round(median, 1),
        "minutes_p90": round(p90, 1),
        "minutes_uncertainty": round(uncertainty, 2),
        "confidence": round(confidence, 1),
        "data_quality_status": data_status,
        "samples": samples,
        "adjustments": {
            "role": round(role_adjustment, 2),
            "home_away": round(home_adj, 2),
            "rest": round(rest_adjustment, 2),
            "blowout": round(blowout_adjustment, 2),
            "injury": round(injury_adjustment, 2),
            "teammate_availability": round(beneficiary_adjustment, 2),
        },
        "context": {**context, "home_away_split": split},
        "reasons": reasons[:8],
        "source": "player_game_log_warehouse+injury_intelligence+game_market_context",
    }


def attach_to_master(projections: dict[str, dict[str, Any]]) -> int:
    attached = 0
    for path in MASTER_PATHS:
        master = load(path, {})
        if not master:
            continue
        props = []
        for prop in master.get("props", []) or []:
            row = dict(prop)
            projection = projections.get(norm(row.get("player")))
            if projection:
                row["minutes_projection_v2"] = projection
                row["projected_minutes"] = projection["projected_minutes"]
                row["minutes_floor"] = projection["minutes_p10"]
                row["minutes_median"] = projection["minutes_p50"]
                row["minutes_ceiling"] = projection["minutes_p90"]
                row["minutes_confidence"] = projection["confidence"]
                row["minutes_data_quality"] = projection["data_quality_status"]
                attached += 1
            props.append(row)
        master["props"] = props
        master["minutes_projection_v2"] = {
            "summary": {"players": len(projections), "props_attached": sum(1 for row in props if row.get("minutes_projection_v2"))},
            "source": "data/dashboard/wnba_minutes_projection_v2.json",
        }
        dump(path, master)
    return attached


def build(target: str) -> dict[str, Any]:
    master = next((load(path, {}) for path in MASTER_PATHS if path.exists()), {})
    histories = history_index()
    injuries = injury_index()
    contexts = team_context(master, target)
    current_players: dict[str, str] = {}
    for prop in master.get("props", []) or []:
        if prop.get("player"):
            current_players[norm(prop.get("player"))] = str(prop.get("player"))
    if not current_players:
        current_players = {key: rows[0].get("player") for key, rows in histories.items() if rows}

    projections: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for key, display_name in current_players.items():
        rows = histories.get(key, [])
        if len(rows) < 1:
            continue
        team = str(rows[0].get("team") or "")
        context = contexts.get(norm(team), {"team": team, "opponent": None, "home_away": None, "spread": None, "blowout_probability": None})
        projection = project_player(display_name, rows, target, context, injuries.get(key))
        projections.append(projection)
        by_key[key] = projection

    projections.sort(key=lambda row: (row["team"] or "", -row["projected_minutes"], row["player"]))
    attached = attach_to_master(by_key)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "schema_version": "2.0",
        "summary": {
            "players_projected": len(projections),
            "props_attached": attached,
            "complete": sum(row["data_quality_status"] == "complete" for row in projections),
            "partial": sum(row["data_quality_status"] == "partial" for row in projections),
            "limited": sum(row["data_quality_status"] == "limited" for row in projections),
            "volatile": sum(row["data_quality_status"] == "volatile" for row in projections),
            "out": sum(row["injury_status"] == "OUT" for row in projections),
        },
        "projections": projections,
        "methodology": {
            "baseline_weights": {"season": 0.20, "last10": 0.25, "last5": 0.35, "last3": 0.20},
            "percentiles": "empirical recent-minute volatility around adjusted median",
            "availability_policy": "verified injury adjustment only; missing injury data is not treated as favorable",
            "blowout_policy": "penalty only when spread or blowout probability is supplied",
            "minute_bounds": [0, 40],
            "purpose": "foundation input for Projection Engine v2 stat-rate models",
        },
    }
    for path in OUTS:
        dump(path, report)
    print("Minutes Projection v2:", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
