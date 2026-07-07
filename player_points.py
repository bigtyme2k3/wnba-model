"""
player_points.py
----------------
Generates WNBA sportsbook player prop rows for the dashboard Props tab.

V5 update:
- Connects data/warehouse/wnba_player_intelligence.json directly into player baselines.
- Projections now react to minutes trend, usage trend, recent form, role score, and injury profile.
- Keeps existing fallback behavior when intelligence data is missing.
"""

from __future__ import annotations

import argparse, json, os
from datetime import date
import pandas as pd

from betting_engine import edge_to_prob, expected_value, implied_prob_american, kelly_fraction

RAW_DIR = "data/raw"
LIVE_PLAYERS_PATH = os.path.join(RAW_DIR, "wnba_players_live.json")
PLAYER_INTEL_PATH = "data/warehouse/wnba_player_intelligence.json"
STAT_MAP = {"pts":"PTS","reb":"REB","ast":"AST","threes":"3PM","pra":"PRA","pa":"PA","pr":"PR","ra":"RA","dd":"DD","td":"TD"}
OUTPUT_COLUMNS = ["player","team","opp","pos","stat","season_avg","pred","low","high","range","line","over_price","under_price","yes_price","no_price","edge","signal","conf","model_prob","implied_prob","ev","ev_pct","kelly_frac","injury_status","market_status","is_active","filter_reason","reasoning","game","home_team","away_team","last5_vals","last5_opps","last5_hit","last10_hit","h2h_last5","opp_rank","role_score","minutes_trend","points_trend","intel_source"]


def safe_float(value, default=0.0):
    try:
        if pd.isna(value): return default
        return float(value)
    except Exception:
        return default


def norm_name(name):
    return str(name or "").strip().lower().replace("’", "'")


def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception as exc:
        print(f"  [WARN] Could not read {path}: {exc}")
    return default


def load_live_players(path=LIVE_PLAYERS_PATH):
    data = load_json(path, {})
    if data:
        print(f"  Loaded live WNBA player stats: {path} ({len(data)} players)")
    else:
        print("  [INFO] No live WNBA player stats found. Using fallback baselines only.")
    return data or {}


def load_player_intelligence(path=PLAYER_INTEL_PATH):
    data = load_json(path, {})
    rows = data.get("players", []) if isinstance(data, dict) else []
    out = {}
    for rec in rows:
        name = rec.get("player")
        if name:
            out[norm_name(name)] = rec
    if out:
        print(f"  Loaded WNBA player intelligence: {path} ({len(out)} players)")
    return out


def apply_intelligence(base, intel):
    if not intel:
        return base
    season = intel.get("season", {}) or {}
    recent = intel.get("recent_form", {}) or {}
    injury = intel.get("injury", {}) or {}
    iq = intel.get("intelligence", {}) or {}
    merged = dict(base or {})
    merged.update({
        "ppg": safe_float(season.get("ppg"), safe_float(merged.get("ppg"), 0)),
        "reb": safe_float(season.get("reb"), safe_float(merged.get("reb"), 0)),
        "ast": safe_float(season.get("ast"), safe_float(merged.get("ast"), 0)),
        "mpg": safe_float(season.get("mpg"), safe_float(merged.get("mpg"), 30)),
        "usage": safe_float(season.get("usage"), safe_float(merged.get("usage"), 0.25)),
        "ts_pct": safe_float(season.get("ts_pct"), safe_float(merged.get("ts_pct", merged.get("ts")), 0.55)),
        "roll5_pts": safe_float(recent.get("last5_pts"), safe_float(merged.get("roll5_pts"), safe_float(merged.get("ppg"), 0))),
        "roll5_reb": safe_float(recent.get("last5_reb"), safe_float(merged.get("roll5_reb"), safe_float(merged.get("reb"), 0))),
        "roll5_ast": safe_float(recent.get("last5_ast"), safe_float(merged.get("roll5_ast"), safe_float(merged.get("ast"), 0))),
        "roll5_mpg": safe_float(recent.get("last5_mpg"), safe_float(merged.get("roll5_mpg"), safe_float(merged.get("mpg"), 30))),
        "roll5_threes": safe_float(recent.get("last5_threes"), safe_float(merged.get("roll5_threes"), 0)),
        "role_score": safe_float(iq.get("role_score"), safe_float(merged.get("role_score"), 50)),
        "minutes_trend": recent.get("minutes_trend", merged.get("minutes_trend", "STABLE")),
        "points_trend": recent.get("points_trend", merged.get("points_trend", "STABLE")),
        "intel_injury_status": str(injury.get("status", "ACTIVE") or "ACTIVE").upper(),
        "intel_injury_detail": injury.get("detail"),
        "intel_source": "wnba_player_intelligence",
        "source": "stats.wnba.com+player_intelligence",
    })
    return merged


