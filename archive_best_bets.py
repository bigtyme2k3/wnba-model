from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MASTER = Path("data/master/wnba_master.json")
DASHBOARD = Path("docs/index.html")
LEDGER = Path("data/history/best_bets_ledger.csv")
SUMMARY = Path("data/history/best_bets_summary.json")

FIELDS = [
    "snapshot_id","snapshot_time_utc","dashboard_version","model_version","slate_date",
    "event_id","game","player_id","player_name","team","opponent","sportsbook","market",
    "side","line","odds","projection","edge","evidence_score","confidence_tier",
    "display_rank","correlation_group","supporting_books","archived_before_lock",
    "workflow_run_id",
]
BLOCKED = {"LIVE","FINAL","COMPLETED","IN_PROGRESS","POSTPONED","CLOSED"}

def text(v: Any) -> str:
    return " ".join(str(v if v is not None else "").split()).strip()

def norm(v: Any) -> str:
    return text(v).lower()

def num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def pct(v: Any) -> float | None:
    x = num(v)
    if x is None:
        return None
    return x / 100.0 if x > 1 else x

def first(row: dict, *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default

def side(row: dict) -> str:
    return text(first(row, "signal", "side", "selection")).upper()

def market(row: dict) -> str:
    return text(first(row, "stat", "market")).upper()

def player(row: dict) -> str:
    return text(first(row, "player", "player_name", "participant", default="Game market"))

def game(row: dict) -> str:
    return text(first(row, "game", "matchup"))

def line(row: dict) -> float | None:
    return num(first(row, "line", "consensus_line", "current_line", default=None))

def projection(row: dict) -> float | None:
    return num(first(row, "projection", "pred", "projected_value", default=None))

def edge(row: dict) -> float:
    a, b = line(row), projection(row)
    return abs(b - a) if a is not None and b is not None else 0.0

def probability(row: dict) -> float | None:
    return pct(first(row, "model_probability", "probability", "win_probability", default=None))

def recent(row: dict) -> float | None:
    return pct(first(row, "l10_hit_rate", "hit_rate_l10", "l5_hit_rate", "recent_hit_rate", "hit_rate_l5", default=None))

def book_count(row: dict) -> int:
    return int(num(first(row, "book_count", "books_count", default=1)) or 1)

def status(row: dict) -> str:
    return text(first(row, "game_status", "availability_status", "injury_status", "status")).upper()

def sportsbook(row: dict) -> str:
    s = side(row)
    return text(first(row, "book", "sportsbook", "best_book", "best_under_book" if s == "UNDER" else "best_over_book", default="Best available"))

def odds(row: dict) -> float | None:
    s = side(row)
    return num(first(row, "odds", "best_price", "best_under_price" if s == "UNDER" else "best_over_price", "current_price", default=None))

def family(row: dict) -> str:
    stat = market(row)
    if stat in {"PTS","POINTS","PR","PA","RA","PRA"}: return "OFFENSE"
    if stat in {"REB","REBOUNDS"}: return "REBOUNDING"
    if stat in {"AST","ASSISTS"}: return "PLAYMAKING"
    if stat in {"3PM","THREES","3PT"}: return "THREES"
    return stat or "OTHER"

def score(row: dict) -> int:
    st, e, pr, rh, bk, od = status(row), edge(row), probability(row), recent(row), book_count(row), odds(row)
    if st in {"OUT","DOUBTFUL"}: return 0
    value = 42 + max(0, min(20, e * 2))
    value += max(-5, min(16, (pr - .50) * 40)) if pr is not None else -7
    value += max(-4, min(12, (rh - .50) * 30)) if rh is not None else -6
    value += 5 if bk >= 3 else 3 if bk == 2 else -2
    value += 4 if od is not None and -135 <= od <= 140 else -3 if od is not None and (od < -175 or od > 220) else -2
    if st in {"QUESTIONABLE","UNKNOWN"}: value -= 10
    if e < 2: value -= 5
    return round(max(0, min(92, value)))

def evidence_count(row: dict) -> int:
    return sum([edge(row) >= 3, probability(row) is not None, recent(row) is not None, book_count(row) >= 2, odds(row) is not None, status(row) not in {"QUESTIONABLE","UNKNOWN","OUT","DOUBTFUL"}])

def tier(row: dict) -> str:
    s, c, pr, rh = score(row), evidence_count(row), probability(row), recent(row)
    if s >= 84 and c >= 5 and pr is not None and rh is not None: return "TOP PLAY"
    if s >= 76 and c >= 4 and (pr is not None or rh is not None): return "STRONG"
    if s >= 64: return "WATCH"
    return "LEAN"

def parse_time(value: Any) -> datetime | None:
    raw = text(value)
    if not raw: return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def game_start_map(master: dict) -> dict[str, Any]:
    result = {}
    games = list(master.get("games") or [])
    nested = master.get("master") if isinstance(master.get("master"), dict) else {}
    games.extend(nested.get("games") or [])
    for row in games:
        name = norm(first(row, "game", "matchup", default=f"{first(row,'away_team','away')} @ {first(row,'home_team','home')}"))
        raw = first(row, "commence_time", "start_time", "game_time", "game_date", "date")
        if name and raw: result[name] = raw
    return result

def start_time(row: dict, starts: dict[str, Any]) -> datetime | None:
    return parse_time(first(row, "commence_time", "start_time", "game_time", "game_date", "date", default=starts.get(norm(game(row)))))

def closed(row: dict, starts: dict[str, Any], now: datetime) -> bool:
    st = status(row)
    if any(token in st for token in BLOCKED): return True
    tip = start_time(row, starts)
    return bool(tip and tip <= now)

def exact_key(row: dict) -> tuple:
    value = line(row)
    return (norm(player(row)), norm(game(row)), market(row), side(row), "" if value is None else f"{value:.2f}")

def overlap_key(row: dict) -> tuple:
    return (norm(player(row)), norm(game(row)), family(row), side(row))

def final_card(master: dict, now: datetime) -> list[dict]:
    nested = master.get("master") if isinstance(master.get("master"), dict) else master
    source = list(nested.get("best_bets") or nested.get("props") or master.get("best_bets") or master.get("props") or [])
    starts = game_start_map(master)
    opened = [row for row in source if not closed(row, starts, now)]
    remaining_games = {norm(game(row)) for row in opened if game(row)}
    threshold = 52 if len(remaining_games) <= 2 else 58
    exact: dict[tuple, dict] = {}
    for row in opened:
        candidate = dict(row); candidate["_cardScore"] = score(candidate)
        key = exact_key(candidate)
        if key not in exact or candidate["_cardScore"] > exact[key]["_cardScore"]: exact[key] = candidate
    overlap: dict[tuple, dict] = {}
    for row in sorted(exact.values(), key=lambda r: r["_cardScore"], reverse=True): overlap.setdefault(overlap_key(row), row)
    selected, per_player, per_game, keys = [], {}, {}, set()
    for row in sorted(overlap.values(), key=lambda r: r["_cardScore"], reverse=True):
        if row["_cardScore"] < threshold or edge(row) <= 0: continue
        key = exact_key(row)
        if key in keys: continue
        p, g = norm(player(row)), norm(game(row))
        if per_player.get(p, 0) >= 2 or per_game.get(g, 0) >= 3: continue
        selected.append(row); keys.add(key); per_player[p] = per_player.get(p, 0) + 1; per_game[g] = per_game.get(g, 0) + 1
        if len(selected) >= 10: break
    return selected

def ids(row: dict, slate_date: str) -> tuple[str, str]:
    event = text(first(row, "event_id", "game_id")) or hashlib.sha256(f"{slate_date}|{game(row)}".encode()).hexdigest()[:24]
    pid = text(first(row, "player_id", "athlete_id")) or hashlib.sha256(player(row).encode()).hexdigest()[:24]
    return event, pid

def row_payload(row: dict, rank: int, now: datetime, master: dict) -> dict:
    slate_date = text(first(master, "target_date", "slate_date", default=now.date().isoformat()))
    event, pid = ids(row, slate_date); book = sportsbook(row); ln, od = line(row), odds(row)
    identity = [slate_date, event, pid, market(row), side(row), ln, book, od]
    snapshot_id = hashlib.sha256(json.dumps(identity, separators=(",", ":"), default=str).encode()).hexdigest()
    tip = start_time(row, game_start_map(master))
    return {"snapshot_id":snapshot_id,"snapshot_time_utc":now.isoformat().replace("+00:00","Z"),"dashboard_version":text(first(master,"dashboard_version","schema_version",default="v4")),"model_version":text(first(master,"model_version",default=os.getenv("MODEL_VERSION","production"))),"slate_date":slate_date,"event_id":event,"game":game(row),"player_id":pid,"player_name":player(row),"team":text(first(row,"team","player_team")),"opponent":text(first(row,"opponent","opp")),"sportsbook":book,"market":market(row),"side":side(row),"line":"" if ln is None else ln,"odds":"" if od is None else od,"projection":"" if projection(row) is None else projection(row),"edge":edge(row),"evidence_score":score(row),"confidence_tier":tier(row),"display_rank":rank,"correlation_group":"|".join(overlap_key(row)),"supporting_books":book_count(row),"archived_before_lock":bool(tip is None or now < tip),"workflow_run_id":os.getenv("GITHUB_RUN_ID","")}

def read_ledger() -> list[dict]:
    if not LEDGER.exists(): return []
    with LEDGER.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != FIELDS: raise SystemExit(f"ledger required columns missing or out of order: {reader.fieldnames}")
        rows = list(reader)
    if any(not row.get("snapshot_id") for row in rows): raise SystemExit("corrupted ledger: empty snapshot_id")
    return rows

def qa(rows: list[dict], latest: list[dict]) -> None:
    if not LEDGER.exists(): raise SystemExit("ledger missing")
    if len({r["snapshot_id"] for r in rows}) != len(rows): raise SystemExit("duplicate snapshot IDs")
    ranks = [int(r["display_rank"]) for r in latest]
    if len(ranks) != len(set(ranks)): raise SystemExit("duplicate display ranks")
    if any(str(r["archived_before_lock"]).lower() not in {"true","1"} for r in latest): raise SystemExit("archived after lock")
    if not DASHBOARD.exists(): raise SystemExit("dashboard missing")
    html = DASHBOARD.read_text(encoding="utf-8")
    for marker in ("sprint25-phase8-live-slate-script", "Best Bets"):
        if marker not in html: raise SystemExit(f"archived recommendation differs from dashboard: missing {marker}")

def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--validate-only", action="store_true"); args = parser.parse_args()
    master = json.loads(MASTER.read_text(encoding="utf-8")); now = datetime.now(timezone.utc)
    latest = [row_payload(row, rank, now, master) for rank, row in enumerate(final_card(master, now), 1)]
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    existing = read_ledger() if LEDGER.exists() else []; existing_ids = {row["snapshot_id"] for row in existing}
    additions = [row for row in latest if row["snapshot_id"] not in existing_ids]
    if not args.validate_only:
        mode = "a" if LEDGER.exists() and LEDGER.stat().st_size else "w"
        with LEDGER.open(mode, newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            if mode == "w": writer.writeheader()
            writer.writerows(additions)
        summary = {"generated_at_utc":now.isoformat().replace("+00:00","Z"),"slate_date":text(first(master,"target_date","slate_date",default=now.date().isoformat())),"dashboard_version":text(first(master,"dashboard_version","schema_version",default="v4")),"model_version":text(first(master,"model_version",default=os.getenv("MODEL_VERSION","production"))),"card_count":len(latest),"rows_archived":len(additions),"rows_skipped_duplicate":len(latest)-len(additions),"latest_snapshot_ids":[row["snapshot_id"] for row in latest],"latest_display_ranks":[row["display_rank"] for row in latest],"workflow_run_id":os.getenv("GITHUB_RUN_ID",""),"status":"PASS"}
        SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    rows = read_ledger(); qa(rows, latest)
    print(json.dumps({"status":"PASS","card":len(latest),"archived":0 if args.validate_only else len(additions)}))

if __name__ == "__main__": main()
