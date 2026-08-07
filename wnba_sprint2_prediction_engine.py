from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DASH = Path("data/dashboard")
MASTER = DASH / "wnba_master.json"
PERFORMANCE = DASH / "wnba_game_performance.json"
RATINGS_OUT = DASH / "wnba_team_ratings.json"
PREDICTIONS_OUT = DASH / "wnba_sprint2_predictions.json"


def f(v, default=None):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def mean(values, default=None):
    vals = [f(v) for v in values]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else default


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def build_team_history(perf: dict) -> dict[str, list[dict]]:
    history: dict[str, list[dict]] = defaultdict(list)
    for row in perf.get("recent_games") or []:
        if not isinstance(row, dict) or not row.get("graded"):
            continue
        away = str(row.get("away_team") or "").strip()
        home = str(row.get("home_team") or "").strip()
        away_score = f(row.get("actual_away_score"))
        home_score = f(row.get("actual_home_score"))
        if not away or not home or away_score is None or home_score is None:
            continue
        date = str(row.get("target_date") or "")
        history[away].append({"date": date, "pf": away_score, "pa": home_score, "home": False})
        history[home].append({"date": date, "pf": home_score, "pa": away_score, "home": True})
    for rows in history.values():
        rows.sort(key=lambda r: r.get("date", ""), reverse=True)
    return history


def roster_form(master: dict) -> dict[str, dict]:
    teams: dict[str, list[dict]] = defaultdict(list)
    for p in master.get("players") or []:
        if not isinstance(p, dict):
            continue
        team = str(p.get("team") or "").strip()
        if not team or team.isupper():
            continue
        mpg = f(p.get("mpg"), 0.0) or 0.0
        if mpg <= 0:
            continue
        teams[team].append(p)

    out = {}
    for team, players in teams.items():
        # Weight production by minutes so deep-bench players do not dominate the team signal.
        w = sum(max(1.0, f(p.get("mpg"), 0.0) or 0.0) for p in players)
        season_pts = sum((f(p.get("ppg"), 0.0) or 0.0) * max(1.0, f(p.get("mpg"), 0.0) or 0.0) for p in players) / max(w, 1.0)
        recent_pts = sum((f(p.get("roll5_pts"), f(p.get("ppg"), 0.0)) or 0.0) * max(1.0, f(p.get("roll5_mpg"), f(p.get("mpg"), 0.0)) or 0.0) for p in players) / max(sum(max(1.0, f(p.get("roll5_mpg"), f(p.get("mpg"), 0.0)) or 0.0) for p in players), 1.0)
        out[team] = {
            "players": len(players),
            "weighted_ppg": round(season_pts, 3),
            "weighted_roll5_ppg": round(recent_pts, 3),
            "form_delta": round(recent_pts - season_pts, 3),
        }
    return out


def build_ratings(master: dict, perf: dict) -> dict:
    history = build_team_history(perf)
    form = roster_form(master)
    all_team_games = [r for rows in history.values() for r in rows]
    league_pf = mean([r["pf"] for r in all_team_games], 82.0) or 82.0
    league_pa = mean([r["pa"] for r in all_team_games], league_pf) or league_pf

    team_names = set(history) | set(form)
    for g in master.get("games") or []:
        if isinstance(g, dict):
            team_names.update([str(g.get("away_team") or "").strip(), str(g.get("home_team") or "").strip()])
    team_names.discard("")

    ratings = []
    by_team = {}
    for team in sorted(team_names):
        rows = history.get(team, [])
        l10 = rows[:10]
        l5 = rows[:5]
        pf10 = mean([r["pf"] for r in l10], league_pf) or league_pf
        pa10 = mean([r["pa"] for r in l10], league_pa) or league_pa
        pf5 = mean([r["pf"] for r in l5], pf10) or pf10
        pa5 = mean([r["pa"] for r in l5], pa10) or pa10
        home_rows = [r for r in rows if r["home"]][:10]
        away_rows = [r for r in rows if not r["home"]][:10]
        form_delta = f((form.get(team) or {}).get("form_delta"), 0.0) or 0.0

        # These are transparent score-based indices, not possession-normalized official ORtg/DRtg.
        offense_index = 100.0 + (pf10 - league_pf) * 1.2 + form_delta * 0.35
        defense_index = 100.0 + (league_pa - pa10) * 1.2
        recent_index = ((pf5 - pa5) - (pf10 - pa10)) * 0.7
        net_index = offense_index + defense_index - 200.0
        power_rating = net_index + recent_index
        sample = len(rows)
        data_conf = round(clamp(35 + sample * 4, 35, 90), 1)

        item = {
            "team": team,
            "games_sample": sample,
            "points_for_l10": round(pf10, 2),
            "points_against_l10": round(pa10, 2),
            "points_for_l5": round(pf5, 2),
            "points_against_l5": round(pa5, 2),
            "home_points_for": round(mean([r["pf"] for r in home_rows], pf10) or pf10, 2),
            "away_points_for": round(mean([r["pf"] for r in away_rows], pf10) or pf10, 2),
            "offense_index": round(offense_index, 2),
            "defense_index": round(defense_index, 2),
            "net_index": round(net_index, 2),
            "recent_form_index": round(recent_index, 2),
            "power_rating": round(power_rating, 2),
            "roster_form": form.get(team, {}),
            "data_confidence": data_conf,
        }
        ratings.append(item)
        by_team[team] = item

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": master.get("target_date"),
        "schema_version": "sprint2-team-ratings-v1",
        "method": "score_history_plus_roster_form_proxy",
        "warning": "offense_index and defense_index are transparent score-based model indices, not official possession-normalized ORtg/DRtg",
        "league_baseline": {"points_for": round(league_pf, 2), "points_against": round(league_pa, 2)},
        "teams": ratings,
        "by_team": by_team,
    }


