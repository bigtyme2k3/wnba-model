#!/usr/bin/env python3
"""Generate per-record diagnostics for unresolved WNBA ALT archive rows.

Phase 2 is diagnostic only: it never grades or mutates frozen archive rows.
It combines the pending manual-recovery report with the official ESPN WNBA
schedule/box scores and emits an actionable failure reason for every pending row.
"""
from __future__ import annotations

import csv
import json
import math
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

PENDING = Path("data/dashboard/wnba_alt_pending_manual_recovery.json")
SCHEDULE_AUDIT = Path("data/dashboard/wnba_alt_schedule_audit.json")
OUT_JSON = Path("data/dashboard/wnba_alt_phase2_diagnostics.json")
OUT_CSV = Path("data/dashboard/wnba_alt_phase2_diagnostics.csv")
WAREHOUSE_JSON = Path("data/warehouse/wnba_alt_phase2_diagnostics.json")

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def norm(value: Any) -> str:
    text = str(value or "").strip().lower().replace("’", "'")
    for ch in ".,()-_/":
        text = text.replace(ch, " ")
    return " ".join(text.split())


def norm_player(value: Any) -> str:
    return norm(value).replace("ë", "e").replace("é", "e").replace("á", "a").replace("í", "i").replace("ó", "o").replace("ú", "u")


