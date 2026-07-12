"""Score ALT Streak candidates with transparent, bounded components.

The engine never invents missing inputs. Unavailable factors receive a neutral
score and are marked in the explanation. Final score weights:
- Trend: 30%
- Matchup: 20%
- Player form: 20%
- Market value: 15%
- Risk: 15%

Scores are descriptive ranking aids, not guarantees of profitability.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ALT_PATHS = [Path("data/warehouse/wnba_alt_streaks.json"), Path("data/dashboard/wnba_alt_streaks.json")]
WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")

WEIGHTS = {"trend": 0.30, "matchup": 0.20, "form": 0.20, "market": 0.15, "risk": 0.15}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def pct_score(value: Any, neutral: float = 50.0) -> float:
    n = num(value)
    return neutral if n is None else clamp(n * 100.0)


def american_implied(odds: Any) -> float | None:
    n = num(odds)
    if n is None or n == 0:
        return None
    return (-n / (-n + 100.0)) if n < 0 else (100.0 / (n + 100.0))


def grade(score: float) -> tuple[str, str, str]:
    if score >= 90: return "A+", "Elite", "BET"
    if score >= 85: return "A", "High", "BET"
    if score >= 80: return "B+", "Strong", "LEAN"
    if score >= 75: return "B", "Above Average", "LEAN"
    if score >= 70: return "C+", "Moderate", "WATCH"
    if score >= 60: return "C", "Small Edge", "WATCH"
    return "D", "Low", "PASS"


def minutes_profile(records: list[dict[str, Any]]) -> dict[str, Any]:
    values = [num(r.get("minutes")) for r in records[:10]]
    values = [v for v in values if v is not None and v > 0]
    if not values:
        return {"average": None, "stdev": None, "stability_score": 50.0, "samples": 0}
    average = sum(values) / len(values)
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    cv = stdev / average if average > 0 else 1.0
    stability = clamp(100.0 - cv * 220.0)
    return {"average": round(average, 2), "stdev": round(stdev, 2), "stability_score": round(stability, 1), "samples": len(values)}


def trend_component(row: dict[str, Any]) -> tuple[float, list[str]]:
    l5 = pct_score(row.get("l5_pct"))
    l10 = pct_score(row.get("l10_pct"))
    season = pct_score(row.get("season_pct"))
    streak = clamp((num(row.get("streak")) or 0) / 10.0 * 100.0)
    score = 0.30 * l5 + 0.30 * l10 + 0.25 * season + 0.15 * streak
    reasons = [
        f"L5 {row.get('l5_hits','—')}/{row.get('l5_games','—')}",
        f"L10 {row.get('l10_hits','—')}/{row.get('l10_games','—')}",
        f"Season {row.get('season_hits','—')}/{row.get('season_games','—')}",
        f"Current streak {row.get('streak','—')}",
    ]
    return round(score, 1), reasons


def matchup_component(row: dict[str, Any]) -> tuple[float, list[str]]:
    rank = num(row.get("opponent_rank"))
    teams = num(row.get("opponent_rank_total_teams"))
    if rank is None or teams is None or teams <= 1:
        return 50.0, ["Opponent rank unavailable; neutral matchup score"]
    score = clamp((teams - rank) / (teams - 1) * 100.0)
    source = str(row.get("opponent_rank_source") or "verified ranking")
    return round(score, 1), [str(row.get("opponent_label") or f"Rank {int(rank)} of {int(teams)}"), f"Source: {source}"]


def form_component(row: dict[str, Any], profile: dict[str, Any]) -> tuple[float, list[str]]:
    recent = [num(v) for v in row.get("recent_values", [])]
    recent = [v for v in recent if v is not None]
    line = num(row.get("alt_line"))
    side = str(row.get("side") or "OVER").upper()
    if recent and line is not None:
        l3 = recent[:3]
        avg3 = sum(l3) / len(l3)
        avg5_values = recent[:5]
        avg5 = sum(avg5_values) / len(avg5_values)
        margin3 = (avg3 - line) if side == "OVER" else (line - avg3)
        margin5 = (avg5 - line) if side == "OVER" else (line - avg5)
        scale = max(abs(line), 5.0)
        margin_score = clamp(50.0 + ((margin3 + margin5) / 2.0) / scale * 120.0)
    else:
        avg3 = avg5 = None
        margin_score = 50.0
    stability = float(profile.get("stability_score") or 50.0)
    score = 0.65 * margin_score + 0.35 * stability
    reasons = [
        f"L3 average {avg3:.2f}" if avg3 is not None else "L3 average unavailable",
        f"L5 average {avg5:.2f}" if avg5 is not None else "L5 average unavailable",
        f"Minutes stability {stability:.0f}/100",
    ]
    return round(score, 1), reasons


def market_component(row: dict[str, Any]) -> tuple[float, list[str], float | None]:
    recent = [num(v) for v in row.get("recent_values", [])]
    recent = [v for v in recent if v is not None]
    line = num(row.get("alt_line"))
    side = str(row.get("side") or "OVER").upper()
    implied = american_implied(row.get("best_odds"))
    empirical = num(row.get("l10_pct")) or num(row.get("season_pct"))
    edge = None if implied is None or empirical is None else empirical - implied
    if recent and line is not None:
        avg = sum(recent) / len(recent)
        margin = (avg - line) if side == "OVER" else (line - avg)
        line_score = clamp(50.0 + margin / max(abs(line), 5.0) * 120.0)
    else:
        margin = None
        line_score = 50.0
    edge_score = 50.0 if edge is None else clamp(50.0 + edge * 200.0)
    score = 0.55 * line_score + 0.45 * edge_score
    reasons = [
        f"Recent average margin {margin:+.2f} vs line" if margin is not None else "Line margin unavailable",
        f"Implied probability {implied*100:.1f}%" if implied is not None else "Implied probability unavailable",
        f"Empirical-minus-implied edge {edge*100:+.1f}%" if edge is not None else "Market edge unavailable",
    ]
    return round(score, 1), reasons, edge


def risk_component(row: dict[str, Any], profile: dict[str, Any]) -> tuple[float, list[str]]:
    # Higher is safer. Unknown fields are neutral, not assumed healthy.
    score = 70.0
    reasons: list[str] = []
    stability = float(profile.get("stability_score") or 50.0)
    score += (stability - 50.0) * 0.25
    injury = str(row.get("injury_status") or "UNKNOWN").upper()
    if injury in {"OUT", "DOUBTFUL"}:
        score -= 50; reasons.append(f"Injury status {injury}")
    elif injury in {"QUESTIONABLE", "PROBABLE"}:
        score -= 18 if injury == "QUESTIONABLE" else 6; reasons.append(f"Injury status {injury}")
    else:
        reasons.append("Injury status unavailable/clear; no positive bonus")
    rest = num(row.get("rest_days"))
    if rest is not None:
        if rest <= 0: score -= 12; reasons.append("Back-to-back or zero rest")
        elif rest >= 2: score += 5; reasons.append(f"Rest days {int(rest)}")
    else:
        reasons.append("Rest data unavailable")
    foul_rate = num(row.get("fouls_per_minute"))
    if foul_rate is not None and foul_rate > 0.14:
        score -= 10; reasons.append("Elevated foul rate")
    else:
        reasons.append("No verified elevated foul-risk signal")
    return round(clamp(score), 1), reasons


def main() -> None:
    warehouse = load(WAREHOUSE, {"records": []})
    by_player: dict[str, list[dict[str, Any]]] = {}
    for record in warehouse.get("records", []):
        if not isinstance(record, dict) or not record.get("player"):
            continue
        by_player.setdefault(norm(record.get("player")), []).append(record)
    for values in by_player.values():
        values.sort(key=lambda r: str(r.get("game_date") or ""), reverse=True)

    updated = 0
    for path in ALT_PATHS:
        payload = load(path, {"rows": []})
        rows = [r for r in payload.get("rows", []) if isinstance(r, dict)]
        for row in rows:
            profile = minutes_profile(by_player.get(norm(row.get("player")), []))
            trend, trend_reasons = trend_component(row)
            matchup, matchup_reasons = matchup_component(row)
            form, form_reasons = form_component(row, profile)
            market, market_reasons, edge = market_component(row)
            risk, risk_reasons = risk_component(row, profile)
            components = {"trend": trend, "matchup": matchup, "form": form, "market": market, "risk": risk}
            score = sum(components[name] * WEIGHTS[name] for name in WEIGHTS)
            letter, confidence, action = grade(score)
            row["streak_score"] = round(score, 1)
            row["streak_grade"] = letter
            row["streak_confidence"] = confidence
            row["streak_action"] = action
            row["expected_edge"] = round(edge, 4) if edge is not None else None
            row["risk_level"] = "Low" if risk >= 78 else "Medium" if risk >= 60 else "High"
            row["score_components"] = components
            row["score_weights"] = WEIGHTS
            row["minutes_profile"] = profile
            positives = []
            negatives = []
            for name, value in components.items():
                target = positives if value >= 70 else negatives if value < 50 else None
                if target is not None:
                    target.append(f"{name.title()} {value:.0f}/100")
            row["score_explanation"] = {
                "summary": f"{letter} {confidence}: score {score:.1f}/100",
                "positives": positives[:4],
                "risks": negatives[:4],
                "trend": trend_reasons,
                "matchup": matchup_reasons,
                "form": form_reasons,
                "market": market_reasons,
                "risk": risk_reasons,
            }
            updated += 1
        rows.sort(key=lambda r: (num(r.get("streak_score")) or 0, num(r.get("expected_edge")) or -999), reverse=True)
        payload["rows"] = rows
        payload["top_10_streaks"] = rows[:10]
        payload.setdefault("summary", {}).update({
            "scored_rows": len(rows),
            "elite_rows": sum((num(r.get("streak_score")) or 0) >= 90 for r in rows),
            "bet_rows": sum(r.get("streak_action") == "BET" for r in rows),
            "lean_rows": sum(r.get("streak_action") == "LEAN" for r in rows),
            "watch_rows": sum(r.get("streak_action") == "WATCH" for r in rows),
            "pass_rows": sum(r.get("streak_action") == "PASS" for r in rows),
        })
        payload["scoring_methodology"] = {
            "weights": WEIGHTS,
            "missing_data_policy": "neutral score; never imputed as favorable",
            "grade_scale": {"A+":"90-100","A":"85-89.9","B+":"80-84.9","B":"75-79.9","C+":"70-74.9","C":"60-69.9","D":"below 60"},
            "disclaimer": "Ranking aid only; not a guarantee of profit.",
        }
        payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
    print("ALT Streak confidence scoring:", {"updated": updated})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.parse_args()
    main()
