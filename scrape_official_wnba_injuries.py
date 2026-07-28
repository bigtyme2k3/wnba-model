"""Collect the latest official WNBA injury report PDF and normalize it for the model.

Primary source: ak-static.cms.nba.com/referee/wnba_injury PDF reports.
Fallback: existing ESPN/manual collector in scrape_injuries.py.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pdfplumber
import requests

from scrape_injuries import (
    RAW_COLUMNS,
    empty_df,
    fetch_all_injuries,
    normalize_status,
    reallocate_minutes,
    save_projections,
)

BASE = "https://ak-static.cms.nba.com/referee/wnba_injury"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WNBA-Model/1.0)"}
ET = ZoneInfo("America/New_York")


def candidate_urls(target_date: str) -> list[str]:
    day = datetime.strptime(target_date, "%Y-%m-%d").date()
    now_et = datetime.now(ET)
    if day == now_et.date():
        minute = (now_et.minute // 15) * 15
        cursor = now_et.replace(minute=minute, second=0, microsecond=0)
    else:
        cursor = datetime.combine(day, datetime.max.time(), tzinfo=ET).replace(hour=23, minute=45, second=0, microsecond=0)
    floor = datetime.combine(day, datetime.min.time(), tzinfo=ET)
    urls = []
    while cursor >= floor:
        stamp = cursor.strftime("%Y-%m-%d_%I_%M%p")
        urls.append(f"{BASE}/Injury-Report_{stamp}.pdf")
        cursor -= timedelta(minutes=15)
    return urls


def download_latest(target_date: str) -> tuple[bytes | None, str | None]:
    for url in candidate_urls(target_date):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code == 200 and response.content.startswith(b"%PDF"):
                return response.content, url
        except requests.RequestException:
            continue
    return None, None


def clean(value) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def display_name(value: str) -> str:
    value = clean(value)
    if "," in value:
        last, first = [part.strip() for part in value.split(",", 1)]
        return f"{first} {last}".strip()
    return value


def parse_pdf(payload: bytes, target_date: str, source_url: str) -> pd.DataFrame:
    rows = []
    current_game_date = target_date
    current_team = ""
    current_matchup = ""
    current_game_time = ""
    now = datetime.now(timezone.utc).isoformat()

    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                for raw in table:
                    cells = [clean(x) for x in (raw or [])]
                    if len(cells) < 6:
                        continue
                    joined = " ".join(cells).lower()
                    if "player name" in joined and "current status" in joined:
                        continue
                    cells += [""] * (7 - len(cells))
                    game_date, game_time, matchup, team, player, status, reason = cells[:7]
                    if game_date:
                        current_game_date = game_date
                    if game_time:
                        current_game_time = game_time
                    if matchup:
                        current_matchup = matchup
                    if team:
                        current_team = team
                    if not player or player.upper() == "NOT YET SUBMITTED":
                        continue
                    severity = normalize_status(status)
                    if severity in {"ACTIVE", "UNKNOWN"}:
                        continue
                    rows.append({
                        "game_date": target_date,
                        "team": current_team,
                        "player": display_name(player),
                        "player_id": "",
                        "position": "",
                        "status": status or severity,
                        "severity": severity,
                        "injury_type": reason,
                        "detail": f"{reason}; matchup={current_matchup}; game_time={current_game_time}",
                        "return_date": "",
                        "is_out": severity in {"OUT", "DOUBTFUL"},
                        "source": "official_wnba_pdf",
                        "scraped_at": now,
                    })
    frame = pd.DataFrame(rows, columns=RAW_COLUMNS) if rows else empty_df()
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["player"], keep="last")
    return frame


def persist(frame: pd.DataFrame, out_dir: str, target_date: str, source_url: str | None, fallback: bool) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    today_path = os.path.join(out_dir, "injuries_today.csv")
    dated_path = os.path.join(out_dir, f"injuries_{target_date}.csv")
    frame.to_csv(today_path, index=False)
    frame.to_csv(dated_path, index=False)

    hist_path = os.path.join(out_dir, "injuries_historical.csv")
    if not frame.empty:
        if os.path.exists(hist_path):
            hist = pd.read_csv(hist_path)
            if "game_date" in hist.columns:
                hist = hist[hist["game_date"].astype(str) != target_date]
            pd.concat([hist, frame], ignore_index=True).to_csv(hist_path, index=False)
        else:
            frame.to_csv(hist_path, index=False)

    adjustments = reallocate_minutes(frame, [])
    save_projections(adjustments, [], out_dir, target_date)
    status = {
        "status": "ok",
        "target_date": target_date,
        "rows": int(len(frame)),
        "out": int(frame["is_out"].astype(bool).sum()) if not frame.empty else 0,
        "questionable": int((frame.get("severity", pd.Series(dtype=str)) == "QUESTIONABLE").sum()) if not frame.empty else 0,
        "probable": int((frame.get("severity", pd.Series(dtype=str)) == "PROBABLE").sum()) if not frame.empty else 0,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": ["espn", "manual_override"] if fallback else ["official_wnba_pdf"],
        "primary_source": "espn_fallback" if fallback else "official_wnba_pdf",
        "source_url": source_url,
        "teams_checked": int(frame["team"].nunique()) if not frame.empty else 0,
    }
    with open(os.path.join(out_dir, "injuries_status.json"), "w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2)
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out", default="data/raw")
    args = parser.parse_args()

    payload, url = download_latest(args.date)
    fallback = False
    if payload:
        frame = parse_pdf(payload, args.date, url or "")
    else:
        frame = empty_df()

    if frame.empty:
        print("Official WNBA PDF unavailable or contained no parsed player rows; using ESPN/manual fallback.")
        frame = fetch_all_injuries(args.out, args.date)
        fallback = True

    status = persist(frame, args.out, args.date, url, fallback)
    print(json.dumps(status, indent=2))
    if status["rows"] == 0:
        raise SystemExit("No injury rows were available from official or fallback sources")


if __name__ == "__main__":
    main()
