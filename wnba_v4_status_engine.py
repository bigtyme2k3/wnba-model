from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG = Path("config/v4_modules.json")
DASH = Path("data/dashboard")
OUT = DASH / "wnba_v4_status.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def file_rows(path: str) -> int:
    p = Path(path)
    if not p.exists(): return 0
    try:
        if p.suffix == ".json":
            data = load_json(p, {})
            if isinstance(data, list): return len(data)
            if isinstance(data, dict):
                for key in ("markets", "props", "games", "players", "events", "matchups", "projections", "decisions", "best_bets", "rows", "top_decisions", "recommended_card", "allocation"):
                    if isinstance(data.get(key), list): return len(data[key])
                summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
                for key in ("markets", "props", "players", "games", "events", "rows", "decision_rows", "evaluated_rows", "card_size"):
                    if isinstance(summary.get(key), int): return summary[key]
                return 1 if data else 0
        if p.suffix == ".csv": return max(0, sum(1 for _ in p.open(encoding="utf-8")) - 1)
        return 1
    except Exception:
        return 0


def valid_zero_output(path: str) -> bool:
    if not path or not Path(path).exists(): return False
    data = load_json(Path(path), {}); summary = data.get("summary", {}) if isinstance(data, dict) else {}
    if path.endswith("wnba_portfolio_optimizer_v2.json"):
        return summary.get("qualified_candidates") == 0 and summary.get("card_size") == 0 and data.get("recommended_card") == []
    if path.endswith("wnba_risk_allocation.json"):
        return summary.get("card_size") == 0 and data.get("allocation") == []
    if path.endswith("wnba_play_by_play_layer.json"):
        return summary.get("games") == 0 and data.get("status") == "ok"
    return False


def infer_runtime_status(module: dict[str, Any]) -> dict[str, Any]:
    owner = module.get("owner_file", ""); exists = Path(owner).exists() if owner else False
    outputs = {
        "wnba_sportsbook_consensus.py": "data/dashboard/wnba_sportsbook_consensus.json",
        "wnba_player_intelligence.py": "data/raw/wnba_players_live.json",
        "wnba_play_by_play_layer.py": "data/dashboard/wnba_play_by_play_layer.json",
        "wnba_matchup_intelligence.py": "data/dashboard/wnba_matchup_intelligence.json",
        "wnba_projection_ai.py": "data/dashboard/wnba_projection_ai.json",
        "wnba_game_market_model.py": "data/dashboard/wnba_game_market_model.json",
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
        "config/source_registry.json": "config/source_registry.json",
    }
    output = outputs.get(owner, ""); count = file_rows(output) if output else 0; planned = module.get("status") == "planned"
    runtime = "active" if exists and (count > 0 or valid_zero_output(output)) else "wired" if exists and not planned else "scaffolded" if exists else "missing"
    return {"owner_exists": exists, "output": output, "rows": count, "runtime_status": runtime, "valid_zero_output": valid_zero_output(output)}


def output_qa_modules(code: str) -> set[str]:
    mapping = {
        "DATE_MISMATCH": {"M02", "M20"}, "BAD_PROBABILITY": {"M09", "M10", "M11", "M12", "M13"},
        "BAD_SCORE": {"M08", "M09", "M10", "M11", "M12", "M13", "M19"}, "IMPLIED_PROBABILITY_MISMATCH": {"M03", "M04", "M13"},
        "UNSUPPORTED_BOOK": {"M03", "M04"}, "UNSUPPORTED_MARKET": {"M10", "M13"}, "INELIGIBLE_BET": {"M13", "M14", "M15"},
        "BET_WITH_FAILURES": {"M13", "M14", "M15"}, "ELIGIBLE_NOT_BET": {"M13", "M14"}, "BET_EV_OUT_OF_RANGE": {"M13"},
        "BET_PROBABILITY_TOO_LOW": {"M09", "M13"}, "BET_HISTORY_TOO_LOW": {"M05", "M10", "M13"},
        "BET_BOOK_COUNT_TOO_LOW": {"M03", "M04", "M13"}, "DECISION_COUNT_MISMATCH": {"M13", "M20"},
        "BET_COUNT_MISMATCH": {"M13", "M14", "M20"}, "DUPLICATE_DECISION": {"M13"}, "PORTFOLIO_CAP_EXCEEDED": {"M14", "M15"},
        "PORTFOLIO_PLAYER_DUPLICATION": {"M14", "M15"}, "PORTFOLIO_GAME_CONCENTRATION": {"M14", "M15"},
        "STAKE_EXCEEDS_BANKROLL": {"M15"}, "PORTFOLIO_SILENT_FAILURE": {"M14"}, "PORTFOLIO_WITHOUT_QUALIFIED_BETS": {"M13", "M14"},
    }
    return mapping.get(code, set())


