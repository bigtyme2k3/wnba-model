from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG = Path("config/v4_modules.json")
DASH = Path("data/dashboard")
OUT = DASH / "wnba_v4_status.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.load(path.open(encoding="utf-8"))
    except Exception:
        pass
    return default


def file_rows(path: str) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    try:
        if p.suffix == ".json":
            data = load_json(p, {})
            if isinstance(data, list):
                return len(data)
            if isinstance(data, dict):
                for key in ("markets", "props", "games", "players", "decisions", "best_bets", "rows"):
                    value = data.get(key)
                    if isinstance(value, list):
                        return len(value)
                summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
                for key in ("markets", "props", "players", "games", "rows"):
                    if isinstance(summary.get(key), int):
                        return summary[key]
                return 1
        if p.suffix == ".csv":
            return max(0, sum(1 for _ in p.open(encoding="utf-8")) - 1)
        return 1
    except Exception:
        return 0


def infer_runtime_status(module: dict[str, Any]) -> dict[str, Any]:
    owner = module.get("owner_file", "")
    exists = Path(owner).exists() if owner else False
    rows = 0
    dashboard_candidates = {
        "wnba_sportsbook_consensus.py": "data/dashboard/wnba_sportsbook_consensus.json",
        "wnba_player_intelligence.py": "data/raw/wnba_players_live.json",
        "wnba_matchup_intelligence.py": "data/dashboard/wnba_matchup_intelligence.json",
        "wnba_projection_ai.py": "data/dashboard/wnba_projection_ai.json",
        "player_points.py": "data/dashboard/wnba_master.json",
        "wnba_decision_engine_final.py": "data/dashboard/wnba_decision_engine_final.json",
        "wnba_portfolio_optimizer_v2.py": "data/dashboard/wnba_portfolio_optimizer_v2.json",
        "wnba_risk_allocation.py": "data/dashboard/wnba_risk_allocation.json",
        "wnba_closing_line_tracker.py": "data/dashboard/wnba_clv_summary.json",
        "wnba_results_grader.py": "data/dashboard/wnba_results_grading.json",
        "wnba_self_learning.py": "data/dashboard/wnba_self_learning.json",
        "wnba_reasoning_layer.py": "data/dashboard/wnba_reasoning_layer.json",
        "patch_dashboard_navigation_v2.py": "docs/index.html",
        "wnba_master_source_builder.py": "data/dashboard/wnba_master.json",
        "odds_source_manager.py": "data/raw/odds_source_status.json",
        "wnba_stats_fallback_from_boxscores.py": "data/raw/wnba_stats_fallback_status.json",
        "sports_skills_core_provider.py": "data/wnba/scores.json",
        "config/source_registry.json": "config/source_registry.json"
    }
    output = dashboard_candidates.get(owner, "")
    if output:
        rows = file_rows(output)
    planned = module.get("status") == "planned"
    if exists and rows > 0:
        runtime = "active"
    elif exists and not planned:
        runtime = "wired"
    elif exists:
        runtime = "scaffolded"
    else:
        runtime = "missing"
    return {"owner_exists": exists, "output": output, "rows": rows, "runtime_status": runtime}


def main() -> None:
    manifest = load_json(CONFIG, {"modules": []})
    modules = []
    for module in manifest.get("modules", []):
        runtime = infer_runtime_status(module)
        modules.append({**module, **runtime})
    totals = {"planned": 0, "partial": 0, "active": 0, "validated": 0, "wired": 0, "scaffolded": 0, "missing": 0}
    for module in modules:
        totals[module.get("status", "planned")] = totals.get(module.get("status", "planned"), 0) + 1
        totals[module.get("runtime_status", "missing")] = totals.get(module.get("runtime_status", "missing"), 0) + 1
    completion = round((totals.get("active", 0) + totals.get("validated", 0)) / max(len(modules), 1) * 100, 1)
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": manifest.get("version", "4.0"),
        "mission": manifest.get("mission", ""),
        "summary": {
            "modules": len(modules),
            "completion_pct": completion,
            "manifest_status_counts": {k: totals.get(k, 0) for k in ["planned", "partial", "active", "validated"]},
            "runtime_status_counts": {k: totals.get(k, 0) for k in ["active", "wired", "scaffolded", "missing"]}
        },
        "modules": modules,
        "next_build_order": [m for m in modules if m.get("status") in ("planned", "partial")][:8]
    }
    DASH.mkdir(parents=True, exist_ok=True)
    json.dump(out, OUT.open("w", encoding="utf-8"), indent=2)
    print(f"WNBA V4 status built: {out['summary']}")


if __name__ == "__main__":
    main()
