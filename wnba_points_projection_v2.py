"""Projection Engine v2 — points, shot distribution, simulation, and market edge.

The engine combines verified player-game history with Minutes Projection v2.
It estimates scoring rates and shot mix, applies only documented context, runs
10,000 deterministic simulations, and compares each current points line to the
simulated distribution.

Missing data is neutral and explicitly reported. Market prices are used only for
comparison; they do not move the basketball projection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

LOGS = Path("data/warehouse/wnba_player_game_logs.json")
MINUTES = Path("data/dashboard/wnba_minutes_projection_v2.json")
MASTER_PATHS = [Path("data/dashboard/wnba_master.json"), Path("data/master/wnba_master.json")]
PACE_RANKS = Path("data/dashboard/wnba_pace_minutes_opponent_rankings.json")
OUTS = [Path("data/warehouse/wnba_points_projection_v2.json"), Path("data/dashboard/wnba_points_projection_v2.json")]
SIMULATIONS = 10_000


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


def avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def weighted(values: list[float]) -> float | None:
    if not values:
        return None
    windows = [(values, 0.20), (values[:10], 0.25), (values[:5], 0.35), (values[:3], 0.20)]
    valid = [(avg(window), weight) for window, weight in windows if window]
    total = sum(weight for value, weight in valid if value is not None) or 1.0
    return sum((value or 0) * weight for value, weight in valid if value is not None) / total


def percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[low]
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def implied_probability(odds: Any) -> float | None:
    price = num(odds)
    if price is None or price == 0:
        return None
    return (-price / (-price + 100.0)) if price < 0 else 100.0 / (price + 100.0)


def decimal_odds(odds: Any) -> float | None:
    price = num(odds)
    if price is None or price == 0:
        return None
    return 1.0 + (100.0 / -price if price < 0 else price / 100.0)


def kelly(probability: float | None, odds: Any) -> float | None:
    decimal = decimal_odds(odds)
    if probability is None or decimal is None or decimal <= 1:
        return None
    b = decimal - 1.0
    q = 1.0 - probability
    return clamp((b * probability - q) / b, 0.0, 1.0)


def position_group(value: Any) -> str | None:
    text = str(value or "").strip().upper().replace(" ", "")
    if not text:
        return None
    if text.startswith("G") or "GUARD" in text:
        return "G"
    if text.startswith("F") or "FORWARD" in text:
        return "F"
    if text.startswith("C") or "CENTER" in text:
        return "C"
    return None


def history_index() -> dict[str, list[dict[str, Any]]]:
    payload = load(LOGS, {"records": []})
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("records", []):
        if not isinstance(row, dict) or not row.get("player"):
            continue
        minutes = num(row.get("minutes"))
        points = num(row.get("scoring", {}).get("total_pts"))
        if minutes is None or minutes <= 0 or points is None or row.get("did_not_play") is True:
            continue
        output[norm(row.get("player"))].append(row)
    for rows in output.values():
        rows.sort(key=lambda row: (str(row.get("game_date") or ""), str(row.get("game_id") or row.get("game") or "")), reverse=True)
    return output


def minute_index() -> dict[str, dict[str, Any]]:
    payload = load(MINUTES, {"projections": []})
    return {norm(row.get("player")): row for row in payload.get("projections", []) if isinstance(row, dict) and row.get("player")}


def matchup_index() -> dict[tuple[str, str], dict[str, Any]]:
    payload = load(PACE_RANKS, {"rankings": []})
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("rankings", []):
        if not isinstance(row, dict) or str(row.get("stat")) != "PTS":
            continue
        output[(norm(row.get("team")), str(row.get("position_group") or ""))] = row
    return output


def row_rates(row: dict[str, Any]) -> dict[str, float | None]:
    minutes = num(row.get("minutes"))
    scoring = row.get("scoring", {}) if isinstance(row.get("scoring"), dict) else {}
    if minutes is None or minutes <= 0:
        return {}
    points = num(scoring.get("total_pts")) or 0.0
    fgm = num(scoring.get("fgm"))
    fga = num(scoring.get("fga"))
    three_m = num(scoring.get("three_pm"))
    three_a = num(scoring.get("three_pa"))
    ftm = num(scoring.get("ftm"))
    fta = num(scoring.get("fta"))
    two_m = (fgm - three_m) if fgm is not None and three_m is not None else None
    two_a = (fga - three_a) if fga is not None and three_a is not None else None
    return {
        "ppm": points / minutes,
        "fga_pm": fga / minutes if fga is not None else None,
        "two_a_pm": two_a / minutes if two_a is not None else None,
        "three_a_pm": three_a / minutes if three_a is not None else None,
        "fta_pm": fta / minutes if fta is not None else None,
        "two_pct": two_m / two_a if two_m is not None and two_a and two_a > 0 else None,
        "three_pct": three_m / three_a if three_m is not None and three_a and three_a > 0 else None,
        "ft_pct": ftm / fta if ftm is not None and fta and fta > 0 else None,
    }


def rate_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    profiles = [row_rates(row) for row in rows]
    output: dict[str, Any] = {}
    defaults = {"ppm": 0.42, "fga_pm": 0.35, "two_a_pm": 0.20, "three_a_pm": 0.13, "fta_pm": 0.10, "two_pct": 0.48, "three_pct": 0.33, "ft_pct": 0.78}
    for field, default in defaults.items():
        values = [num(profile.get(field)) for profile in profiles]
        values = [value for value in values if value is not None and value >= 0]
        output[field] = weighted(values) if values else default
        output[f"{field}_samples"] = len(values)
    ppm_values = [num(profile.get("ppm")) for profile in profiles[:10]]
    ppm_values = [value for value in ppm_values if value is not None]
    output["ppm_stdev"] = statistics.pstdev(ppm_values) if len(ppm_values) >= 2 else 0.18
    output["games"] = len(rows)
    return output


def matchup_adjustment(minutes: dict[str, Any], latest: dict[str, Any], matchups: dict[tuple[str, str], dict[str, Any]]) -> tuple[float, dict[str, Any] | None]:
    opponent = norm(minutes.get("opponent"))
    position = position_group(latest.get("position"))
    ranking = matchups.get((opponent, position or ""))
    if not ranking:
        return 0.0, None
    adjusted = num(ranking.get("pace_minutes_adjusted_average_allowed"))
    raw = num(ranking.get("raw_average_allowed"))
    if adjusted is None or raw is None or raw <= 0:
        return 0.0, ranking
    ratio = clamp(adjusted / raw, 0.88, 1.12)
    return ratio - 1.0, ranking


def projection_for_player(player: str, rows: list[dict[str, Any]], minute: dict[str, Any], matchups: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    profile = rate_profile(rows)
    latest = rows[0]
    projected_minutes = num(minute.get("projected_minutes")) or 0.0
    minutes_p10 = num(minute.get("minutes_p10")) or projected_minutes
    minutes_p90 = num(minute.get("minutes_p90")) or projected_minutes
    matchup_adj, ranking = matchup_adjustment(minute, latest, matchups)

    rest = num(minute.get("rest_days"))
    rest_adj = -0.025 if rest == 0 else 0.01 if rest is not None and rest >= 2 else 0.0
    home_adj = 0.012 if minute.get("home_away") == "home" else -0.006 if minute.get("home_away") == "away" else 0.0
    injury_status = str(minute.get("injury_status") or "ACTIVE").upper()
    efficiency_adj = -0.04 if injury_status in {"QUESTIONABLE", "GTD", "DOUBTFUL"} else 0.0
    total_rate_adjustment = clamp(matchup_adj + rest_adj + home_adj + efficiency_adj, -0.18, 0.18)

    ppm = float(profile["ppm"]) * (1.0 + total_rate_adjustment)
    median = clamp(projected_minutes * ppm, 0.0, 60.0)

    shot_distribution = {
        "two_point_attempts": round(projected_minutes * float(profile["two_a_pm"]), 2),
        "three_point_attempts": round(projected_minutes * float(profile["three_a_pm"]), 2),
        "free_throw_attempts": round(projected_minutes * float(profile["fta_pm"]), 2),
        "two_point_percentage": round(clamp(float(profile["two_pct"]), 0.20, 0.75), 4),
        "three_point_percentage": round(clamp(float(profile["three_pct"]), 0.15, 0.55), 4),
        "free_throw_percentage": round(clamp(float(profile["ft_pct"]), 0.45, 0.98), 4),
    }
    shot_points = (
        shot_distribution["two_point_attempts"] * shot_distribution["two_point_percentage"] * 2
        + shot_distribution["three_point_attempts"] * shot_distribution["three_point_percentage"] * 3
        + shot_distribution["free_throw_attempts"] * shot_distribution["free_throw_percentage"]
    )
    if profile["two_a_pm_samples"] + profile["three_a_pm_samples"] + profile["fta_pm_samples"] >= 10:
        median = 0.55 * median + 0.45 * shot_points

    seed = int(hashlib.sha256(f"{player}|{minute.get('opponent')}|points-v2".encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    simulations: list[float] = []
    ppm_sigma = clamp(float(profile["ppm_stdev"]), 0.08, 0.35)
    minute_sigma = max(1.0, (minutes_p90 - minutes_p10) / 2.5632)
    for _ in range(SIMULATIONS):
        sim_minutes = clamp(rng.gauss(projected_minutes, minute_sigma), 0.0, 40.0)
        sim_rate = max(0.0, rng.gauss(ppm, ppm_sigma))
        # Blend continuous rate variation with discrete shot-making variance.
        two_a = max(0, round(rng.gauss(sim_minutes * float(profile["two_a_pm"]), 1.2)))
        three_a = max(0, round(rng.gauss(sim_minutes * float(profile["three_a_pm"]), 1.1)))
        fta = max(0, round(rng.gauss(sim_minutes * float(profile["fta_pm"]), 1.0)))
        two_m = sum(rng.random() < shot_distribution["two_point_percentage"] for _ in range(two_a))
        three_m = sum(rng.random() < shot_distribution["three_point_percentage"] for _ in range(three_a))
        ftm = sum(rng.random() < shot_distribution["free_throw_percentage"] for _ in range(fta))
        shot_sim = two_m * 2 + three_m * 3 + ftm
        rate_sim = sim_minutes * sim_rate
        simulations.append(clamp(0.55 * shot_sim + 0.45 * rate_sim, 0.0, 65.0))
    simulations.sort()

    p10 = percentile(simulations, 0.10)
    p25 = percentile(simulations, 0.25)
    p50 = percentile(simulations, 0.50)
    p75 = percentile(simulations, 0.75)
    p90 = percentile(simulations, 0.90)
    mean = sum(simulations) / len(simulations)

    confidence = 35.0
    confidence += min(25.0, profile["games"] * 1.4)
    confidence += (num(minute.get("confidence")) or 50.0) * 0.25
    confidence += 8.0 if ranking else 0.0
    confidence += 8.0 if profile["fga_pm_samples"] >= 10 else 2.0
    if injury_status in {"QUESTIONABLE", "GTD", "DOUBTFUL", "UNKNOWN"}:
        confidence -= 12
    confidence = clamp(confidence, 0.0, 100.0)

    adjustments = {
        "minutes_vs_recent_baseline": round(projected_minutes - (num(profile.get("games")) and avg([num(row.get("minutes")) or 0 for row in rows[:5]]) or projected_minutes), 2),
        "matchup_rate_pct": round(matchup_adj * 100, 2),
        "rest_rate_pct": round(rest_adj * 100, 2),
        "home_away_rate_pct": round(home_adj * 100, 2),
        "availability_rate_pct": round(efficiency_adj * 100, 2),
    }
    reasons = [
        f"Projected minutes {projected_minutes:.1f} (P10 {minutes_p10:.1f}, P90 {minutes_p90:.1f})",
        f"Adjusted scoring rate {ppm:.3f} points/minute",
        f"Recent weighted scoring baseline {float(profile['ppm']):.3f} points/minute",
    ]
    if ranking:
        reasons.append(str(ranking.get("rank_label") or "Verified position matchup adjustment"))
    if rest_adj:
        reasons.append(f"Rest scoring-rate adjustment {rest_adj*100:+.1f}%")
    if home_adj:
        reasons.append(f"{str(minute.get('home_away')).title()} scoring-rate adjustment {home_adj*100:+.1f}%")
    if efficiency_adj:
        reasons.append(f"Availability uncertainty adjustment {efficiency_adj*100:+.1f}%")

    return {
        "player": player,
        "team": minute.get("team") or latest.get("team"),
        "opponent": minute.get("opponent"),
        "position_group": position_group(latest.get("position")),
        "projected_minutes": round(projected_minutes, 1),
        "projected_points": round(mean, 2),
        "points_p10": round(p10, 2),
        "points_p25": round(p25, 2),
        "points_p50": round(p50, 2),
        "points_p75": round(p75, 2),
        "points_p90": round(p90, 2),
        "median_projection": round(p50, 2),
        "floor_projection": round(p10, 2),
        "ceiling_projection": round(p90, 2),
        "scoring_rate_per_minute": round(ppm, 4),
        "shot_distribution": shot_distribution,
        "simulation_count": SIMULATIONS,
        "confidence": round(confidence, 1),
        "injury_status": injury_status,
        "data_quality_status": "complete" if profile["games"] >= 10 and minute.get("data_quality_status") == "complete" else "partial" if profile["games"] >= 5 else "limited",
        "adjustments": adjustments,
        "matchup_context": ranking,
        "reasons": reasons[:8],
        "simulation_values": simulations,
    }


def candidate_lines(prop: dict[str, Any]) -> list[dict[str, Any]]:
    stat = str(prop.get("stat") or "").upper().replace("POINTS", "PTS")
    if stat != "PTS":
        return []
    line = num(prop.get("line") or prop.get("alt_line"))
    candidates: list[dict[str, Any]] = []
    if line is not None:
        candidates.extend([
            {"side": "OVER", "line": line, "odds": prop.get("best_over_price") or prop.get("over_price") or prop.get("best_odds"), "book": prop.get("best_over_book") or prop.get("book") or prop.get("best_book")},
            {"side": "UNDER", "line": line, "odds": prop.get("best_under_price") or prop.get("under_price"), "book": prop.get("best_under_book") or prop.get("book")},
        ])
    if prop.get("side") and prop.get("alt_line") is not None:
        candidates.append({"side": str(prop.get("side")).upper(), "line": num(prop.get("alt_line")), "odds": prop.get("best_odds"), "book": prop.get("best_book")})
    unique: dict[tuple[str, float, str], dict[str, Any]] = {}
    for row in candidates:
        if row["line"] is None:
            continue
        unique[(row["side"], float(row["line"]), str(row.get("book") or ""))] = row
    return list(unique.values())


def market_comparison(projection: dict[str, Any], props: list[dict[str, Any]]) -> list[dict[str, Any]]:
    simulations = projection.pop("simulation_values")
    output: list[dict[str, Any]] = []
    for prop in props:
        for market in candidate_lines(prop):
            line = float(market["line"])
            side = market["side"]
            wins = sum(value > line for value in simulations) if side == "OVER" else sum(value < line for value in simulations)
            pushes = sum(round(value, 6) == round(line, 6) for value in simulations)
            probability = wins / len(simulations)
            implied = implied_probability(market.get("odds"))
            edge = None if implied is None else probability - implied
            decimal = decimal_odds(market.get("odds"))
            ev = None if decimal is None else probability * (decimal - 1.0) - (1.0 - probability)
            full_kelly = kelly(probability, market.get("odds"))
            output.append({
                "side": side,
                "line": line,
                "odds": num(market.get("odds")),
                "sportsbook": market.get("book"),
                "hit_probability": round(probability, 4),
                "push_probability": round(pushes / len(simulations), 4),
                "implied_probability": round(implied, 4) if implied is not None else None,
                "probability_edge": round(edge, 4) if edge is not None else None,
                "expected_value_per_unit": round(ev, 4) if ev is not None else None,
                "full_kelly_fraction": round(full_kelly, 4) if full_kelly is not None else None,
                "recommended_units": round(min(1.0, (full_kelly or 0.0) * 0.25 * 10), 2),
                "action": "BET" if ev is not None and ev >= 0.05 and probability >= 0.56 else "LEAN" if ev is not None and ev > 0 else "PASS",
            })
    output.sort(key=lambda row: (row.get("expected_value_per_unit") if row.get("expected_value_per_unit") is not None else -999, row["hit_probability"]), reverse=True)
    return output


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
            if projection and str(row.get("stat") or "").upper().replace("POINTS", "PTS") == "PTS":
                row["points_projection_v2"] = {key: value for key, value in projection.items() if key != "markets"}
                row["projection"] = projection["projected_points"]
                row["proj"] = projection["projected_points"]
                row["projection_floor"] = projection["points_p10"]
                row["projection_median"] = projection["points_p50"]
                row["projection_ceiling"] = projection["points_p90"]
                row["projection_confidence_v2"] = projection["confidence"]
                attached += 1
            props.append(row)
        master["props"] = props
        master["points_projection_v2"] = {"summary": {"players": len(projections), "props_attached": sum(1 for row in props if row.get("points_projection_v2"))}, "source": "data/dashboard/wnba_points_projection_v2.json"}
        dump(path, master)
    return attached


def build(target: str) -> dict[str, Any]:
    histories = history_index()
    minutes = minute_index()
    matchups = matchup_index()
    master = next((load(path, {}) for path in MASTER_PATHS if path.exists()), {})
    props_by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prop in master.get("props", []) or []:
        if prop.get("player"):
            props_by_player[norm(prop.get("player"))].append(prop)

    projections: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for key, minute in minutes.items():
        rows = histories.get(key, [])
        if not rows:
            continue
        projection = projection_for_player(str(minute.get("player")), rows, minute, matchups)
        projection["markets"] = market_comparison(projection, props_by_player.get(key, []))
        projections.append(projection)
        by_key[key] = projection
    projections.sort(key=lambda row: (row["team"] or "", -row["projected_points"], row["player"]))
    attached = attach_to_master(by_key)
    all_markets = [market for projection in projections for market in projection.get("markets", [])]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": "ok",
        "schema_version": "2.0",
        "summary": {
            "players_projected": len(projections),
            "props_attached": attached,
            "simulations_per_player": SIMULATIONS,
            "market_comparisons": len(all_markets),
            "bet_markets": sum(row.get("action") == "BET" for row in all_markets),
            "lean_markets": sum(row.get("action") == "LEAN" for row in all_markets),
            "complete": sum(row["data_quality_status"] == "complete" for row in projections),
            "partial": sum(row["data_quality_status"] == "partial" for row in projections),
            "limited": sum(row["data_quality_status"] == "limited" for row in projections),
        },
        "projections": projections,
        "top_market_edges": sorted(all_markets, key=lambda row: row.get("expected_value_per_unit") if row.get("expected_value_per_unit") is not None else -999, reverse=True)[:20],
        "methodology": {
            "minutes_source": "Minutes Projection v2",
            "rate_baseline_weights": {"season": 0.20, "last10": 0.25, "last5": 0.35, "last3": 0.20},
            "shot_model": "2PA, 3PA, and FTA per minute with player shooting percentages",
            "simulation": "10,000 deterministic player-level simulations combining minute, scoring-rate, and shot-making variation",
            "market_policy": "sportsbook lines and prices are comparison inputs only; they do not alter the projection",
            "missing_data_policy": "neutral documented defaults and explicit quality status",
            "kelly_policy": "displayed units use quarter-Kelly and are capped at 1.0 unit",
        },
    }
    for path in OUTS:
        dump(path, report)
    print("Points Projection v2:", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    args = parser.parse_args()
    build(args.date)


if __name__ == "__main__":
    main()