def num(value: Any) -> float | None:
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def fetch_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    request_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(request_url, headers={"User-Agent": "wnba-model/5.0 (+github-actions)"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def scoreboard(game_date: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if game_date not in cache:
        cache[game_date] = fetch_json(SCOREBOARD, {"dates": game_date.replace("-", ""), "limit": "100"})
    return cache[game_date]


def summary(event_id: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if event_id not in cache:
        cache[event_id] = fetch_json(SUMMARY, {"event": event_id})
    return cache[event_id]


def event_info(event: dict[str, Any]) -> dict[str, Any]:
    comp = ((event.get("competitions") or [{}])[0])
    competitors = comp.get("competitors") or []
    home = away = ""
    for c in competitors:
        team = (c.get("team") or {}).get("displayName") or (c.get("team") or {}).get("shortDisplayName") or ""
        if c.get("homeAway") == "home":
            home = team
        elif c.get("homeAway") == "away":
            away = team
    st = ((event.get("status") or {}).get("type") or {})
    completed = bool(st.get("completed")) or str(st.get("state") or "").lower() == "post"
    description = str(st.get("description") or st.get("detail") or "")
    return {
        "event_id": str(event.get("id") or ""),
        "game": f"{away} @ {home}" if away or home else "",
        "away": away,
        "home": home,
        "completed": completed,
        "status": description,
    }


def parse_game(game: str) -> tuple[str, str]:
    if " @ " not in str(game):
        return "", ""
    away, home = str(game).split(" @ ", 1)
    return away.strip(), home.strip()


def matchup_equal(a: str, b: str) -> bool:
    aa, ah = parse_game(a)
    ba, bh = parse_game(b)
    return norm(aa) == norm(ba) and norm(ah) == norm(bh)


def player_presence(payload: dict[str, Any], player_name: str) -> tuple[str, dict[str, float]]:
    """Return (PLAYED|DNP|ABSENT, derived stats)."""
    wanted = norm_player(player_name)
    for team_block in (payload.get("boxscore") or {}).get("players") or []:
        for stat_group in team_block.get("statistics") or []:
            labels = [str(x).strip().upper() for x in (stat_group.get("labels") or stat_group.get("names") or [])]
            for athlete_row in stat_group.get("athletes") or []:
                athlete = athlete_row.get("athlete") or {}
                display = athlete.get("displayName") or athlete.get("fullName") or ""
                if norm_player(display) != wanted:
                    continue
                values = athlete_row.get("stats") or []
                raw = {labels[i]: values[i] for i in range(min(len(labels), len(values)))}
                pts = num(raw.get("PTS")); reb = num(raw.get("REB")); ast = num(raw.get("AST"))
                three = raw.get("3PT")
                if isinstance(three, str) and "-" in three:
                    three = num(three.split("-", 1)[0])
                else:
                    three = num(three)
                if pts is None and reb is None and ast is None and not values:
                    return "DNP", {}
                stats: dict[str, float] = {}
                for key, val in (("PTS", pts), ("REB", reb), ("AST", ast), ("3PM", three)):
                    if val is not None:
                        stats[key] = float(val)
                if pts is not None and ast is not None: stats["PA"] = pts + ast
                if pts is not None and reb is not None: stats["PR"] = pts + reb
                if reb is not None and ast is not None: stats["RA"] = reb + ast
                if pts is not None and reb is not None and ast is not None: stats["PRA"] = pts + reb + ast
                return "PLAYED", stats
    return "ABSENT", {}


def audit_map(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r.get("row_key") or ""): r for r in (audit.get("rows") or []) if isinstance(r, dict)}


def pending_key(row: dict[str, Any]) -> str:
    return "|".join([
        str(row.get("date") or "")[:10],
        norm(row.get("player")),
        norm(row.get("stat")),
        norm(row.get("side")),
        str(row.get("line") if row.get("line") is not None else ""),
    ])


def diagnose(row: dict[str, Any], audit_row: dict[str, Any] | None,
             sb_cache: dict[str, dict[str, Any]], sum_cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    date = str(row.get("date") or "")[:10]
    game = str(row.get("game") or "")
    player = str(row.get("player") or "")
    stat = str(row.get("stat") or "").upper()

    try:
        events = [event_info(e) for e in scoreboard(date, sb_cache).get("events") or []]
    except Exception as exc:
        return {"failure_reason": "SCHEDULE_FETCH_ERROR", "diagnostic_detail": str(exc)}

    exact = [e for e in events if matchup_equal(e["game"], game)]
    exact_completed = [e for e in exact if e["completed"]]
    exact_noncompleted = [e for e in exact if not e["completed"]]

    # ESPN scoreboard date is the only source that may establish a game on the archived day.
    if exact_noncompleted and not exact_completed:
        return {
            "failure_reason": "POSTPONED_OR_NONCOMPLETED_GAME",
            "diagnostic_detail": f"Official matchup exists on {date} but is not completed: {exact_noncompleted[0].get('status')}",
            "official_event_id": exact_noncompleted[0].get("event_id"),
        }

    if exact_completed:
        event = exact_completed[0]
        try:
            payload = summary(str(event["event_id"]), sum_cache)
            presence, stats = player_presence(payload, player)
        except Exception as exc:
            return {"failure_reason": "BOX_SCORE_FETCH_ERROR", "diagnostic_detail": str(exc), "official_event_id": event.get("event_id")}
        if presence == "DNP":
            return {"failure_reason": "DNP", "diagnostic_detail": "Player is listed in the official box score without playable stats.", "official_event_id": event.get("event_id")}
        if presence == "ABSENT":
            return {"failure_reason": "PLAYER_NOT_IN_BOX_SCORE", "diagnostic_detail": "Official game is valid but player is absent from its box score.", "official_event_id": event.get("event_id")}
        if stat not in stats:
            return {"failure_reason": "STAT_NOT_DERIVABLE", "diagnostic_detail": f"Player played, but {stat} could not be derived from the official box score.", "official_event_id": event.get("event_id"), "available_stats": stats}
        return {"failure_reason": "GAME_LOG_JOIN_FAILURE", "diagnostic_detail": f"Official player actual exists ({stat}={stats[stat]}) but the archive grader did not join it.", "official_event_id": event.get("event_id"), "official_actual": stats[stat]}

    # No matching game occurred on archived date. Use audit to distinguish unique alias vs repeated matchup.
    classification = str((audit_row or {}).get("classification") or "")
    candidates = [g for g in ((audit_row or {}).get("candidate_games") or []) if isinstance(g, dict) and g.get("completed")]
    if classification == "repeated_matchup_ambiguous" or len(candidates) > 1:
        dates = sorted({str(g.get("date") or "")[:10] for g in candidates if g.get("date")})
        return {"failure_reason": "REPEATED_MATCHUP_AMBIGUOUS", "diagnostic_detail": "Archived date has no exact official matchup and multiple completed candidate meetings exist.", "candidate_dates": dates}
    if classification == "unique_schedule_alias" or len(candidates) == 1:
        c = candidates[0] if candidates else {}
        return {"failure_reason": "GAME_DATE_MISMATCH", "diagnostic_detail": "Archived date has no exact official matchup; one completed schedule candidate exists.", "suggested_date": str(c.get("date") or (audit_row or {}).get("suggested_date") or "")[:10], "official_event_id": c.get("event_id")}

    # Check whether player appears in exactly one completed event on that date; this identifies stale game labels.
    player_events = []
    for e in events:
        if not e["completed"] or not e["event_id"]:
            continue
        try:
            presence, stats = player_presence(summary(str(e["event_id"]), sum_cache), player)
        except Exception:
            continue
        if presence == "PLAYED":
            player_events.append({"event_id": e["event_id"], "game": e["game"], "stats": stats})
        elif presence == "DNP":
            player_events.append({"event_id": e["event_id"], "game": e["game"], "dnp": True})
    if len(player_events) == 1:
        pe = player_events[0]
        return {"failure_reason": "WRONG_GAME_LABEL", "diagnostic_detail": f"Archived matchup did not occur, but player maps uniquely to {pe['game']} on this date.", "official_event_id": pe["event_id"], "suggested_game": pe["game"], "official_actual": (pe.get("stats") or {}).get(stat)}

    return {"failure_reason": "NO_OFFICIAL_GAME_MATCH", "diagnostic_detail": "No exact official matchup or unique player event could be established for the archived date."}


def main() -> None:
    pending = load(PENDING, {"rows": []})
    audit = load(SCHEDULE_AUDIT, {"rows": []})
    amap = audit_map(audit)
    sb_cache: dict[str, dict[str, Any]] = {}
    sum_cache: dict[str, dict[str, Any]] = {}
    out_rows = []

    for row in pending.get("rows") or []:
        key = pending_key(row)
        result = diagnose(row, amap.get(key), sb_cache, sum_cache)
        out_rows.append({
            "candidate_id": row.get("candidate_id"),
            "date": row.get("date"),
            "player": row.get("player"),
            "team": row.get("team"),
            "game": row.get("game"),
            "stat": row.get("stat"),
            "side": row.get("side"),
            "line": row.get("line"),
            "sportsbook": row.get("sportsbook"),
            "odds": row.get("odds"),
            "score": row.get("score"),
            "schedule_classification": (amap.get(key) or {}).get("classification"),
            **result,
        })

    counts = Counter(str(r.get("failure_reason") or "UNKNOWN") for r in out_rows)
    payload = {
        "pending_rows": len(out_rows),
        "failure_reason_counts": dict(sorted(counts.items())),
        "rows": out_rows,
    }
    text = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    for path in (OUT_JSON, WAREHOUSE_JSON):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["date","player","team","game","stat","side","line","sportsbook","odds","score","schedule_classification","failure_reason","diagnostic_detail","official_event_id","suggested_date","suggested_game","official_actual","candidate_dates","candidate_id"]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in out_rows:
            rr = dict(r)
            if isinstance(rr.get("candidate_dates"), list): rr["candidate_dates"] = ";".join(rr["candidate_dates"])
            w.writerow(rr)

    print(json.dumps({"pending_rows": len(out_rows), "failure_reason_counts": dict(sorted(counts.items()))}, indent=2))


if __name__ == "__main__":
    main()