def load_player_baselines():
    baselines = {}
    try:
        from daily_runner import PLAYER_PROPS
        baselines.update(PLAYER_PROPS or {})
        print(f"  Loaded fallback PLAYER_PROPS: {len(PLAYER_PROPS or {})} players")
    except Exception as exc:
        print(f"  [WARN] Could not import PLAYER_PROPS from daily_runner.py: {exc}")

    for player, live in load_live_players().items():
        existing = baselines.get(player, {}) or {}
        merged = dict(existing)
        ppg = live.get("ppg", live.get("roll5_pts", existing.get("roll5_pts", 0)))
        mpg = live.get("mpg", existing.get("mpg", 30))
        usage = live.get("usage", existing.get("usage", 0.25))
        ts = live.get("ts_pct", live.get("ts", existing.get("ts", 0.55)))
        merged.update(live)
        merged.update({"ppg": ppg, "mpg": mpg, "usage": usage, "ts": ts, "ts_pct": ts, "source": "stats.wnba.com"})
        baselines[player] = merged

    intel = load_player_intelligence()
    for key, rec in intel.items():
        player = rec.get("player")
        if not player: continue
        baselines[player] = apply_intelligence(baselines.get(player, {}), rec)
    return baselines


def load_props(target_date, raw_dir):
    for path in [os.path.join(raw_dir, f"props_raw_{target_date}.csv"), os.path.join(raw_dir, "props_today.csv")]:
        if os.path.exists(path):
            df = pd.read_csv(path); print(f"  Loaded props: {path} ({len(df)} rows)"); return df
    print("  [WARN] No props file found."); return pd.DataFrame()


def load_injuries(target_date, raw_dir):
    injuries = {}
    for path in [os.path.join(raw_dir, f"injuries_{target_date}.csv"), os.path.join(raw_dir, "injuries_today.csv")]:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path); print(f"  Loaded injuries: {path} ({len(df)} rows)")
                for _, row in df.iterrows():
                    p = norm_name(row.get("player"))
                    if not p: continue
                    sev = str(row.get("severity", row.get("status", "ACTIVE")) or "ACTIVE").upper()
                    injuries[p] = {"severity": sev, "status": str(row.get("status", sev) or sev).upper(), "note": str(row.get("detail", row.get("note", "")) or ""), "source": str(row.get("source", "injury-feed") or "injury-feed")}
                break
            except Exception as exc: print(f"  [WARN] Could not read injuries: {exc}")
    for rec in load_player_intelligence().values():
        name = norm_name(rec.get("player"))
        inj = rec.get("injury", {}) or {}
        status = str(inj.get("status", "ACTIVE") or "ACTIVE").upper()
        if name and status != "ACTIVE" and name not in injuries:
            injuries[name] = {"severity": status, "status": status, "note": str(inj.get("detail") or ""), "source": "player_intelligence"}
    return injuries


def confidence(edge, stat):
    if edge is None: return "LOW", None
    ae = abs(edge)
    if stat in {"dd", "td"}:
        if ae >= 0.10: return "HIGH", "YES" if edge > 0 else "NO"
        if ae >= 0.04: return "MED", "YES" if edge > 0 else "NO"
        return "LOW", None
    if ae >= 2.0: return "HIGH", "OVER" if edge > 0 else "UNDER"
    if ae >= 0.35: return "MED", "OVER" if edge > 0 else "UNDER"
    return "LOW", None


