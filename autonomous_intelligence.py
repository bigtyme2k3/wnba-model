"""
autonomous_intelligence.py
--------------------------
Phase 7 autonomous intelligence layer.

Builds a consensus layer across existing engines without external API calls.
Runs after Decision Center and any DeepSeek Phase 6 outputs.

Adds `autonomous_intelligence` to predictions/predictions_YYYY-MM-DD.json and exports
`data/intelligence/autonomous_intelligence_YYYY-MM-DD.json`.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

PRED_DIR = "predictions"
OUT_DIR = "data/intelligence"
DASH_DIR = "data/dashboard"


def f(v, default=0.0):
    try:
        if v is None or v == "" or str(v).lower() == "nan":
            return default
        return float(v)
    except Exception:
        return default


def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except Exception:
        return default if default is not None else {}


def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def player_key(p):
    return "|".join([
        str(p.get("player", "")).lower().strip(),
        str(p.get("game", "")).lower().strip(),
        str(p.get("stat", "")).upper().strip(),
        str(p.get("line", "")).strip(),
    ])


def direction(p):
    return str(p.get("signal") or p.get("recommendation") or "").upper()


def engine_votes(p):
    votes = []
    edge = f(p.get("edge"))
    ev = f(p.get("ev_pct"))
    ups = f(p.get("ups_score"))
    conf = f(p.get("confidence_v2", p.get("score", 0)))
    readiness = f(p.get("readiness_score"))
    agreement = p.get("model_agreement", {}) if isinstance(p.get("model_agreement"), dict) else {}
    agree_count = f(agreement.get("agree_count"))
    agree_total = max(1, f(agreement.get("total"), 1))
    hit_prob = f(p.get("simulation_hit_prob", p.get("hit_probability", 0)))
    if hit_prob > 1:
        hit_prob = hit_prob / 100
    clv = f(p.get("expected_clv", p.get("clv", 0)))
    strategy_roi = f(p.get("strategy_roi", p.get("historical_roi", 0)))
    market_edge = f(p.get("market_consensus_edge", p.get("consensus_edge", 0)))

    votes.append({"engine": "Projection Edge", "vote": abs(edge) >= 1.0, "score": clamp(abs(edge) * 18), "value": round(edge, 2)})
    votes.append({"engine": "Expected Value", "vote": ev > 0, "score": clamp(50 + ev * 3), "value": round(ev, 2)})
    votes.append({"engine": "UPS", "vote": ups >= 80, "score": clamp(ups), "value": round(ups, 1)})
    votes.append({"engine": "Confidence", "vote": conf >= 75, "score": clamp(conf), "value": round(conf, 1)})
    votes.append({"engine": "Readiness", "vote": readiness >= 75, "score": clamp(readiness), "value": round(readiness, 1)})
    votes.append({"engine": "Model Agreement", "vote": (agree_count / agree_total) >= 0.55, "score": clamp((agree_count / agree_total) * 100), "value": f"{int(agree_count)}/{int(agree_total)}"})
    if hit_prob:
        votes.append({"engine": "Simulation", "vote": hit_prob >= 0.54, "score": clamp(hit_prob * 100), "value": round(hit_prob * 100, 1)})
    if clv:
        votes.append({"engine": "CLV Predictor", "vote": clv > 0, "score": clamp(50 + clv * 15), "value": round(clv, 2)})
    if strategy_roi:
        votes.append({"engine": "Strategy Lab", "vote": strategy_roi > 0, "score": clamp(50 + strategy_roi * 2), "value": round(strategy_roi, 2)})
    if market_edge:
        votes.append({"engine": "Market Consensus", "vote": market_edge > 0, "score": clamp(50 + market_edge * 5), "value": round(market_edge, 2)})
    return votes


def consensus_for_prop(p):
    votes = engine_votes(p)
    yes = sum(1 for v in votes if v["vote"])
    total = max(1, len(votes))
    avg_score = sum(f(v["score"]) for v in votes) / total
    agreement_pct = round(yes / total * 100, 1)
    injury = str(p.get("injury_status", "ACTIVE")).upper()
    risk_penalty = 0
    warnings = []
    if injury in {"OUT", "DOUBTFUL"}:
        risk_penalty += 45
        warnings.append(f"Injury status: {injury}")
    elif injury in {"QUESTIONABLE", "GTD"}:
        risk_penalty += 14
        warnings.append(f"Injury status: {injury}")
    if f(p.get("readiness_score")) < 65:
        risk_penalty += 12
        warnings.append("Low readiness")
    if f(p.get("ev_pct")) < -2:
        risk_penalty += 10
        warnings.append("Negative EV")
    consensus = round(clamp(avg_score * 0.62 + agreement_pct * 0.38 - risk_penalty), 1)
    if consensus >= 88 and yes >= max(4, total * 0.65):
        rec = "BET"
    elif consensus >= 78:
        rec = "LEAN"
    elif consensus >= 65:
        rec = "WATCH"
    else:
        rec = "PASS"
    return {
        "player": p.get("player"),
        "team": p.get("team"),
        "game": p.get("game"),
        "stat": p.get("stat"),
        "line": p.get("line"),
        "signal": direction(p),
        "best_book": p.get("best_book_title") or p.get("best_book"),
        "projection": p.get("pred"),
        "edge": p.get("edge"),
        "ev_pct": p.get("ev_pct"),
        "ups_score": p.get("ups_score"),
        "consensus_score": consensus,
        "agreement_pct": agreement_pct,
        "engines_agree": yes,
        "engines_total": total,
        "recommendation": rec,
        "votes": votes,
        "warnings": warnings,
        "badges": p.get("ups_badges", [])[:5],
    }


def discover_strategies(props):
    groups = defaultdict(list)
    for p in props:
        groups[(str(p.get("stat", "UNKNOWN")).upper(), direction(p))].append(p)
        groups[("book:" + str(p.get("best_book_title") or p.get("best_book") or "Unknown"), direction(p))].append(p)
        groups[("game:" + str(p.get("game") or "Unknown"), direction(p))].append(p)
    strategies = []
    for (name, sig), rows in groups.items():
        if len(rows) < 3:
            continue
        avg_ups = sum(f(r.get("ups_score")) for r in rows) / len(rows)
        avg_ev = sum(f(r.get("ev_pct")) for r in rows) / len(rows)
        high = len([r for r in rows if f(r.get("ups_score")) >= 80])
        score = clamp(avg_ups * 0.55 + max(0, avg_ev) * 2 + high * 4)
        if score >= 68:
            strategies.append({
                "name": name,
                "direction": sig,
                "matches": len(rows),
                "avg_ups": round(avg_ups, 1),
                "avg_ev": round(avg_ev, 1),
                "high_grade_matches": high,
                "discovery_score": round(score, 1),
                "example_players": [r.get("player") for r in sorted(rows, key=lambda x: f(x.get("ups_score")), reverse=True)[:4]],
            })
    strategies.sort(key=lambda s: s["discovery_score"], reverse=True)
    return strategies[:12]


def model_ranking(props):
    names = ["Projection Edge", "Expected Value", "UPS", "Confidence", "Readiness", "Model Agreement", "Simulation", "CLV Predictor", "Strategy Lab", "Market Consensus"]
    stats = {n: {"engine": n, "votes": 0, "avg_score": 0, "positive": 0, "rank": "Unrated"} for n in names}
    seen_scores = defaultdict(list)
    seen_pos = defaultdict(int)
    for p in props:
        for v in engine_votes(p):
            seen_scores[v["engine"]].append(f(v["score"]))
            if v["vote"]:
                seen_pos[v["engine"]] += 1
    out = []
    for n in names:
        scores = seen_scores.get(n, [])
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        pos = seen_pos[n]
        pct = pos / len(scores) * 100
        grade = "Elite" if avg >= 85 else "Strong" if avg >= 75 else "Good" if avg >= 65 else "Watch"
        out.append({"engine": n, "votes": len(scores), "positive_pct": round(pct, 1), "avg_score": round(avg, 1), "rank": grade})
    out.sort(key=lambda x: x["avg_score"], reverse=True)
    return out


def build(data):
    props = data.get("props", []) or []
    decision = data.get("decision_center", {}) or {}
    consensus = [consensus_for_prop(p) for p in props]
    consensus.sort(key=lambda x: (f(x.get("consensus_score")), f(x.get("ev_pct"))), reverse=True)
    bets = [c for c in consensus if c["recommendation"] == "BET"]
    leans = [c for c in consensus if c["recommendation"] == "LEAN"]
    watch = [c for c in consensus if c["recommendation"] == "WATCH"]
    passes = [c for c in consensus if c["recommendation"] == "PASS"]
    strategy_discovery = discover_strategies(props)
    rankings = model_ranking(props)
    top = bets[0] if bets else consensus[0] if consensus else None
    agent_report = []
    if top:
        agent_report.append(f"Top consensus play: {top['player']} {top['stat']} {top['signal']} with {top['consensus_score']} consensus.")
    agent_report.append(f"Consensus found {len(bets)} BETs, {len(leans)} leans, and {len(watch)} watchlist plays.")
    if strategy_discovery:
        s = strategy_discovery[0]
        agent_report.append(f"Top discovered angle: {s['name']} {s['direction']} with score {s['discovery_score']} across {s['matches']} matches.")
    if rankings:
        agent_report.append(f"Strongest active engine today: {rankings[0]['engine']} ({rankings[0]['rank']}).")
    if decision.get("summary", {}).get("recommended_exposure"):
        agent_report.append(f"Decision Center exposure setting: {decision['summary']['recommended_exposure']}.")

    memory_snapshot = {
        "props_seen": len(props),
        "players_seen": len(set(str(p.get("player")) for p in props if p.get("player"))),
        "books_seen": dict(Counter(str(p.get("best_book_title") or p.get("best_book") or "Unknown") for p in props).most_common(8)),
        "markets_seen": dict(Counter(str(p.get("stat", "UNKNOWN")).upper() for p in props).most_common(12)),
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_consensus_items": len(consensus),
            "bet_count": len(bets),
            "lean_count": len(leans),
            "watch_count": len(watch),
            "pass_count": len(passes),
            "top_consensus_score": top.get("consensus_score") if top else 0,
            "top_player": top.get("player") if top else "—",
            "top_play": f"{top.get('stat')} {top.get('signal')}" if top else "—",
        },
        "agent_report": agent_report,
        "top_consensus": consensus[:15],
        "bets": bets[:20],
        "leans": leans[:20],
        "watchlist": watch[:20],
        "strategy_discovery": strategy_discovery,
        "model_rankings": rankings,
        "memory_snapshot": memory_snapshot,
        "agent_contract": {
            "version": "phase7.autonomous_intelligence.v1",
            "standard_fields": ["player", "game", "stat", "line", "signal", "consensus_score", "recommendation", "votes", "warnings"],
            "future_agents": ["Research Agent", "Injury Agent", "News Agent", "Odds Agent", "Portfolio Agent", "Simulation Agent", "Learning Agent"],
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    pred_path = os.path.join(PRED_DIR, f"predictions_{args.date}.json")
    if not os.path.exists(pred_path):
        raise SystemExit(f"Missing predictions file: {pred_path}")
    with open(pred_path) as fh:
        data = json.load(fh)
    auto = build(data)
    data["autonomous_intelligence"] = auto
    with open(pred_path, "w") as fh:
        json.dump(data, fh, indent=2)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"autonomous_intelligence_{args.date}.json"), "w") as fh:
        json.dump(auto, fh, indent=2)
    os.makedirs(DASH_DIR, exist_ok=True)
    with open(os.path.join(DASH_DIR, "master_feed.json"), "w") as fh:
        json.dump({"date": args.date, "autonomous_intelligence": auto, "decision_center": data.get("decision_center", {})}, fh, indent=2)
    print(f"✅ Autonomous Intelligence built: {auto['summary']['bet_count']} BET / {auto['summary']['lean_count']} LEAN")


if __name__ == "__main__":
    main()
