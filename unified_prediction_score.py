"""
unified_prediction_score.py
---------------------------
Builds a Universal Prediction Score (UPS) for each player prop and best bet.

No external API calls. Reads predictions/predictions_YYYY-MM-DD.json and enriches:
  - each prop with ups_score, ups_grade, ups_badges, model_agreement, readiness_score
  - daily report with top UPS plays

This is the decision layer that sits above projection, EV, strategy, simulation,
market consensus, confidence calibration, injury impact and sportsbook value.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone

PRED_DIR = "predictions"
OUT_DIR = "data/intelligence"


def f(v, default=0.0):
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return default
        return float(v)
    except Exception:
        return default


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))


def grade(score):
    if score >= 94:
        return "A+"
    if score >= 88:
        return "A"
    if score >= 80:
        return "B+"
    if score >= 72:
        return "B"
    if score >= 62:
        return "C"
    return "AVOID"


def badges(row, score, agreement, readiness):
    out = []
    ev = f(row.get("ev_pct"))
    edge = abs(f(row.get("edge")))
    signal = str(row.get("signal", "")).upper()
    conf = f(row.get("confidence_v2", row.get("score", 0)))
    injury = str(row.get("injury_status", "ACTIVE")).upper()
    corr = row.get("correlation_flag") or ""
    if score >= 94:
        out.append("🔥 Best Bet")
    if ev >= 8:
        out.append("💎 High EV")
    if conf >= 88 and readiness >= 80:
        out.append("🛡 Safe Play")
    if edge >= 2.5:
        out.append("📈 Line Value")
    if agreement.get("agree_count", 0) >= 4:
        out.append("✅ Model Agreement")
    if signal in {"UNDER", "NO"} and conf >= 80:
        out.append("⬇️ Strong Under")
    if signal in {"OVER", "YES"} and conf >= 80:
        out.append("⬆️ Strong Over")
    if injury not in {"", "ACTIVE", "PROBABLE"}:
        out.append("🚨 Injury Risk")
    if corr:
        out.append("🔗 Correlation Watch")
    if score < 62:
        out.append("⚠ Avoid")
    return out[:6]


def model_agreement(row):
    factors = []
    edge = f(row.get("edge"))
    ev = f(row.get("ev_pct"))
    conf = f(row.get("confidence_v2", row.get("score", 0)))
    l5 = f(row.get("last5_hit"))
    l10 = f(row.get("last10_hit"))
    sim = f(row.get("simulation_hit_prob", row.get("hit_probability", 0)))
    strategy = f(row.get("strategy_roi", row.get("historical_roi", 0)))
    consensus = f(row.get("market_consensus_edge", row.get("consensus_edge", 0)))
    clv = f(row.get("expected_clv", row.get("clv", 0)))

    factors.append({"name": "Projection Model", "agrees": abs(edge) >= 1.0, "value": round(edge, 2)})
    factors.append({"name": "Expected Value", "agrees": ev > 0, "value": round(ev, 2)})
    factors.append({"name": "Confidence", "agrees": conf >= 74, "value": round(conf, 1)})
    if l5 or l10:
        factors.append({"name": "Recent Hit Rate", "agrees": max(l5, l10) >= 0.6, "value": round(max(l5, l10) * 100, 1)})
    if sim:
        factors.append({"name": "Monte Carlo", "agrees": sim >= 0.55 or sim >= 55, "value": round(sim, 1)})
    if strategy:
        factors.append({"name": "Strategy Lab", "agrees": strategy > 0, "value": round(strategy, 2)})
    if consensus:
        factors.append({"name": "Market Consensus", "agrees": consensus > 0, "value": round(consensus, 2)})
    if clv:
        factors.append({"name": "CLV Expectation", "agrees": clv > 0, "value": round(clv, 2)})

    agree = sum(1 for x in factors if x["agrees"])
    return {"agree_count": agree, "total": len(factors), "factors": factors, "label": f"{agree}/{len(factors)} agree"}


def readiness(row):
    score = 100
    missing = []
    for key, label in [("line", "line"), ("pred", "projection"), ("best_book", "sportsbook"), ("game", "game"), ("signal", "signal")]:
        if row.get(key) in [None, "", "—"]:
            score -= 12
            missing.append(label)
    if str(row.get("injury_status", "ACTIVE")).upper() in {"QUESTIONABLE", "DOUBTFUL", "GTD"}:
        score -= 18
        missing.append("uncertain injury")
    if f(row.get("projected_minutes")) <= 0 and str(row.get("stat", "")).upper() not in {"DD", "TD"}:
        score -= 8
        missing.append("minutes")
    if f(row.get("available_books", row.get("num_books", 1))) <= 1:
        score -= 6
        missing.append("limited books")
    score = int(clamp(score))
    return {"score": score, "label": "READY" if score >= 85 else "PARTIAL" if score >= 65 else "LOW", "missing": missing[:5]}


def ups(row):
    edge = abs(f(row.get("edge")))
    ev = f(row.get("ev_pct"))
    conf = f(row.get("confidence_v2", row.get("score", 0)))
    l5 = f(row.get("last5_hit"))
    l10 = f(row.get("last10_hit"))
    sim = f(row.get("simulation_hit_prob", row.get("hit_probability", 0)))
    if sim > 1:
        sim = sim / 100.0
    injury = str(row.get("injury_status", "ACTIVE")).upper()
    minutes_conf = str(row.get("minutes_confidence", "MED")).upper()
    opp_rank = f(row.get("opp_rank"), 8)
    agreement = model_agreement(row)
    ready = readiness(row)

    score = 44
    score += min(16, edge * 4.2)
    score += min(14, max(0, ev) * 0.9)
    score += min(16, conf * 0.16)
    score += max(0, (max(l5, l10) - 0.5) * 18)
    score += max(0, (sim - 0.52) * 32)
    score += agreement["agree_count"] * 2.2
    score += 4 if minutes_conf == "HIGH" else 1 if minutes_conf == "MED" else -4
    score += 4 if opp_rank >= 11 else -3 if opp_rank <= 5 else 0
    score += (ready["score"] - 75) * 0.16
    if injury in {"OUT", "DOUBTFUL"}:
        score -= 40
    elif injury in {"QUESTIONABLE", "GTD"}:
        score -= 14
    elif injury == "PROBABLE":
        score -= 3
    score = int(round(clamp(score)))
    return score, agreement, ready


def explain(row):
    reasons = []
    edge = f(row.get("edge"))
    ev = f(row.get("ev_pct"))
    if edge:
        reasons.append(f"Projection edge {edge:+.1f} vs market line.")
    if ev:
        reasons.append(f"Expected value estimate {ev:+.1f}%.")
    if row.get("projected_minutes"):
        reasons.append(f"Projected minutes: {row.get('projected_minutes')} ({row.get('minutes_confidence', 'MED')}).")
    if row.get("injury_status") and str(row.get("injury_status")).upper() != "ACTIVE":
        reasons.append(f"Injury status risk: {row.get('injury_status')}.")
    if row.get("opp_rank"):
        reasons.append(f"Opponent rank: {row.get('opp_rank')} where higher is easier.")
    if row.get("best_book_title") or row.get("best_book"):
        reasons.append(f"Best available sportsbook: {row.get('best_book_title') or row.get('best_book')}.")
    if row.get("confidence_v2"):
        reasons.append(f"Confidence Score 2.0: {row.get('confidence_v2')}/100.")
    return reasons[:7]


def apply(data):
    props = data.get("props", []) or []
    enriched = []
    for r in props:
        row = dict(r)
        score, agreement, ready = ups(row)
        row["ups_score"] = score
        row["ups_grade"] = grade(score)
        row["model_agreement"] = agreement
        row["readiness"] = ready
        row["readiness_score"] = ready["score"]
        row["ups_badges"] = badges(row, score, agreement, ready["score"])
        row["prediction_breakdown"] = explain(row)
        enriched.append(row)
    enriched.sort(key=lambda x: (f(x.get("ups_score")), f(x.get("ev_pct"))), reverse=True)
    data["props"] = enriched

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "top_ups": enriched[:12],
        "top_grades": {g: len([x for x in enriched if x.get("ups_grade") == g]) for g in ["A+", "A", "B+", "B", "C", "AVOID"]},
        "avg_ups": round(sum(f(x.get("ups_score")) for x in enriched) / max(1, len(enriched)), 1),
        "ready_count": len([x for x in enriched if x.get("readiness_score", 0) >= 85]),
        "props_scored": len(enriched),
    }
    data["unified_prediction_score"] = report
    return data


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=str(date.today()))
    args = p.parse_args()
    path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(path):
        raise SystemExit(f"Missing predictions file: {path}")
    with open(path) as fobj:
        data = json.load(fobj)
    data = apply(data)
    with open(path, "w") as fobj:
        json.dump(data, fobj, indent=2)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"unified_prediction_score_{args.date}.json"), "w") as fobj:
        json.dump(data.get("unified_prediction_score", {}), fobj, indent=2)
    print(f"✅ UPS complete: {data['unified_prediction_score']['props_scored']} props scored")


if __name__ == "__main__":
    main()
