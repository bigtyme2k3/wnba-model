"""V5 Phase 1: synchronize one authoritative WNBA game state across all decision artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DASH = Path("data/dashboard")
WH = Path("data/warehouse")
MASTER_PATHS = [DASH / "wnba_master.json", Path("data/master/wnba_master.json")]
STATE_PATHS = [DASH / "wnba_game_state.json", WH / "wnba_game_state.json"]
ACTION_PATHS = [
    DASH / "wnba_decision_engine_final.json", WH / "wnba_decision_engine_final.json",
    DASH / "wnba_portfolio_optimizer_v2.json", WH / "wnba_portfolio_optimizer_v2.json",
    DASH / "wnba_risk_allocation.json", WH / "wnba_risk_allocation.json",
    DASH / "wnba_portfolio_dashboard.json", WH / "wnba_portfolio_dashboard.json",
]
INJURY_PATHS = [DASH / "wnba_injury_intelligence.json", WH / "wnba_injury_intelligence.json"]
ROW_KEYS = (
    "rows", "props", "decisions", "top_decisions", "qualified_bets", "final_decisions",
    "recommended_card", "candidates", "bets", "portfolio", "allocations", "best_bets",
    "top_plays", "recommendations",
)


def load(path: Path, default: Any):
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def dump(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(value, path.open("w", encoding="utf-8"), indent=2, allow_nan=False)


def norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def parse_time(value: Any):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def state_for(game: dict, now: datetime) -> str:
    raw = norm(game.get("status") or game.get("game_status") or game.get("state") or game.get("event_status"))
    if any(token in raw for token in ("final", "completed", "closed", "postgame", "ended")):
        return "FINAL"
    if any(token in raw for token in ("live", "in progress", "halftime", "q1", "q2", "q3", "q4", "ot")):
        return "LIVE"
    start = parse_time(game.get("commence_time") or game.get("start_time") or game.get("game_time") or game.get("scheduled"))
    if start:
        if now >= start + timedelta(hours=4):
            return "FINAL"
        if now >= start:
            return "LIVE"
    return "PREGAME"


def teams_for(game: dict) -> list[str]:
    values = []
    for key in ("away_team", "home_team", "away", "home"):
        value = str(game.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def row_locked(row: dict, locked_teams: set[str], locked_ids: set[str]) -> bool:
    team = str(row.get("team") or row.get("team_name") or "").strip()
    opponent = str(row.get("opponent") or "").strip()
    game_id = str(row.get("game_id") or row.get("event_id") or row.get("matchup_id") or "")
    matchup = norm(row.get("game") or row.get("matchup") or "")
    return (
        team in locked_teams or opponent in locked_teams or game_id in locked_ids
        or any(norm(team_name) in matchup for team_name in locked_teams)
    )


def synchronize_rows(rows: list, locked_teams: set[str], locked_ids: set[str]) -> list:
    output = []
    for source in rows or []:
        row = dict(source)
        locked = row_locked(row, locked_teams, locked_ids)
        row["pregame_eligible"] = not locked
        row["game_locked"] = locked
        if locked:
            row["game_state"] = "LIVE_OR_FINAL"
            row["eligible"] = False
            row["eligible_for_bet"] = False
            row["final_action"] = "PASS"
            row["recommendation"] = "PASS"
            row["blocked_reason"] = "Game live/final — pregame market locked"
        output.append(row)
    return output


def main():
    now = datetime.now(timezone.utc)
    source_master = next((load(path, {}) for path in MASTER_PATHS if path.exists()), {})
    games = source_master.get("games", []) or source_master.get("today_games", []) or []

    records = []
    locked_teams: set[str] = set()
    locked_ids: set[str] = set()
    for game in games:
        state = state_for(game, now)
        teams = teams_for(game)
        game_id = str(game.get("game_id") or game.get("event_id") or game.get("id") or "")
        actionable = state == "PREGAME"
        record = {
            "game_id": game_id,
            "matchup": game.get("matchup") or " @ ".join(teams),
            "teams": teams,
            "state": state,
            "actionable": actionable,
            "start_time": game.get("commence_time") or game.get("start_time") or game.get("game_time"),
        }
        records.append(record)
        game["game_state"] = state
        game["pregame_eligible"] = actionable
        if not actionable:
            locked_teams.update(teams)
            if game_id:
                locked_ids.add(game_id)

    payload = {
        "generated_at_utc": now.isoformat(),
        "source_of_truth": "wnba_v5_live_state_sync",
        "games": records,
        "summary": {
            "pregame": sum(r["state"] == "PREGAME" for r in records),
            "live": sum(r["state"] == "LIVE" for r in records),
            "final": sum(r["state"] == "FINAL" for r in records),
            "locked_teams": sorted(locked_teams),
        },
    }
    for path in STATE_PATHS:
        dump(path, payload)

    for path in MASTER_PATHS:
        data = load(path, None)
        if data is None:
            continue
        target_games = data.get("games", []) or data.get("today_games", []) or []
        for game in target_games:
            game["game_state"] = state_for(game, now)
            game["pregame_eligible"] = game["game_state"] == "PREGAME"
        for key in ROW_KEYS:
            if isinstance(data.get(key), list):
                data[key] = synchronize_rows(data[key], locked_teams, locked_ids)
        data["game_state_sync"] = payload
        dump(path, data)

    for path in ACTION_PATHS:
        data = load(path, None)
        if data is None:
            continue
        if isinstance(data, list):
            data = synchronize_rows(data, locked_teams, locked_ids)
        elif isinstance(data, dict):
            for key in ROW_KEYS:
                if isinstance(data.get(key), list):
                    data[key] = synchronize_rows(data[key], locked_teams, locked_ids)
            data["game_state_sync"] = payload
        dump(path, data)

    for path in INJURY_PATHS:
        data = load(path, None)
        if data is None:
            continue
        rows = []
        for source in data.get("adjustments", []) or []:
            row = dict(source)
            locked = str(row.get("team") or "").strip() in locked_teams
            row["pregame_eligible"] = not locked
            row["game_locked"] = locked
            if locked:
                row["headline_eligible"] = False
            rows.append(row)
        data["adjustments"] = rows
        data["game_state_sync"] = payload
        dump(path, data)

    phase = {
        "phase": 1,
        "name": "Live State Synchronization",
        "status": "COMPLETE",
        "generated_at_utc": now.isoformat(),
        "qa_gate": "pending_workflow_verification",
        "artifact": "data/dashboard/wnba_game_state.json",
    }
    dump(DASH / "wnba_v5_phase_status.json", phase)
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