def implied_scores(total, home_spread):
    if total is None:
        return None, None
    if home_spread is None:
        return total / 2.0, total / 2.0
    # Spread is stored from the home-team perspective: negative = home favorite.
    home_margin = -home_spread
    home = (total + home_margin) / 2.0
    away = total - home
    return away, home


def build_predictions(master: dict, ratings: dict) -> dict:
    by_team = ratings.get("by_team") or {}
    league = ratings.get("league_baseline") or {}
    league_pf = f(league.get("points_for"), 82.0) or 82.0
    predictions = []

    for g in master.get("games") or []:
        if not isinstance(g, dict) or g.get("bucket") != "today":
            continue
        away = str(g.get("away_team") or "").strip()
        home = str(g.get("home_team") or "").strip()
        ar = by_team.get(away, {})
        hr = by_team.get(home, {})
        total = f(g.get("total"))
        home_spread = f(g.get("spread"))
        market_away, market_home = implied_scores(total, home_spread)

        a_pf = f(ar.get("points_for_l10"), league_pf) or league_pf
        h_pf = f(hr.get("points_for_l10"), league_pf) or league_pf
        a_pa = f(ar.get("points_against_l10"), league_pf) or league_pf
        h_pa = f(hr.get("points_against_l10"), league_pf) or league_pf
        roster_a = f((ar.get("roster_form") or {}).get("form_delta"), 0.0) or 0.0
        roster_h = f((hr.get("roster_form") or {}).get("form_delta"), 0.0) or 0.0

        raw_away = (a_pf + h_pa) / 2.0 + roster_a * 0.25
        raw_home = (h_pf + a_pa) / 2.0 + roster_h * 0.25 + 1.4  # modest home-court prior

        if market_away is not None and market_home is not None:
            # With limited owned history, market is deliberately the stronger prior.
            proj_away = market_away * 0.58 + raw_away * 0.42
            proj_home = market_home * 0.58 + raw_home * 0.42
            source = "team_indices+roster_form+market_prior"
        else:
            proj_away, proj_home = raw_away, raw_home
            source = "team_indices+roster_form"

        proj_total = proj_away + proj_home
        home_margin = proj_home - proj_away
        model_home_spread = -home_margin
        spread_edge = (home_spread - model_home_spread) if home_spread is not None else None
        total_edge = (proj_total - total) if total is not None else None
        win_home = 1.0 / (1.0 + math.exp(-home_margin / 6.5))

        a_conf = f(ar.get("data_confidence"), 35.0) or 35.0
        h_conf = f(hr.get("data_confidence"), 35.0) or 35.0
        disagreement = abs(spread_edge or 0.0) + abs(total_edge or 0.0) * 0.25
        confidence = clamp((a_conf + h_conf) / 2.0 + min(disagreement, 8.0) * 2.0, 35.0, 88.0)

        spread_pick = "PASS"
        if spread_edge is not None and abs(spread_edge) >= 2.0:
            spread_pick = home if spread_edge > 0 else away
        total_pick = "PASS"
        if total_edge is not None and abs(total_edge) >= 3.0:
            total_pick = "OVER" if total_edge > 0 else "UNDER"

        predictions.append({
            "game": g.get("game") or f"{away} @ {home}",
            "away_team": away,
            "home_team": home,
            "start_time": g.get("start_time"),
            "market": {"home_spread": home_spread, "total": total},
            "projection": {
                "away_score": round(proj_away, 1),
                "home_score": round(proj_home, 1),
                "home_margin": round(home_margin, 2),
                "model_home_spread": round(model_home_spread, 2),
                "total": round(proj_total, 1),
                "home_win_probability": round(win_home, 4),
                "away_win_probability": round(1.0 - win_home, 4),
            },
            "edge": {
                "spread": round(spread_edge, 2) if spread_edge is not None else None,
                "total": round(total_edge, 2) if total_edge is not None else None,
            },
            "recommendation": {"spread": spread_pick, "total": total_pick},
            "confidence": round(confidence, 1),
            "source": source,
            "team_ratings": {"away": ar, "home": hr},
        })

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": master.get("target_date"),
        "schema_version": "sprint2-game-projections-v1",
        "status": "PASS",
        "games": predictions,
        "summary": {"game_count": len(predictions), "qualified_spreads": sum(1 for p in predictions if p["recommendation"]["spread"] != "PASS"), "qualified_totals": sum(1 for p in predictions if p["recommendation"]["total"] != "PASS")},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    args = ap.parse_args()

    master = load(MASTER, {})
    if not master:
        raise SystemExit("Missing canonical master data")
    target = str(master.get("target_date") or "")
    if args.date and target != args.date:
        raise SystemExit(f"Canonical master date mismatch: expected {args.date}, got {target}")

    perf = load(PERFORMANCE, {})
    ratings = build_ratings(master, perf)
    predictions = build_predictions(master, ratings)
    RATINGS_OUT.write_text(json.dumps(ratings, indent=2), encoding="utf-8")
    PREDICTIONS_OUT.write_text(json.dumps(predictions, indent=2), encoding="utf-8")
    print(json.dumps({"target_date": target, "teams": len(ratings.get("teams") or []), "games": len(predictions.get("games") or []), "status": "PASS"}))


if __name__ == "__main__":
    main()
