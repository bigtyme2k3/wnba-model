"""Build calibrated player-prop bet cards and verified historical trend context."""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

MASTER_PATHS = [Path("data/master/wnba_master.json"), Path("data/dashboard/wnba_master.json")]
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
OUTS = [Path("data/warehouse/wnba_prop_bet_cards.json"), Path("data/dashboard/wnba_prop_bet_cards.json")]


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(payload, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)


def num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("’", "'").split())


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def stat_value(row: dict[str, Any], stat: str) -> float | None:
    stat = str(stat or "").upper()
    scoring = row.get("scoring") or {}
    box = row.get("boxscore") or {}
    pts = num(scoring.get("total_pts") if isinstance(scoring, dict) else None)
    reb = num(box.get("reb") if isinstance(box, dict) else None)
    ast = num(box.get("ast") if isinstance(box, dict) else None)
    threes = num(scoring.get("three_pm") if isinstance(scoring, dict) else None)
    stl = num(box.get("stl") if isinstance(box, dict) else None)
    blk = num(box.get("blk") if isinstance(box, dict) else None)
    tov = num(box.get("tov") if isinstance(box, dict) else None)
    values = {
        "PTS": pts, "REB": reb, "AST": ast, "3PM": threes, "STL": stl, "BLK": blk, "TOV": tov,
        "PRA": None if None in (pts, reb, ast) else pts + reb + ast,
        "PR": None if None in (pts, reb) else pts + reb,
        "PA": None if None in (pts, ast) else pts + ast,
        "RA": None if None in (reb, ast) else reb + ast,
    }
    return values.get(stat)


def histories() -> dict[str, list[dict[str, Any]]]:
    payload = load(LOGS, {"records": []})
    records = payload.get("records", []) if isinstance(payload, dict) else []
    out: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        if not isinstance(row, dict) or not row.get("player"):
            continue
        out.setdefault(norm(row.get("player")), []).append(row)
    for rows in out.values():
        rows.sort(key=lambda r: (str(r.get("game_date") or ""), str(r.get("game_id") or "")), reverse=True)
    return out


def hit(value: float, side: str, line: float) -> bool:
    return value > line if side == "OVER" else value < line


def window(rows: list[dict[str, Any]], stat: str, side: str, line: float, n: int) -> dict[str, Any]:
    values: list[float] = []
    opponents: list[str] = []
    for row in rows:
        value = stat_value(row, stat)
        if value is None:
            continue
        values.append(round(value, 2))
        opponents.append(str(row.get("opponent") or row.get("opponent_team") or ""))
        if len(values) >= n:
            break
    wins = sum(hit(v, side, line) for v in values)
    return {
        "sample": len(values),
        "hits": wins,
        "hit_rate": round(wins / len(values), 4) if values else None,
        "average": round(sum(values) / len(values), 2) if values else None,
        "values": values,
        "opponents": opponents,
    }


def american_decimal(odds: Any) -> float | None:
    x = num(odds)
    if x is None or x == 0:
        return None
    return 1 + (100 / abs(x) if x < 0 else x / 100)


def grade_letter(score: float) -> str:
    if score >= 90: return "A+"
    if score >= 84: return "A"
    if score >= 78: return "B+"
    if score >= 72: return "B"
    if score >= 65: return "C+"
    if score >= 58: return "C"
    return "PASS"


