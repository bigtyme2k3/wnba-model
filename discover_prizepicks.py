"""
discover_prizepicks.py
----------------------
Discovers which PrizePicks public API query returns WNBA projections.

Why this exists:
  scrape_props.py currently calls /projections?league_id=7&per_page=250&single_stat=true,
  but that query can return HTTP 200 with zero projections. This script tests
  several public endpoint/query variations and writes a diagnostic report.

Outputs:
  data/raw/prizepicks_discovery.json
  data/raw/prizepicks_discovery_summary.csv

Usage:
  python discover_prizepicks.py --out data/raw
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import pandas as pd
import requests

BASE_URL = "https://api.prizepicks.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Tablet) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://app.prizepicks.com/",
    "Origin": "https://app.prizepicks.com",
}

CANDIDATE_QUERIES = [
    {"league_id": "7", "per_page": "250", "single_stat": "true"},
    {"league_id": "7", "per_page": "250"},
    {"league_id": "7", "per_page": "1000"},
    {"league_id[]": "7", "per_page": "250", "single_stat": "true"},
    {"league_id[]": "7", "per_page": "250"},
    {"league_id": "3", "per_page": "250", "single_stat": "true"},
    {"league_id": "3", "per_page": "250"},
    {"per_page": "250", "single_stat": "true"},
    {"per_page": "250"},
    {"per_page": "1000"},
]


def get_json(path: str, params: dict | None = None) -> tuple[int, dict | None, str]:
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.get(url, headers=HEADERS, params=params or {}, timeout=20)
        text_preview = resp.text[:300].replace("\n", " ")
        if resp.status_code != 200:
            return resp.status_code, None, text_preview
        try:
            return resp.status_code, resp.json(), text_preview
        except Exception:
            return resp.status_code, None, text_preview
    except Exception as exc:
        return 0, None, str(exc)


def count_projection_payload(data: dict | None) -> dict:
    if not data:
        return {"projection_count": 0, "included_count": 0, "leagues": [], "stat_types": [], "sample_players": []}
    rows = data.get("data", []) or []
    included = data.get("included", []) or []
    lookup = {obj.get("id"): obj for obj in included if obj.get("id") is not None}
    leagues = set()
    stat_types = set()
    sample_players = []

    for row in rows:
        attrs = row.get("attributes", {}) or {}
        stat = attrs.get("stat_type") or attrs.get("stat_display")
        if stat:
            stat_types.add(str(stat))
        rels = row.get("relationships", {}) or {}
        league_ref = (rels.get("league", {}) or {}).get("data", {}) or {}
        league_obj = lookup.get(league_ref.get("id"), {}) or {}
        league_attrs = league_obj.get("attributes", {}) or {}
        league_name = league_attrs.get("name") or league_attrs.get("display_name") or league_ref.get("id")
        if league_name:
            leagues.add(str(league_name))
        player_ref = (rels.get("new_player", rels.get("player", {})) or {}).get("data", {}) or {}
        player_obj = lookup.get(player_ref.get("id"), {}) or {}
        player_attrs = player_obj.get("attributes", {}) or {}
        player = player_attrs.get("display_name") or player_attrs.get("name") or attrs.get("name")
        if player and len(sample_players) < 10:
            sample_players.append(str(player))

    return {
        "projection_count": len(rows),
        "included_count": len(included),
        "leagues": sorted(leagues),
        "stat_types": sorted(stat_types),
        "sample_players": sample_players,
    }


def discover_leagues() -> list[dict]:
    results = []
    for path in ["/leagues", "/sports", "/projection_types"]:
        status, data, preview = get_json(path)
        payload = {"path": path, "http_status": status, "preview": preview, "items": []}
        if data:
            rows = data.get("data", []) if isinstance(data, dict) else []
            for row in rows[:200]:
                attrs = row.get("attributes", {}) or {}
                payload["items"].append({
                    "id": row.get("id"),
                    "type": row.get("type"),
                    "name": attrs.get("name") or attrs.get("display_name") or attrs.get("league") or attrs.get("title"),
                    "raw": attrs,
                })
        results.append(payload)
        time.sleep(1.0)
    return results


def run_discovery(out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "league_probe": discover_leagues(),
        "projection_queries": [],
        "best_query": None,
    }

    best = None
    summary_rows = []
    for params in CANDIDATE_QUERIES:
        status, data, preview = get_json("/projections", params)
        counts = count_projection_payload(data)
        item = {
            "path": "/projections",
            "params": params,
            "query_string": urlencode(params),
            "http_status": status,
            "preview": preview,
            **counts,
        }
        report["projection_queries"].append(item)
        summary_rows.append({
            "http_status": status,
            "query_string": item["query_string"],
            "projection_count": counts["projection_count"],
            "included_count": counts["included_count"],
            "leagues": ", ".join(counts["leagues"][:8]),
            "stat_types": ", ".join(counts["stat_types"][:12]),
            "sample_players": ", ".join(counts["sample_players"][:5]),
        })
        if counts["projection_count"] > 0 and (best is None or counts["projection_count"] > best["projection_count"]):
            best = item
        time.sleep(1.0)

    report["best_query"] = best

    json_path = os.path.join(out_dir, "prizepicks_discovery.json")
    csv_path = os.path.join(out_dir, "prizepicks_discovery_summary.csv")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    pd.DataFrame(summary_rows).to_csv(csv_path, index=False)

    print("\n═══ PRIZEPICKS DISCOVERY ═══\n")
    print(f"Saved → {json_path}")
    print(f"Saved → {csv_path}")
    for row in summary_rows:
        print(f"  {row['projection_count']:>4} projections | {row['query_string']}")
    if best:
        print(f"\nBest query: {best['query_string']} ({best['projection_count']} projections)")
    else:
        print("\nNo projection query returned rows.")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/raw")
    args = parser.parse_args()
    run_discovery(args.out)


if __name__ == "__main__":
    main()
