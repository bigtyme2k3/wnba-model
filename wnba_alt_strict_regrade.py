"""Strictly promote unresolved ALT history against completed player-games.

Final grades are immutable. Pending rows are promoted only when game identity is
strictly resolved. Duplicate warehouse records for the same player/date/matchup
may be resolved when every candidate reports the same requested-stat value;
this treats provider duplicates as evidence, not as different games.
"""
from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from wnba_alt_performance_tracker import stat_value, outcome, one_unit_profit

ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
REPORT = Path("data/dashboard/wnba_alt_strict_regrade.json")
WAREHOUSE_REPORT = Path("data/warehouse/wnba_alt_strict_regrade.json")
STRICT_SOURCE = "player_game_log_warehouse_strict_match"
FINAL = {"WIN", "LOSS", "PUSH", "VOID"}
ET = ZoneInfo("America/New_York")

TEAM_ALIASES = {
    "la sparks":"los angeles sparks","los angeles":"los angeles sparks","sparks":"los angeles sparks",
    "ny liberty":"new york liberty","new york":"new york liberty","liberty":"new york liberty",
    "gs valkyries":"golden state valkyries","golden state":"golden state valkyries","valkyries":"golden state valkyries",
    "lv aces":"las vegas aces","las vegas":"las vegas aces","aces":"las vegas aces",
    "washington":"washington mystics","mystics":"washington mystics",
    "connecticut":"connecticut sun","sun":"connecticut sun",
    "phoenix":"phoenix mercury","mercury":"phoenix mercury",
    "atlanta":"atlanta dream","dream":"atlanta dream",
    "dallas":"dallas wings","wings":"dallas wings",
    "seattle":"seattle storm","storm":"seattle storm",
    "chicago":"chicago sky","sky":"chicago sky",
    "minnesota":"minnesota lynx","lynx":"minnesota lynx",
    "indiana":"indiana fever","fever":"indiana fever",
    "portland":"portland fire","fire":"portland fire",
    "toronto":"toronto tempo","tempo":"toronto tempo",
}


def norm(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().replace("’", "'").split())


def team_norm(v: Any) -> str:
    text = re.sub(r"[^a-z0-9' ]+", " ", norm(v))
    text = " ".join(text.split())
    return TEAM_ALIASES.get(text, text)


def parse_time(v: Any) -> datetime | None:
    try:
        text = str(v or "").strip().replace("Z", "+00:00")
        if not text:
            return None
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def frozen_game_date(row: dict[str, Any]) -> str:
    dt = parse_time(row.get("game_time"))
    return dt.astimezone(ET).date().isoformat() if dt else ""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except Exception:
            pass
    return out


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as h:
        for row in rows:
            h.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def game_pair(v: Any) -> frozenset[str]:
    text = str(v or "").strip()
    if "@" not in text:
        return frozenset()
    away, home = text.split("@", 1)
    parts = [team_norm(away), team_norm(home)]
    return frozenset(parts) if all(parts) and parts[0] != parts[1] else frozenset()


def team_pair(row: dict[str, Any]) -> frozenset[str]:
    for key in ("game", "matchup", "opponent"):
        pair = game_pair(row.get(key))
        if pair:
            return pair
    away = team_norm(row.get("away_team")); home = team_norm(row.get("home_team"))
    if away and home and away != home:
        return frozenset((away, home))
    team = team_norm(row.get("team") or row.get("team_name"))
    opp = team_norm(row.get("opponent") or row.get("opponent_name"))
    if team and opp and "@" not in str(row.get("opponent") or "") and team != opp:
        return frozenset((team, opp))
    return frozenset()


def record_identity(r: dict[str, Any]) -> str:
    return str(r.get("record_id") or r.get("game_id") or r.get("event_id") or r.get("game") or "")


