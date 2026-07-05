"""
player_points.py
----------------
Generates WNBA player points projections and compares them to PrizePicks lines.

Input:
  data/raw/props_today.csv or data/raw/props_raw_YYYY-MM-DD.csv from scrape_props.py

Output:
  data/raw/player_points_today.csv
  data/raw/player_points_YYYY-MM-DD.csv

Columns:
  player, team, opp, pos, season_avg, pred, low, high, range,
  line, edge, signal, conf, reasoning, game

This is intentionally lightweight for GitHub Actions/tablet-only workflow.
When a player is in daily_runner.PLAYER_PROPS, it uses that baseline.
Otherwise it starts from the PrizePicks line and marks the play as no-edge.
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime

import pandas as pd

RAW_DIR = "data/raw"


def load_player_baselines() -> dict:
    """Load simple baseline player stats from daily_runner if available."""
    try:
        from daily_runner import PLAYER_PROPS
        return PLAYER_PROPS or {}
    except Exception as exc:
        print(f"  [WARN] Could not import PLAYER_PROPS from daily_runner.py: {exc}")
        return {}


def load_props(target_date: str, raw_dir: str) -> pd.DataFrame:
    candidates = [
        os.path.join(raw_dir, f"props_raw_{target_date}.csv"),
        os.path.join(raw_dir, "props_today.csv"),
    ]
    for path in candidates:
        if os.path.exists(path):
            df = pd.read_csv(path)
            print(f"  Loaded props: {path} ({len(df)} rows)")
            return df
    print("  [WARN] No PrizePicks props file found.")
    return pd.DataFrame()


def confidence(edge: float | None) -> tuple[str, str | None]:
    if edge is None:
        return "LOW", None
    abs_edge = abs(edge)
    if abs_edge >= 3.0:
        return "HIGH", "OVER" if edge > 0 else "UNDER"
    if abs_edge >= 1.5:
        return "MED", "OVER" if edge > 0 else "UNDER"
    return "LOW", None


def make_projection(row: pd.Series, baselines: dict) -> dict:
    player = str(row.get("player", "")).strip()
    team = str(row.get("team", "")).strip()
    opp = str(row.get("opp_team", row.get("opp", ""))).strip()
    pos = str(row.get("position", "")).strip()
    line = float(row.get("line"))

    base = baselines.get(player, {})
    season_avg = float(base.get("roll5_pts", line))

    # Lightweight points projection.
    # Known players use model baseline from daily_runner; unknown players stay near market.
    if base:
        usage = float(base.get("usage", 0.25))
        ts = float(base.get("ts", 0.55))
        mpg = float(base.get("mpg", 30))
        usage_adj = (usage - 0.25) * 10.0
        efficiency_adj = (ts - 0.55) * 8.0
        minutes_adj = (mpg - 30.0) * 0.12
        pred = season_avg + usage_adj + efficiency_adj + minutes_adj
        reasoning = "Baseline from daily_runner.PLAYER_PROPS with usage, efficiency, and minutes adjustment."
    else:
        pred = line
        reasoning = "No player baseline found yet; market line used as neutral placeholder."

    pred = round(float(pred), 1)
    low = round(pred - 3.5, 1)
    high = round(pred + 3.5, 1)
    edge = round(pred - line, 1)
    conf, signal = confidence(edge)

    game = f"{team} vs {opp}" if opp else team
    return {
        "player": player,
        "team": team,
        "opp": opp,
        "pos": pos,
        "season_avg": round(season_avg, 1),
        "pred": pred,
        "low": low,
        "high": high,
        "range": f"{low}-{high}",
        "line": line,
        "edge": edge,
        "signal": signal,
        "conf": conf,
        "reasoning": reasoning,
        "game": game,
    }


def build_player_points(target_date: str, raw_dir: str) -> pd.DataFrame:
    props = load_props(target_date, raw_dir)
    if props.empty:
        return pd.DataFrame(columns=[
            "player", "team", "opp", "pos", "season_avg", "pred", "low", "high", "range",
            "line", "edge", "signal", "conf", "reasoning", "game"
        ])

    # PrizePicks points props are normalized to stat == pts by scrape_props.py.
    if "stat" in props.columns:
        props = props[props["stat"].astype(str).str.lower().eq("pts")].copy()
    elif "stat_raw" in props.columns:
        props = props[props["stat_raw"].astype(str).str.lower().eq("points")].copy()

    if props.empty:
        print("  [WARN] No points props found.")
        return pd.DataFrame()

    baselines = load_player_baselines()
    rows = []
    for _, row in props.iterrows():
        try:
            if pd.isna(row.get("line")):
                continue
            rows.append(make_projection(row, baselines))
        except Exception as exc:
            print(f"  [WARN] Skipping prop row: {exc}")

    df = pd.DataFrame(rows)
    if not df.empty:
        df["abs_edge"] = df["edge"].abs()
        df = df.sort_values(["abs_edge", "player"], ascending=[False, True]).drop(columns=["abs_edge"])
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out", default=RAW_DIR)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    print(f"\n═══ PLAYER POINTS — {args.date} ═══\n")
    df = build_player_points(args.date, args.out)

    today_path = os.path.join(args.out, "player_points_today.csv")
    dated_path = os.path.join(args.out, f"player_points_{args.date}.csv")
    df.to_csv(today_path, index=False)
    df.to_csv(dated_path, index=False)

    print(f"  Saved → {today_path}")
    print(f"  Saved → {dated_path}")
    print(f"  Players: {len(df)}")
    if not df.empty:
        print(df[["player", "team", "opp", "pred", "line", "edge", "signal", "conf"]].head(15).to_string(index=False))
    print("\n✅ Player points complete.")


if __name__ == "__main__":
    main()
