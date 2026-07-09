from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MASTER = Path("data/dashboard/wnba_master.json")
CONSENSUS = Path("data/dashboard/wnba_sportsbook_consensus.json")
OUT = Path("data/dashboard/wnba_v4_player_props_audit.json")


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.load(path.open(encoding="utf-8"))
    except Exception:
        pass
    return default


def read_csv_rows(path: Path) -> tuple[int, list[str], list[dict[str, Any]]]:
    try:
        if not path.exists():
            return 0, [], []
        with path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
            return len(rows), list(rows[0].keys()) if rows else list(csv.DictReader(path.open(encoding="utf-8")).fieldnames or []), rows[:5]
    except Exception:
        return 0, [], []


def teams(g: str) -> set[str]:
    if " @ " not in str(g):
        return set()
    return {x.strip() for x in str(g).split(" @ ", 1)}


def same_game(a: str, b: str) -> bool:
    return bool(teams(a)) and teams(a) == teams(b)


def pct(n: int, d: int) -> float:
    return round(n / d * 100, 1) if d else 0.0


def main() -> None:
    master = load_json(MASTER, {})
    consensus = load_json(CONSENSUS, {})
    today_games = [g.get("game") for g in master.get("games", []) if g.get("bucket") == "today" and g.get("game")]
    props = master.get("props", []) if isinstance(master.get("props"), list) else []
    markets = consensus.get("markets", []) if isinstance(consensus.get("markets"), list) else []

    props_by_game = Counter(p.get("game", "") for p in props)
    markets_by_game = Counter(m.get("game", "") for m in markets)
    exact_counts = {g: sum(1 for p in props if same_game(p.get("game", ""), g)) for g in today_games}
    market_exact_counts = {g: sum(1 for m in markets if same_game(m.get("game", ""), g)) for g in today_games}

    prop_quality = {
        "total_props": len(props),
        "with_game": sum(1 for p in props if p.get("game")),
        "with_player": sum(1 for p in props if p.get("player")),
        "with_stat": sum(1 for p in props if p.get("stat")),
        "with_line": sum(1 for p in props if p.get("line") not in (None, "")),
        "with_projection": sum(1 for p in props if p.get("projection") not in (None, "")),
        "with_side": sum(1 for p in props if p.get("signal") in ("OVER", "UNDER", "PASS")),
        "with_over_price": sum(1 for p in props if p.get("best_over_price") not in (None, "")),
        "with_under_price": sum(1 for p in props if p.get("best_under_price") not in (None, "")),
        "with_player_team": sum(1 for p in props if p.get("player_team")),
        "with_opponent": sum(1 for p in props if p.get("opponent")),
        "with_logo": sum(1 for p in props if p.get("team_logo")),
    }
    prop_quality["projection_coverage_pct"] = pct(prop_quality["with_projection"], len(props))
    prop_quality["team_context_coverage_pct"] = pct(prop_quality["with_player_team"], len(props))
    prop_quality["odds_pair_coverage_pct"] = pct(min(prop_quality["with_over_price"], prop_quality["with_under_price"]), len(props))

    raw_files = []
    for p in sorted(Path("data/raw").glob("*prop*.csv")) + sorted(Path("data/raw").glob("line_shopping*.csv")):
        rows, cols, sample = read_csv_rows(p)
        raw_files.append({"path": str(p), "rows": rows, "columns": cols[:20], "sample": sample[:2]})

    exact_total = sum(exact_counts.values())
    issues = []
    if not today_games:
        issues.append("No active today games were found in master.")
    if markets and exact_total == 0:
        issues.append("Sportsbook consensus has markets, but none match today's active slate. This indicates stale or mismatched prop odds source files.")
    if props and exact_total == 0:
        issues.append("Master props exist, but none match today's games. Do not trust single-game filters until prop source refreshes.")
    if not markets:
        issues.append("No target-date sportsbook prop markets were accepted after stale-source rejection.")
    if prop_quality["projection_coverage_pct"] < 75 and props:
        issues.append("Projection coverage is weak; player stats mapping needs improvement.")

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_date": master.get("target_date"),
        "summary": {
            "today_games": len(today_games),
            "master_props": len(props),
            "consensus_markets": len(markets),
            "props_matching_today_games": exact_total,
            "consensus_markets_matching_today_games": sum(market_exact_counts.values()),
            "source_used": consensus.get("summary", {}).get("source_used"),
        },
        "today_games": today_games,
        "exact_prop_counts_by_today_game": exact_counts,
        "exact_market_counts_by_today_game": market_exact_counts,
        "top_master_prop_games": props_by_game.most_common(20),
        "top_consensus_market_games": markets_by_game.most_common(20),
        "prop_quality": prop_quality,
        "consensus_summary": consensus.get("summary", {}),
        "consensus_input_diagnostics": consensus.get("input_diagnostics", []),
        "raw_prop_files": raw_files[:30],
        "issues": issues,
        "recommended_next_fix": "Refresh/replace player-prop odds ingestion for the active target_date. V4 should not use stale line_shopping_best_today.csv rows from older game_date values.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("V4 player props audit:", out["summary"])
    if issues:
        print("Issues:")
        for issue in issues:
            print("-", issue)


if __name__ == "__main__":
    main()