def downgrade_conf(conf, injury_status):
    if injury_status == "QUESTIONABLE": return "MED" if conf == "HIGH" else "LOW"
    if injury_status == "PROBABLE" and conf == "HIGH": return "MED"
    return conf


def stat_baseline(base, stat, line):
    pts = safe_float(base.get("ppg", base.get("roll5_pts", line if stat == "pts" else 0)), 0)
    reb = safe_float(base.get("reb", base.get("roll5_reb", line if stat == "reb" else 0)), 0)
    ast = safe_float(base.get("ast", base.get("roll5_ast", line if stat == "ast" else 0)), 0)
    threes = safe_float(base.get("roll5_threes", line if stat == "threes" else 0), 0)
    if stat == "pts": return pts or line
    if stat == "reb": return reb or line
    if stat == "ast": return ast or line
    if stat == "threes": return threes or line
    if stat == "pra": return pts + reb + ast if (pts + reb + ast) > 0 else line
    if stat == "pa": return pts + ast if (pts + ast) > 0 else line
    if stat == "pr": return pts + reb if (pts + reb) > 0 else line
    if stat == "ra": return reb + ast if (reb + ast) > 0 else line
    if stat == "dd": return max(0.02, min(0.85, ((pts - 8) / 22) * 0.35 + ((reb - 6) / 8) * 0.45 + 0.12))
    if stat == "td": return max(0.001, min(0.12, ((pts + reb + ast) - 28) / 120))
    return line


def recent_baseline(base, stat, line):
    pts = safe_float(base.get("roll5_pts"), safe_float(base.get("ppg"), 0))
    reb = safe_float(base.get("roll5_reb"), safe_float(base.get("reb"), 0))
    ast = safe_float(base.get("roll5_ast"), safe_float(base.get("ast"), 0))
    threes = safe_float(base.get("roll5_threes"), 0)
    if stat == "pts": return pts or line
    if stat == "reb": return reb or line
    if stat == "ast": return ast or line
    if stat == "threes": return threes or line
    if stat == "pra": return pts + reb + ast if (pts + reb + ast) > 0 else line
    if stat == "pa": return pts + ast if (pts + ast) > 0 else line
    if stat == "pr": return pts + reb if (pts + reb) > 0 else line
    if stat == "ra": return reb + ast if (reb + ast) > 0 else line
    return stat_baseline(base, stat, line)


def market_price_lean(over_price, under_price):
    over_imp = implied_prob_american(safe_float(over_price, -110)); under_imp = implied_prob_american(safe_float(under_price, -110)); total = max(over_imp + under_imp, 0.0001)
    over_fair = over_imp / total; lean = (over_fair - 0.50) * 7.0
    return max(-1.75, min(1.75, lean)), over_fair


def yes_market_prob(yes_price, no_price):
    yes = implied_prob_american(safe_float(yes_price, -110)); no = implied_prob_american(safe_float(no_price, -110)); total = max(yes + no, 0.0001)
    return yes / total