def emit_report(report: dict[str, Any]) -> None:
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    for path in (REPORT, WAREHOUSE_REPORT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def unique_games(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    for r in rows:
        identity = str(r.get("game_id") or r.get("event_id") or f"{str(r.get('game_date') or '')[:10]}|{r.get('game')}")
        chosen[identity] = r
    return list(chosen.values())


def consensus_candidate(rows: list[dict[str, Any]], stat: str) -> tuple[dict[str, Any] | None, Any, list[str]]:
    """Resolve provider duplicates only when all candidate stat values agree."""
    candidates = unique_games(rows)
    values = [(r, stat_value(r, stat)) for r in candidates]
    available = [(r, v) for r, v in values if v is not None]
    ids = [record_identity(r) for r in candidates]
    if len(available) != len(candidates) or not available:
        return None, None, ids
    first = available[0][1]
    if all(v == first for _, v in available[1:]):
        return available[0][0], first, ids
    return None, None, ids


def main() -> None:
    original = read_jsonl(ARCHIVE)
    history = copy.deepcopy(original)
    payload = load(LOGS, {"records": []})
    records = [r for r in payload.get("records", []) if isinstance(r, dict)]
    baseline_final = sum(str(r.get("outcome") or "").upper() in FINAL for r in original)

    by_player_date: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        player = norm(r.get("player") or r.get("player_name"))
        day = str(r.get("game_date") or r.get("date") or r.get("event_date") or "")[:10]
        if player:
            by_player[player].append(r)
        if player and day:
            by_player_date[(player, day)].append(r)

    now_dt = datetime.now(timezone.utc); now = now_dt.isoformat()
    stats = {
        "rows":len(history),"baseline_final":baseline_final,"verified_final_preserved":0,"strictly_graded":0,
        "same_date_exact":0,"frozen_game_time_exact":0,"unique_matchup_date_shift":0,"game_not_completed_yet":0,
        "no_player_game":0,"archive_matchup_missing":0,"matchup_mismatch":0,"repeated_matchup_date_ambiguous":0,
        "multiple_exact_matches":0,"consensus_duplicate_matches":0,"consensus_duplicate_rows_graded":0,
        "unique_player_date_fallback":0,"stat_unavailable":0,
    }
    mismatch_samples = []

    for row in history:
        if str(row.get("outcome") or "").upper() in FINAL:
            stats["verified_final_preserved"] += 1; continue

        player = norm(row.get("player")); snapshot = str(row.get("date") or "")[:10]
        scheduled = frozen_game_date(row); wanted = team_pair(row); stat = str(row.get("stat") or "")
        same = by_player_date.get((player, snapshot), [])
        sched = by_player_date.get((player, scheduled), []) if scheduled else []
        all_player = by_player.get(player, [])
        exact: list[dict[str, Any]] = []; mode = ""; consensus_actual = None; consensus_ids: list[str] = []

        start = parse_time(row.get("game_time"))
        if start is not None and start > now_dt:
            row["grading_reason"] = "frozen sportsbook game has not started yet"; row["scheduled_game_date"] = scheduled or None
            stats["game_not_completed_yet"] += 1; continue

        def choose(candidates: list[dict[str, Any]], normal_mode: str, consensus_mode: str) -> bool:
            nonlocal exact, mode, consensus_actual, consensus_ids
            games = unique_games(candidates)
            if len(games) == 1:
                exact = games; mode = normal_mode; stats[normal_mode] += 1; return True
            if len(games) > 1:
                picked, actual, ids = consensus_candidate(games, stat)
                if picked is not None:
                    exact = [picked]; mode = consensus_mode; consensus_actual = actual; consensus_ids = ids
                    stats["consensus_duplicate_matches"] += 1; return True
                row["grading_reason"] = "multiple completed player-games match archived wager and requested stat does not have unanimous candidate consensus"
                row["candidate_record_ids"] = ids; stats["multiple_exact_matches"] += 1; return False
            return False

        if wanted:
            same_exact = [r for r in same if team_pair(r) == wanted]
            if same_exact:
                if not choose(same_exact, "same_date_exact", "same_date_stat_consensus"):
                    continue
            else:
                scheduled_exact = [r for r in sched if team_pair(r) == wanted]
                if scheduled and scheduled != snapshot and scheduled_exact:
                    if not choose(scheduled_exact, "frozen_game_time_exact", "frozen_game_time_stat_consensus"):
                        continue
                else:
                    season_exact = unique_games([r for r in all_player if team_pair(r) == wanted])
                    if len(season_exact) == 1:
                        exact = season_exact; mode = "unique_matchup_date_shift"; stats["unique_matchup_date_shift"] += 1
                    elif len(season_exact) > 1:
                        row["grading_reason"] = "repeated matchup across season; exact date anchors do not resolve one completed game"
                        row["scheduled_game_date"] = scheduled or None
                        row["candidate_completed_games"] = [f"{str(r.get('game_date') or '')[:10]} {r.get('game')}" for r in season_exact]
                        row["candidate_record_ids"] = [record_identity(r) for r in season_exact]
                        stats["repeated_matchup_date_ambiguous"] += 1; continue
                    else:
                        if not same and not sched:
                            stats["no_player_game"] += 1; row["grading_reason"] = "no completed player-game found for archived matchup"
                        else:
                            stats["matchup_mismatch"] += 1; row["grading_reason"] = "candidate-date player-game exists but archived matchup does not match"
                        if len(mismatch_samples) < 25:
                            mismatch_samples.append({"date":snapshot,"scheduled_game_date":scheduled,"player":row.get("player"),"archive_game":row.get("game")})
                        continue
        else:
            stats["archive_matchup_missing"] += 1
            candidates = unique_games(sched if sched else same)
            if len(candidates) == 1:
                exact = candidates; mode = "unique_player_date_fallback"; stats["unique_player_date_fallback"] += 1
            else:
                row["grading_reason"] = "archive matchup missing and candidate date is not uniquely resolvable"
                row["candidate_record_ids"] = [record_identity(r) for r in candidates]; continue

        if len(exact) != 1:
            row["grading_reason"] = "strict matching did not resolve exactly one completed player-game"; continue
        record = exact[0]
        actual = consensus_actual if consensus_actual is not None else stat_value(record, stat)
        if actual is None:
            row["grading_reason"] = "actual stat unavailable in matched completed player-game"; row["actual_record_id"] = record_identity(record)
            stats["stat_unavailable"] += 1; continue
        result = outcome(str(row.get("side") or ""), actual, row.get("alt_line"))
        if result == "PENDING":
            row["grading_reason"] = "could not derive final outcome"; continue

        row["actual"] = actual; row["outcome"] = result; row["profit_loss"] = one_unit_profit(result, row.get("best_odds"))
        row["graded_at_utc"] = now; row["actual_source"] = STRICT_SOURCE; row["actual_record_id"] = record_identity(record)
        row["actual_game_id"] = record.get("game_id") or record.get("event_id"); row["actual_game_date"] = str(record.get("game_date") or "")[:10]
        row["grading_match_mode"] = mode; row["grading_reason"] = None
        if consensus_ids:
            row["consensus_record_ids"] = consensus_ids; row["consensus_record_count"] = len(consensus_ids)
            stats["consensus_duplicate_rows_graded"] += 1
        stats["strictly_graded"] += 1

    final = sum(str(r.get("outcome") or "").upper() in FINAL for r in history)
    pending = sum(str(r.get("outcome") or "PENDING").upper() == "PENDING" for r in history)
    stats.update({"proposed_final":final,"proposed_pending":pending})
    safe = final >= baseline_final
    report = {
        "generated_at_utc":now,"status":"PASS" if safe else "BLOCKED","safe_to_apply":safe,"minimum_safe_final":baseline_final,
        "stats":stats,"mismatch_samples":mismatch_samples,
        "identity_rule":"player + canonical matchup; snapshot date exact, then frozen game-time date exact, then unique completed season matchup; duplicate exact candidates require unanimous requested-stat consensus",
        "duplicate_policy":"multiple exact player/date/matchup records are gradeable only when every candidate exposes the requested stat and all values are identical",
        "repeated_matchup_policy":"never guess among repeated completed matchups",
        "future_game_policy":"future frozen game times remain pending",
        "preservation_policy":"every pre-existing final outcome is immutable; strict recovery only promotes pending rows",
    }
    emit_report(report)
    if not safe:
        raise SystemExit(f"Refusing destructive archive rewrite: proposed final {final} < existing final {baseline_final}")
    write_jsonl(ARCHIVE, history)
    print("Strict ALT regrade:", stats)


if __name__ == "__main__":
    main()
