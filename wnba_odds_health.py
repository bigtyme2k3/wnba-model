from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
import pandas as pd


def read_csv(path):
    try:
        if os.path.exists(path):
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def nonempty(v):
    try:
        return not pd.isna(v) and str(v).strip() != ""
    except Exception:
        return False


def build(target):
    team = read_csv(f"data/raw/odds_{target}.csv")
    if team.empty:
        team = read_csv("data/raw/odds_today.csv")
    props = read_csv(f"data/raw/player_points_{target}.csv")
    if props.empty:
        props = read_csv("data/raw/player_points_today.csv")
    source_status = {}
    try:
        source_status = json.load(open("data/raw/odds_source_status.json", encoding="utf-8"))
    except Exception:
        source_status = {}

    team_rows = len(team)
    spread_rows = 0 if team.empty or "spread_home" not in team.columns else int(team["spread_home"].apply(nonempty).sum())
    total_rows = 0 if team.empty or "total" not in team.columns else int(team["total"].apply(nonempty).sum())
    prop_rows = len(props)
    active_prop_rows = 0
    books = []
    if not props.empty:
        if "market_status" in props.columns:
            active_prop_rows = int((props["market_status"].astype(str).str.upper() == "ACTIVE MARKET").sum())
        else:
            active_prop_rows = prop_rows
        for col in ["book", "source", "best_book"]:
            if col in props.columns:
                books += [str(x) for x in props[col].dropna().unique().tolist() if str(x).strip()]
    books = sorted(set(books))[:12]

    if spread_rows or total_rows:
        status = "ok"
        label = "Team odds loaded"
    elif active_prop_rows:
        status = "props_only"
        label = "Player props loaded; team spreads/totals missing"
    elif prop_rows:
        status = "props_unpriced"
        label = "Props exist but price fields need review"
    else:
        status = "missing"
        label = "No odds or props loaded"

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": target,
        "status": status,
        "label": label,
        "summary": {
            "team_odds_rows": team_rows,
            "spread_rows": spread_rows,
            "total_rows": total_rows,
            "prop_rows": prop_rows,
            "active_prop_rows": active_prop_rows,
            "books_detected": books,
        },
        "source_status": source_status,
        "dashboard_note": "Do not treat missing team spreads/totals as a full odds failure when player prop markets are loaded.",
        "next_fix": "Add manual/team odds or a reliable sportsbook feed for spreads and totals; continue using prop markets for player decisions.",
    }
    os.makedirs("data/warehouse", exist_ok=True)
    os.makedirs("data/dashboard", exist_ok=True)
    for p in ["data/warehouse/wnba_odds_health.json", "data/dashboard/wnba_odds_health.json"]:
        json.dump(report, open(p, "w", encoding="utf-8"), indent=2)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=str(date.today()))
    args = ap.parse_args()
    print("Odds health built:", build(args.date)["status"])


if __name__ == "__main__":
    main()