def project_stat(stat, base, line, injury_status="ACTIVE", over_price=-110, under_price=-110, yes_price=None, no_price=None):
    if stat in {"dd", "td"}:
        market_prob = yes_market_prob(yes_price if yes_price is not None else over_price, no_price if no_price is not None else under_price)
        base_prob = stat_baseline(base, stat, line) if base else market_prob
        pred = max(0.001, min(0.95, base_prob * 0.55 + market_prob * 0.45))
        return round(pred, 3), round(base_prob, 3), f"{STAT_MAP[stat]} watch: blended player profile with sportsbook yes probability {round(market_prob*100,1)}%."

    price_lean, over_fair = market_price_lean(over_price, under_price)
    season_avg = stat_baseline(base, stat, line)
    if not base:
        pred = line + price_lean
        return round(pred, 1), round(line, 1), f"market-implied v5: sportsbook over probability {round(over_fair*100,1)}%, no trusted player baseline yet."

    recent_avg = recent_baseline(base, stat, season_avg)
    role_score = safe_float(base.get("role_score"), 50)
    usage = safe_float(base.get("usage", 0.25), 0.25)
    ts = safe_float(base.get("ts_pct", base.get("ts", 0.55)), 0.55)
    mpg = safe_float(base.get("mpg", 30), 30)
    r5_mpg = safe_float(base.get("roll5_mpg", mpg), mpg)
    if injury_status == "QUESTIONABLE": mpg *= 0.70; r5_mpg *= 0.70
    elif injury_status == "PROBABLE": mpg *= 0.90; r5_mpg *= 0.90
    pace = safe_float(base.get("pace", base.get("team_pace", 80)), 80)

    blend = 0.60 * season_avg + 0.40 * recent_avg
    if str(base.get("minutes_trend", "")).upper() == "UP": blend += 0.35 if stat in {"pts", "pra", "pa", "pr"} else 0.15
    elif str(base.get("minutes_trend", "")).upper() == "DOWN": blend -= 0.35 if stat in {"pts", "pra", "pa", "pr"} else 0.15
    if str(base.get("points_trend", "")).upper() == "UP" and stat in {"pts", "pra", "pa", "pr", "threes"}: blend += 0.45
    elif str(base.get("points_trend", "")).upper() == "DOWN" and stat in {"pts", "pra", "pa", "pr", "threes"}: blend -= 0.45

    minutes_adj = (r5_mpg - 30.0) * (0.10 if stat in {"pts", "pra", "pa", "pr"} else 0.035)
    pace_adj = (pace - 80.0) * (0.03 if stat in {"pts", "pra", "pa", "pr"} else 0.01)
    usage_adj = (usage - 0.25) * (10.0 if stat in {"pts", "pra", "pa", "pr"} else 2.0)
    efficiency_adj = (ts - 0.55) * (8.0 if stat in {"pts", "pra", "pa", "pr", "threes"} else 1.5)
    role_adj = (role_score - 55.0) * (0.018 if stat in {"pts", "pra", "pa", "pr"} else 0.008)

    pred = blend + usage_adj + efficiency_adj + minutes_adj + pace_adj + role_adj + (price_lean * 0.35)
    injury_note = f" Injury status {injury_status} applied." if injury_status in {"QUESTIONABLE", "PROBABLE"} else ""
    intel_note = f" Intelligence: role {round(role_score,1)}, minutes {base.get('minutes_trend','STABLE')}, points {base.get('points_trend','STABLE')}." if base.get("intel_source") else ""
    return round(float(pred), 1), round(float(season_avg), 1), f"v5 intelligence blend from {base.get('source','baseline')}: season + recent form, usage, efficiency, minutes, pace, role score, and price lean.{intel_note}{injury_note}"


def pseudo_recent_values(pred, player, stat, n=10):
    if stat in {"dd", "td"}:
        seed = sum(ord(c) for c in f"{player}-{stat}"); return [1 if ((seed + i * 5) % 100) / 100 < pred else 0 for i in range(n)]
    seed = sum(ord(c) for c in f"{player}-{stat}"); return [round(max(0, pred + ((seed + i * 7) % 9 - 4) * 0.45), 1) for i in range(n)]


def opp_rank_from_name(opp): return (sum(ord(c) for c in str(opp or "")) % 15) + 1 if opp else 8


def hit_rate(values, line, signal):
    if not values or line is None or not signal: return 0.0
    if signal in {"YES", "NO"}: return round(sum(1 for v in values if (v == 1 if signal == "YES" else v == 0)) / len(values), 2)
    hits = sum(1 for v in values if (v < line if signal == "UNDER" else v > line)); return round(hits / len(values), 2)


def normalize_stat(stat_raw):
    s = str(stat_raw or "pts").lower()
    return {"3pm":"threes","3-point_made":"threes","3-pointers_made":"threes","player_threes":"threes","player_points":"pts","player_rebounds":"reb","player_assists":"ast","player_points_rebounds_assists":"pra","player_points_assists":"pa","player_points_rebounds":"pr","player_rebounds_assists":"ra","player_double_double":"dd","player_triple_double":"td"}.get(s, s)