def build_card(prop: dict[str, Any], player_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    stat = str(prop.get("stat") or "").upper()
    line = num(prop.get("line") if prop.get("line") is not None else prop.get("consensus_line"))
    side = str(prop.get("signal") or prop.get("side") or "").upper()
    if stat not in {"PTS","REB","AST","3PM","STL","BLK","TOV","PRA","PR","PA","RA"} or line is None or side not in {"OVER","UNDER"}:
        return None

    sim = prop.get("unified_simulation_v2") or {}
    best_market = sim.get("best_market") or {}
    probability = num(best_market.get("hit_probability"))
    if probability is None:
        probability = num(prop.get("simulation_probability"))
    odds = prop.get("best_price") or (prop.get("best_over_price") if side == "OVER" else prop.get("best_under_price"))
    decimal = american_decimal(odds)
    ev = num(best_market.get("expected_value_per_unit"))
    if ev is None and probability is not None and decimal is not None:
        ev = probability * decimal - 1

    l5 = window(player_rows, stat, side, line, 5)
    l10 = window(player_rows, stat, side, line, 10)
    l20 = window(player_rows, stat, side, line, 20)
    trend_rates = [x["hit_rate"] for x in (l5, l10, l20) if x["hit_rate"] is not None]
    trend_rate = sum(trend_rates) / len(trend_rates) if trend_rates else 0.5

    data_quality = str(sim.get("data_quality_status") or prop.get("data_quality_status") or "limited")
    quality_score = {"complete": 1.0, "partial": 0.7, "limited": 0.4}.get(data_quality, 0.35)
    sim_conf = (num(sim.get("confidence")) or num(prop.get("projection_confidence_v2")) or 50) / 100
    books = int(num(prop.get("book_count")) or 0)

    probability_component = clamp(((probability or 0.5) - 0.5) / 0.25, 0, 1) * 35
    ev_component = clamp((ev or 0) / 0.20, 0, 1) * 20
    trend_component = clamp((trend_rate - 0.45) / 0.30, 0, 1) * 15
    quality_component = quality_score * 15
    confidence_component = clamp(sim_conf, 0, 1) * 10
    books_component = clamp(books / 3, 0, 1) * 5
    score = round(clamp(probability_component + ev_component + trend_component + quality_component + confidence_component + books_component, 0, 95), 1)

    reasons = []
    risks = []
    if probability is not None: reasons.append(f"10,000-run simulation hit probability {probability:.1%}")
    if ev is not None: reasons.append(f"Expected value {ev:+.1%} at listed price")
    if l10["sample"]: reasons.append(f"Historical line hit rate {l10['hits']}/{l10['sample']} over last {l10['sample']} games")
    if books >= 2: reasons.append(f"Line compared across {books} sportsbooks")
    if data_quality != "complete": risks.append(f"Projection data quality is {data_quality}")
    if l20["sample"] < 10: risks.append("Limited verified historical sample")
    if probability is None: risks.append("Simulation probability unavailable")
    if ev is None: risks.append("Price-based expected value unavailable")
    if books < 2: risks.append("Only one sportsbook price available")

    action = "BET" if score >= 78 and probability is not None and probability >= 0.56 and ev is not None and ev >= 0.03 else "LEAN" if score >= 65 else "WATCH" if score >= 55 else "PASS"
    return {
        "player": prop.get("player"), "team": prop.get("team"), "game": prop.get("game"), "stat": stat,
        "side": side, "signal": side, "line": line, "sportsbook": prop.get("best_book") or prop.get("book"), "odds": odds,
        "projection": prop.get("projection") or prop.get("proj") or prop.get("pred"),
        "simulation_probability": round(probability, 4) if probability is not None else None,
        "expected_value": round(ev, 4) if ev is not None else None,
        "recommended_units": best_market.get("recommended_units"),
        "research_grade": score, "letter_grade": grade_letter(score), "action": action,
        "trend": {"last5": l5, "last10": l10, "last20": l20},
        "data_quality": data_quality, "book_count": books, "reasons": reasons[:5], "risks": risks[:5],
        "source": "calibrated_prop_bet_card_v1",
    }


def build(target: str) -> dict[str, Any]:
    master = next((load(path, {}) for path in MASTER_PATHS if path.exists()), {})
    hist = histories()
    cards = []
    enriched_props = []
    for prop in master.get("props", []) or []:
        row = dict(prop)
        card = build_card(row, hist.get(norm(row.get("player")), []))
        if card:
            row["bet_card"] = card
            cards.append(card)
        enriched_props.append(row)
    cards.sort(key=lambda x: (x["action"] != "BET", -x["research_grade"], -(x.get("expected_value") or -9)))
    ranked = [c for c in cards if c["action"] in {"BET", "LEAN"}][:30]
    for path in MASTER_PATHS:
        payload = load(path, {})
        if not payload:
            continue
        payload["props"] = enriched_props
        payload["best_bets"] = ranked
        payload["prop_bet_cards"] = {"count": len(cards), "ranked": len(ranked), "source": "data/dashboard/wnba_prop_bet_cards.json"}
        if isinstance(payload.get("summary"), dict):
            payload["summary"]["best_bets"] = len(ranked)
        dump(path, payload)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "target_date": target, "status": "ok",
        "summary": {"cards": len(cards), "bets": sum(c["action"] == "BET" for c in cards), "leans": sum(c["action"] == "LEAN" for c in cards), "watch": sum(c["action"] == "WATCH" for c in cards)},
        "ranked_cards": ranked, "all_cards": cards,
        "scoring_note": "Research grade is not a win probability. Simulation probability and expected value are displayed separately.",
    }
    for path in OUTS: dump(path, report)
    print("PROP BET CARDS ACTIVE", report["summary"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); args = parser.parse_args(); build(args.date)


if __name__ == "__main__":
    main()
