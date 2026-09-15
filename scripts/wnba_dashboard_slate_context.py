#!/usr/bin/env python3
"""Resolve whether Pages may render a prepared upcoming WNBA slate.

The schedule resolver intentionally treats a day without games as a break.
Pages may still render the *next* slate when the complete source stack has
already been prepared for that exact date.  This module is the fail-closed
bridge between those two facts: a date match alone is never enough.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from active_slate_date import SlateContext, resolve_slate_context

ALLOWED_BOOKS = {"draftkings", "fanduel", "fanatics"}

SOURCE_PATHS = {
    "master": "data/dashboard/wnba_master.json",
    "standard_props": "data/dashboard/wnba_player_props.json",
    "manifest": "data/dashboard/wnba_daily_canonical_manifest.json",
    "base_predictions": "data/dashboard/wnba_sprint2_predictions.json",
    "injury": "data/dashboard/wnba_injury_intelligence.json",
    "phase2": "data/dashboard/wnba_sprint2_phase2.json",
    "m02": "data/dashboard/wnba_s19_m02_predictions.json",
    "m02_audit": "data/dashboard/wnba_s19_m02_prediction_audit.json",
    "projection_integrity": "data/dashboard/wnba_projection_integrity_audit.json",
    "tab_freshness": "data/dashboard/wnba_tab_freshness.json",
}

ALT_PATHS = {
    "alt_warehouse": "data/dashboard/wnba_alt_market_warehouse.json",
    "alt_streaks": "data/dashboard/wnba_alt_streaks.json",
}


@dataclass(frozen=True)
class DashboardSlateContext:
    schema_version: str
    observation_date: str
    schedule_mode: str
    target_date: str
    deployment_mode: str
    next_slate_date: str | None
    maintenance_break: bool
    prepared_upcoming: bool
    source_stack_ready: bool
    source_errors: list[str]
    game_count: int
    standard_prop_rows: int
    m02_prediction_rows: int
    injury_source_verified: bool
    recommendations_actionable: bool
    alt_current_source: bool
    paid_api_called: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_json(root: Path, relative_path: str) -> tuple[dict[str, Any], str | None]:
    path = root / relative_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"{relative_path}:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return {}, f"{relative_path}:not_an_object"
    return payload, None


def target_of(payload: dict[str, Any]) -> str:
    return str(payload.get("target_date") or payload.get("date") or "")[:10]


def row_count(payload: dict[str, Any]) -> int:
    rows = payload.get("rows")
    if isinstance(rows, list):
        return len(rows)
    try:
        return int(payload.get("row_count") or 0)
    except (TypeError, ValueError):
        return 0


def normalized_books(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(value or "").strip().lower().replace(" ", "") for value in values if value}


def standard_prop_books(payload: dict[str, Any]) -> set[str]:
    books: set[str] = set()
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        for quote in row.get("books") or []:
            if isinstance(quote, dict) and quote.get("book"):
                books.add(str(quote["book"]).strip().lower().replace(" ", ""))
    return books


def inspect_alt_current_source(target: str, root: Path = ROOT) -> bool:
    payloads: list[dict[str, Any]] = []
    for relative_path in ALT_PATHS.values():
        payload, error = load_json(root, relative_path)
        if error:
            return False
        payloads.append(payload)
    return bool(payloads) and all(target_of(payload) == target for payload in payloads)


def inspect_source_stack(target: str, root: Path = ROOT) -> dict[str, Any]:
    date.fromisoformat(target)
    loaded: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name, relative_path in SOURCE_PATHS.items():
        payload, error = load_json(root, relative_path)
        loaded[name] = payload
        if error:
            errors.append(error)
            continue
        actual = target_of(payload)
        if actual != target:
            errors.append(f"{name}:target_mismatch:{actual or 'missing'}")

    manifest = loaded.get("manifest") or {}
    props = loaded.get("standard_props") or {}
    master = loaded.get("master") or {}
    base = loaded.get("base_predictions") or {}
    injury = loaded.get("injury") or {}
    phase2 = loaded.get("phase2") or {}
    m02 = loaded.get("m02") or {}
    m02_audit = loaded.get("m02_audit") or {}
    integrity = loaded.get("projection_integrity") or {}

    games = list(master.get("today_games") or [])
    game_count = int(manifest.get("game_count") or len(games))
    prop_rows = row_count(props)
    m02_rows = int(
        m02_audit.get("player_prop_predictions")
        or (m02.get("summary") or {}).get("player_prop_predictions")
        or 0
    )

    if manifest.get("status") != "PASS":
        errors.append("manifest:status_not_pass")
    if game_count <= 0 or not games:
        errors.append("canonical:zero_games")
    if prop_rows <= 0:
        errors.append("standard_props:zero_rows")
    if base.get("status") != "PASS":
        errors.append("base_predictions:status_not_pass")
    if phase2.get("status") != "PASS" or not (phase2.get("games") or []):
        errors.append("phase2:not_ready")
    if injury.get("source_only") is not True:
        errors.append("injury:not_source_only")
    if m02.get("status") != "READY" or m02_rows <= 0:
        errors.append("m02:not_ready")
    if m02_audit.get("status") != "READY":
        errors.append("m02_audit:not_ready")
    if m02_audit.get("all_rendered_props_exact_current_slate") is not True:
        errors.append("m02_audit:off_slate_rows_possible")
    if int(m02_audit.get("actionable_out_props") or 0) != 0:
        errors.append("m02_audit:actionable_unavailable_player")
    if m02_audit.get("phase2_best_bets_fallback_enabled") is not False:
        errors.append("m02_audit:best_bets_fallback_enabled")
    if m02_audit.get("phase2_portfolio_fallback_enabled") is not False:
        errors.append("m02_audit:portfolio_fallback_enabled")
    if integrity.get("status") != "PASS" or int(integrity.get("violation_count") or 0) != 0:
        errors.append("projection_integrity:not_clean")

    allowed_manifest = normalized_books(manifest.get("sportsbooks_allowed"))
    allowed_props = normalized_books(props.get("sportsbooks_allowed"))
    observed_manifest = normalized_books(manifest.get("sportsbooks_observed"))
    observed_props = normalized_books(props.get("sportsbooks_observed"))
    quoted_books = standard_prop_books(props)
    if allowed_manifest != ALLOWED_BOOKS or allowed_props != ALLOWED_BOOKS:
        errors.append("sportsbooks:allowed_contract_mismatch")
    if not observed_props or not observed_manifest:
        errors.append("sportsbooks:no_observed_book")
    if not (observed_manifest | observed_props | quoted_books).issubset(ALLOWED_BOOKS):
        errors.append("sportsbooks:unsupported_book_observed")
    if props.get("unsupported_bookmakers_rejected") not in ([], None):
        errors.append("sportsbooks:unsupported_rows_present")

    injury_verified = injury.get("injury_source_verified") is True
    m02_summary = m02.get("summary") or {}
    if not injury_verified:
        if any(
            int(m02_summary.get(key) or 0) != 0
            for key in ("bet_player_props", "v5_best_bets", "v5_portfolio_rows")
        ):
            errors.append("injury_unverified:actionable_rows_present")
        if m02.get("best_bets") or m02.get("portfolio"):
            errors.append("injury_unverified:decision_payload_not_empty")

    alt_current = inspect_alt_current_source(target, root=root)

    return {
        "ready": not errors,
        "errors": sorted(set(errors)),
        "game_count": game_count,
        "standard_prop_rows": prop_rows,
        "m02_prediction_rows": m02_rows,
        "injury_source_verified": injury_verified,
        "recommendations_actionable": injury_verified and bool(m02.get("best_bets")),
        "alt_current_source": alt_current,
    }


def resolve_dashboard_slate_context(
    schedule: SlateContext | None = None,
    root: Path = ROOT,
) -> DashboardSlateContext:
    schedule = schedule or resolve_slate_context()
    target = schedule.target_date
    deployment_mode = schedule.mode
    maintenance = schedule.mode in {"break", "offseason"}
    prepared = False
    evidence = {
        "ready": schedule.mode in {"active", "manual"},
        "errors": [],
        "game_count": 0,
        "standard_prop_rows": 0,
        "m02_prediction_rows": 0,
        "injury_source_verified": False,
        "recommendations_actionable": False,
        "alt_current_source": False,
    }
    reason = schedule.reason

    if schedule.mode in {"active", "manual"}:
        evidence["alt_current_source"] = inspect_alt_current_source(target, root=root)

    if schedule.mode == "break" and schedule.next_slate_date:
        evidence = inspect_source_stack(schedule.next_slate_date, root=root)
        if evidence["ready"]:
            target = schedule.next_slate_date
            deployment_mode = "upcoming"
            maintenance = False
            prepared = True
            reason = "next_slate_source_stack_ready"
        else:
            reason = "next_slate_source_stack_not_ready"

    return DashboardSlateContext(
        schema_version="wnba-dashboard-slate-context-v1",
        observation_date=schedule.current_date,
        schedule_mode=schedule.mode,
        target_date=target,
        deployment_mode=deployment_mode,
        next_slate_date=schedule.next_slate_date,
        maintenance_break=maintenance,
        prepared_upcoming=prepared,
        source_stack_ready=bool(evidence["ready"]),
        source_errors=list(evidence["errors"]),
        game_count=int(evidence["game_count"]),
        standard_prop_rows=int(evidence["standard_prop_rows"]),
        m02_prediction_rows=int(evidence["m02_prediction_rows"]),
        injury_source_verified=bool(evidence["injury_source_verified"]),
        recommendations_actionable=bool(evidence["recommendations_actionable"]),
        alt_current_source=bool(evidence["alt_current_source"]),
        paid_api_called=False,
        reason=reason,
    )


def print_field(context: DashboardSlateContext, field: str) -> None:
    payload = context.to_dict()
    if field not in payload:
        raise SystemExit(f"Unknown dashboard slate-context field: {field}")
    value = payload[field]
    if value is None:
        print("")
    elif isinstance(value, bool):
        print(str(value).lower())
    elif isinstance(value, (dict, list)):
        print(json.dumps(value, separators=(",", ":")))
    else:
        print(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", action="store_true")
    parser.add_argument("--field", default="")
    args = parser.parse_args()
    context = resolve_dashboard_slate_context()
    if args.context:
        print(json.dumps(context.to_dict(), sort_keys=True))
    elif args.field:
        print_field(context, args.field)
    else:
        print(context.target_date)


if __name__ == "__main__":
    main()