def aggregate_findings(items: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    errors: Counter[str] = Counter(); warnings: Counter[str] = Counter()
    for item in items:
        text = f"{item.get('code')}: {item.get('message')}"; (errors if item.get("level") == "error" else warnings)[text] += 1
    render = lambda c: [f"{text} ×{count}" if count > 1 else text for text, count in c.items()]
    return render(errors), render(warnings)


def acceptance_for(module_id: str, downstream: dict[str, Any], foundation: dict[str, Any]) -> dict[str, Any] | None:
    if module_id in {"M07", "M08", "M09"}:
        value = foundation.get("modules", {}).get(module_id)
    else:
        key = "M11/M12" if module_id in {"M11", "M12"} else module_id
        value = downstream.get("modules", {}).get(key)
    return value if isinstance(value, dict) else None


def main() -> None:
    manifest = load_json(CONFIG, {"modules": []}); repo_qa = load_json(DASH / "wnba_v4_qa.json", {})
    output_qa = load_json(DASH / "wnba_v4_output_qa.json", {}); downstream = load_json(DASH / "wnba_v4_acceptance.json", {})
    foundation = load_json(DASH / "wnba_v4_foundation_acceptance.json", {})
    repo_by_id = {m.get("id"): m for m in repo_qa.get("modules", []) if isinstance(m, dict)}
    output_findings = output_qa.get("findings", []) if isinstance(output_qa, dict) else []; modules = []
    required = {"M07", "M08", "M09", "M11", "M12", "M13", "M14", "M15"}

    for module in manifest.get("modules", []):
        runtime = infer_runtime_status(module); repo_item = repo_by_id.get(module.get("id"), {})
        mapped = [x for x in output_findings if module.get("id") in output_qa_modules(str(x.get("code")))]
        blockers, warnings = aggregate_findings(mapped); acceptance = acceptance_for(module.get("id"), downstream, foundation)
        if not runtime["owner_exists"]: blockers.append("Owner file missing")
        if repo_item.get("syntax_ok") is False: blockers.append("Owner file has a Python syntax error")
        if module.get("id") in required and not acceptance: blockers.append("Production acceptance report missing")
        elif module.get("id") in required and not acceptance.get("passed"): blockers.append("Production acceptance tests failed")
        score = int(repo_item.get("qa_score", 100)); score = max(0, score - min(60, 25 * len(blockers)) - min(25, 5 * len(warnings)))
        grade = "red" if blockers or score < 60 else "yellow" if warnings or score < 90 else "green"
        ready = module.get("status") in {"active", "validated"} and runtime["runtime_status"] == "active" and grade == "green"
        effective = "blocked" if grade == "red" else "validated" if ready else "attention" if grade == "yellow" else runtime["runtime_status"]
        modules.append({**module, **runtime, "qa_score": score, "qa_grade": grade, "effective_status": effective,
                        "production_ready": ready, "acceptance": acceptance, "blockers": blockers, "warnings": warnings})

    manifest_counts = {k: sum(m.get("status") == k for m in modules) for k in ("planned", "partial", "active", "validated")}
    runtime_counts = {k: sum(m.get("runtime_status") == k for m in modules) for k in ("active", "wired", "scaffolded", "missing")}
    qa_counts = {k: sum(m.get("qa_grade") == k for m in modules) for k in ("green", "yellow", "red")}; ready_count = sum(m["production_ready"] for m in modules)
    overall = "red" if qa_counts["red"] else "yellow" if qa_counts["yellow"] else "green"
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "version": manifest.get("version", "4.0"), "mission": manifest.get("mission", ""),
        "qa": {"overall_status": overall, "repository_qa_status": repo_qa.get("status", "unknown"), "output_qa_status": output_qa.get("status", "unknown"),
               "acceptance_status": downstream.get("status", "missing"), "foundation_acceptance_status": foundation.get("status", "missing"),
               "repository_qa_generated_at": repo_qa.get("generated_at_utc"), "output_qa_generated_at": output_qa.get("generated_at_utc"),
               "acceptance_generated_at": downstream.get("generated_at_utc"), "foundation_acceptance_generated_at": foundation.get("generated_at_utc"),
               "output_summary": output_qa.get("summary", {}), "acceptance_summary": downstream.get("summary", {}),
               "foundation_acceptance_summary": foundation.get("summary", {})},
        "summary": {"modules": len(modules), "completion_pct": round(ready_count / max(len(modules), 1) * 100, 1), "production_ready": ready_count,
                    "manifest_status_counts": manifest_counts, "runtime_status_counts": runtime_counts, "qa_status_counts": qa_counts,
                    "release_blockers": sum(len(m["blockers"]) for m in modules), "warnings": sum(len(m["warnings"]) for m in modules)},
        "modules": modules, "release_blockers": [{"id": m["id"], "module": m["name"], "items": m["blockers"]} for m in modules if m["blockers"]],
        "next_build_order": [m for m in modules if not m["production_ready"]][:8],
    }
    DASH.mkdir(parents=True, exist_ok=True); json.dump(out, OUT.open("w", encoding="utf-8"), indent=2, allow_nan=False)
    print(f"WNBA V4 QA-integrated status built: {out['summary']}")


if __name__ == "__main__": main()
