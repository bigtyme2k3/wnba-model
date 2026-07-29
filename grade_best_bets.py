from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

LEDGER = Path("data/history/best_bets_ledger.csv")
PERFORMANCE = Path("data/history/best_bets_performance.csv")
SUMMARY = Path("data/history/best_bets_performance_summary.json")
PROJECTION_HISTORY = Path("data/history/wnba_projection_history.jsonl")
MARKET_INTELLIGENCE = Path("data/dashboard/wnba_market_intelligence.json")

FIELDS = [
    "snapshot_id","snapshot_time_utc","slate_date","event_id","game","player_id",
    "player_name","team","opponent","sportsbook","market","side","line","odds",
    "projection","edge","evidence_score","confidence_tier","display_rank","actual",
    "outcome","closing_line","closing_odds","line_clv","odds_clv_probability",
    "stake_units","profit_units","roi","graded_at_utc","days_since_prediction",
]


def text(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split()).strip()


def norm(value: Any) -> str:
    return text(value).lower().replace("’", "'")


def num(value: Any) -> float | None:
    try:
        candidate = float(value)
        return candidate if math.isfinite(candidate) else None
    except (TypeError, ValueError):
        return None


def decimal_odds(value: Any) -> float | None:
    odds = num(value)
    if odds is None or odds == 0:
        return None
    return 1 + (100 / -odds) if odds < 0 else 1 + (odds / 100)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in FIELDS} for row in rows])


def actual_index() -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in read_jsonl(PROJECTION_HISTORY):
        actual = num(row.get("actual"))
        if actual is None:
            continue
        key = (text(row.get("date")), norm(row.get("player")), text(row.get("stat")).upper())
        index[key] = row
    return index


def market_index() -> dict[tuple[str, str, str, str, str, str], dict[str, Any]]:
    try:
        payload = json.loads(MARKET_INTELLIGENCE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        payload = {"records": []}
    index: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
    for row in payload.get("records", []):
        if not isinstance(row, dict):
            continue
        key = (
            text(row.get("target_date")), norm(row.get("player")), norm(row.get("game")),
            text(row.get("stat")).upper(), text(row.get("side")).upper(), norm(row.get("sportsbook")),
        )
        index[key] = row
    return index


def grade(ledger_row: dict[str, str], actuals: dict, markets: dict, now: datetime) -> dict[str, Any]:
    slate_date = text(ledger_row.get("slate_date"))
    player = text(ledger_row.get("player_name"))
    market = text(ledger_row.get("market")).upper()
    side = text(ledger_row.get("side")).upper()
    game = text(ledger_row.get("game"))
    sportsbook = text(ledger_row.get("sportsbook"))
    actual_row = actuals.get((slate_date, norm(player), market))
    market_row = markets.get((slate_date, norm(player), norm(game), market, side, norm(sportsbook)))
    actual = num(actual_row.get("actual")) if actual_row else None
    line = num(ledger_row.get("line"))
    odds = num(ledger_row.get("odds"))
    outcome = "PENDING"
    profit = None
    graded_at = ""
    if actual is not None and line is not None:
        if actual == line:
            outcome, profit = "PUSH", 0.0
        else:
            won = actual > line if side == "OVER" else actual < line
            outcome = "WIN" if won else "LOSS"
            dec = decimal_odds(odds)
            profit = round((dec - 1), 4) if won and dec is not None else -1.0
        graded_at = now.isoformat().replace("+00:00", "Z")
    try:
        days_since = (now.date() - date.fromisoformat(slate_date)).days
    except ValueError:
        days_since = ""
    closing_line = num(market_row.get("closing_line")) if market_row else None
    closing_odds = num(market_row.get("closing_odds")) if market_row else None
    line_clv = num(market_row.get("line_clv")) if market_row else None
    odds_clv = num(market_row.get("odds_clv_probability")) if market_row else None
    result = {key: ledger_row.get(key, "") for key in FIELDS}
    result.update({
        "actual": "" if actual is None else actual,
        "outcome": outcome,
        "closing_line": "" if closing_line is None else closing_line,
        "closing_odds": "" if closing_odds is None else closing_odds,
        "line_clv": "" if line_clv is None else line_clv,
        "odds_clv_probability": "" if odds_clv is None else odds_clv,
        "stake_units": 1.0,
        "profit_units": "" if profit is None else profit,
        "roi": "" if profit is None else profit,
        "graded_at_utc": graded_at,
        "days_since_prediction": days_since,
    })
    return result


def summarize(rows: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    graded = [row for row in rows if row.get("outcome") in {"WIN", "LOSS", "PUSH"}]
    decisions = [row for row in graded if row.get("outcome") in {"WIN", "LOSS"}]
    profit = sum(num(row.get("profit_units")) or 0 for row in graded)
    clvs = [num(row.get("line_clv")) for row in rows]
    clvs = [value for value in clvs if value is not None]
    return {
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "status": "PASS",
        "total_best_bets": len(rows),
        "graded": len(graded),
        "pending": sum(row.get("outcome") == "PENDING" for row in rows),
        "wins": sum(row.get("outcome") == "WIN" for row in rows),
        "losses": sum(row.get("outcome") == "LOSS" for row in rows),
        "pushes": sum(row.get("outcome") == "PUSH" for row in rows),
        "win_rate": round(sum(row.get("outcome") == "WIN" for row in decisions) / len(decisions), 4) if decisions else None,
        "profit_units": round(profit, 4),
        "roi": round(profit / len(graded), 4) if graded else None,
        "average_line_clv": round(sum(clvs) / len(clvs), 4) if clvs else None,
        "positive_clv_rate": round(sum(value > 0 for value in clvs) / len(clvs), 4) if clvs else None,
        "actual_source": str(PROJECTION_HISTORY),
        "clv_source": str(MARKET_INTELLIGENCE),
        "ledger_source": str(LEDGER),
    }


def validate(rows: list[dict[str, Any]]) -> None:
    if not LEDGER.exists():
        raise SystemExit("best bets ledger missing")
    if not PERFORMANCE.exists():
        raise SystemExit("best bets performance database missing")
    ids = [text(row.get("snapshot_id")) for row in rows]
    if any(not value for value in ids):
        raise SystemExit("performance database contains empty snapshot_id")
    if len(ids) != len(set(ids)):
        raise SystemExit("performance database contains duplicate snapshot_id")
    if any(row.get("outcome") not in {"PENDING", "WIN", "LOSS", "PUSH"} for row in rows):
        raise SystemExit("invalid outcome in performance database")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.validate_only:
        rows = read_csv(PERFORMANCE)
        validate(rows)
        print(json.dumps({"status": "PASS", "rows": len(rows)}))
        return
    ledger_rows = read_csv(LEDGER)
    actuals = actual_index()
    markets = market_index()
    performance = [grade(row, actuals, markets, now) for row in ledger_rows]
    write_csv(PERFORMANCE, performance)
    SUMMARY.write_text(json.dumps(summarize(performance, now), indent=2) + "\n", encoding="utf-8")
    validate(performance)
    print(json.dumps(summarize(performance, now)))


if __name__ == "__main__":
    main()