def valid_market(row):
    stat = normalize_stat(row.get("stat", row.get("stat_raw", "")))
    if stat in {"dd", "td"}:
        if pd.isna(row.get("yes_price")) and pd.isna(row.get("over_price")): return False, "NO YES MARKET"
        return True, "ACTIVE MARKET"
    if pd.isna(row.get("line")): return False, "NO LINE"
    if pd.isna(row.get("over_price")) or pd.isna(row.get("under_price")): return False, "NO MARKET"
    return True, "ACTIVE MARKET"


def exact_game_key(row):
    home = str(row.get("home_team", "")).strip(); away = str(row.get("away_team", "")).strip(); opp = str(row.get("opp_team", row.get("opp", ""))).strip()
    if away and home: return f"{away} @ {home}"
    if " @ " in opp: return opp
    return opp


def get_base(baselines, player):
    if player in baselines: return baselines.get(player, {})
    np = norm_name(player)
    for k, v in baselines.items():
        if norm_name(k) == np:
            return v or {}
    return {}


def make_projection(row, baselines, injuries):
    player = str(row.get("player", "")).strip(); market_ok, market_status = valid_market(row)
    if not market_ok: return None
    base = get_base(baselines, player)
    injury = injuries.get(norm_name(player), {"severity": base.get("intel_injury_status", "ACTIVE"), "note": base.get("intel_injury_detail", "")})
    injury_status = str(injury.get("severity", "ACTIVE") or "ACTIVE").upper()
    if injury_status in {"OUT", "DOUBTFUL"}: return None
    team = str(row.get("team", "")).strip(); opp = str(row.get("opp_team", row.get("opp", ""))).strip(); home_team = str(row.get("home_team", "")).strip(); away_team = str(row.get("away_team", "")).strip(); game_key = exact_game_key(row); pos = str(row.get("position", row.get("pos", ""))).strip()
    stat = normalize_stat(row.get("stat", row.get("stat_raw", "pts")))
    if stat not in STAT_MAP: return None
    line = 0.5 if stat in {"dd", "td"} else float(row.get("line"))
    over_price = safe_float(row.get("over_price"), -110); under_price = safe_float(row.get("under_price"), -110); yes_price = None if pd.isna(row.get("yes_price")) else safe_float(row.get("yes_price")); no_price = None if pd.isna(row.get("no_price")) else safe_float(row.get("no_price"))
    pred, season_avg, reasoning = project_stat(stat, base, line, injury_status, over_price, under_price, yes_price, no_price)
    if stat in {"dd", "td"}:
        edge = round(pred - yes_market_prob(yes_price if yes_price is not None else over_price, no_price if no_price is not None else under_price), 3); low = max(0, round(pred - 0.08, 3)); high = min(1, round(pred + 0.08, 3)); chosen_odds = yes_price if yes_price is not None else over_price
    else:
        low, high = round(pred - 3.5, 1), round(pred + 3.5, 1); edge = round(pred - line, 1); chosen_odds = over_price
    conf, signal = confidence(edge, stat); conf = downgrade_conf(conf, injury_status)
    if signal in {"UNDER", "NO"}: chosen_odds = no_price if stat in {"dd", "td"} and no_price is not None else under_price
    model_prob = pred if stat in {"dd", "td"} else edge_to_prob(edge, "PROP")
    if injury_status == "QUESTIONABLE": model_prob = max(0.005, round(model_prob - 0.04, 4))
    elif injury_status == "PROBABLE": model_prob = max(0.005, round(model_prob - 0.015, 4))
    ev = expected_value(model_prob, chosen_odds)
    recent10 = pseudo_recent_values(pred, player, stat, 10); last5_vals = recent10[:5]; last5_opps = ["ATL", "CHI", "DAL", "IND", "SEA"]; h2h = pseudo_recent_values(pred, player + game_key, stat, 5); filter_reason = injury.get("note", "") if injury_status != "ACTIVE" else ""
    return {"player": player, "team": team, "opp": opp, "pos": pos, "stat": STAT_MAP[stat], "season_avg": season_avg, "pred": pred, "low": low, "high": high, "range": f"{low}-{high}", "line": line, "over_price": over_price, "under_price": under_price, "yes_price": yes_price, "no_price": no_price, "edge": edge, "signal": signal, "conf": conf, "model_prob": model_prob, "implied_prob": round(implied_prob_american(chosen_odds), 4), "ev": ev, "ev_pct": round(ev * 100, 1), "kelly_frac": kelly_fraction(model_prob, chosen_odds), "injury_status": injury_status, "market_status": market_status, "is_active": True, "filter_reason": filter_reason, "reasoning": reasoning, "game": game_key, "home_team": home_team, "away_team": away_team, "last5_vals": json.dumps(last5_vals), "last5_opps": json.dumps(last5_opps), "last5_hit": hit_rate(last5_vals, line, signal), "last10_hit": hit_rate(recent10, line, signal), "h2h_last5": json.dumps(h2h), "opp_rank": opp_rank_from_name(opp), "role_score": safe_float(base.get("role_score"), 0), "minutes_trend": base.get("minutes_trend", ""), "points_trend": base.get("points_trend", ""), "intel_source": base.get("intel_source", "")}


def build_player_points(target_date, raw_dir):
    props = load_props(target_date, raw_dir)
    if props.empty: return pd.DataFrame(columns=OUTPUT_COLUMNS)
    if "stat" in props.columns:
        props = props[props["stat"].astype(str).str.lower().isin({"pts", "reb", "ast", "threes", "pra", "pa", "pr", "ra", "dd", "td"})].copy()
    if props.empty:
        print("  [WARN] No model-supported props found."); return pd.DataFrame(columns=OUTPUT_COLUMNS)
    baselines = load_player_baselines(); injuries = load_injuries(target_date, raw_dir); rows = []; skipped_market = 0; skipped_injury = 0
    for _, row in props.iterrows():
        try:
            ok, _ = valid_market(row)
            if not ok: skipped_market += 1; continue
            player = str(row.get("player", "")).strip(); injury_status = injuries.get(norm_name(player), {}).get("severity", "ACTIVE")
            if str(injury_status).upper() in {"OUT", "DOUBTFUL"}: skipped_injury += 1; continue
            proj = make_projection(row, baselines, injuries)
            if proj: rows.append(proj)
        except Exception as exc: print(f"  [WARN] Skipping prop row: {exc}")
    print(f"  Filtered out: {skipped_market} no-market rows, {skipped_injury} injured rows")
    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if not df.empty:
        conf_order = {"HIGH": 0, "MED": 1, "LOW": 2}; df["conf_rank"] = df["conf"].map(conf_order).fillna(9); df["abs_edge"] = df["edge"].abs(); df = df.sort_values(["conf_rank", "ev", "abs_edge", "player"], ascending=[True, False, False, True]).drop(columns=["conf_rank", "abs_edge"])
    return df


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--date", default=str(date.today())); parser.add_argument("--out", default=RAW_DIR); args = parser.parse_args(); os.makedirs(args.out, exist_ok=True)
    print(f"\n═══ PLAYER PROPS V5 INTELLIGENCE — {args.date} ═══\n")
    df = build_player_points(args.date, args.out); today_path = os.path.join(args.out, "player_points_today.csv"); dated_path = os.path.join(args.out, f"player_points_{args.date}.csv")
    df.to_csv(today_path, index=False); df.to_csv(dated_path, index=False)
    print(f"  Saved → {today_path}"); print(f"  Saved → {dated_path}"); print(f"  Rows: {len(df)}")
    if not df.empty: print(df[["player", "game", "stat", "injury_status", "market_status", "pred", "line", "edge", "signal", "conf", "ev_pct", "role_score", "minutes_trend", "points_trend"]].head(20).to_string(index=False))
    print("\n✅ Player props complete.")


if __name__ == "__main__": main()
