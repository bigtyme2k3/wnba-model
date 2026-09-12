"""Resolve the Eastern WNBA observation date and schedule state.

GitHub Actions runs on UTC, so the legacy command continues to print the
America/New_York calendar date. Consumers that need to know whether that date
actually has WNBA games should use ``--context`` or ``--field``. The context
keeps three concepts separate:

* ``current_date``: the Eastern observation date;
* ``active_slate_date``: today when the cached league calendar has games;
* ``next_slate_date``: the next known WNBA game date during a break.

That distinction lets dashboard deployment enter a truthful maintenance state
without treating old predictions as current or spending odds credits merely to
prove that no player/ALT markets have been posted.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/New_York"
ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEDULE_SOURCE = ROOT / "data/wnba/scores.json"


@dataclass(frozen=True)
class SlateContext:
    schema_version: str
    current_date: str
    target_date: str
    mode: str
    active_slate_date: str | None
    next_slate_date: str | None
    display_slate_date: str
    days_until_slate: int | None
    schedule_source: str
    schedule_generated_at_utc: str | None
    schedule_date_count: int
    upcoming_slate_dates: list[str]
    schedule_evidence_available: bool
    current_market_refresh_allowed: bool
    maintenance_deploy_allowed: bool
    reason: str
    schedule_error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _localized_now(now: datetime | date | None, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)
    if now is None:
        return datetime.now(zone)
    if isinstance(now, datetime):
        return now.replace(tzinfo=zone) if now.tzinfo is None else now.astimezone(zone)
    return datetime.combine(now, time.min, tzinfo=zone)


def _schedule_label(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _calendar_dates(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []

    event_container = payload.get("data", {}).get("events", {})
    if not isinstance(event_container, dict):
        event_container = payload.get("events", {})
    if not isinstance(event_container, dict):
        return []

    values: set[str] = set()
    for league in event_container.get("leagues") or []:
        if not isinstance(league, dict):
            continue
        for raw in league.get("calendar") or []:
            text = str(raw or "")[:10]
            try:
                date.fromisoformat(text)
            except ValueError:
                continue
            values.add(text)

    for event in event_container.get("events") or []:
        if not isinstance(event, dict):
            continue
        text = str(event.get("date") or "")[:10]
        try:
            date.fromisoformat(text)
        except ValueError:
            continue
        values.add(text)

    return sorted(values)


def load_schedule_evidence(path: str | Path = DEFAULT_SCHEDULE_SOURCE) -> tuple[list[str], str | None, str | None]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], None, f"{type(exc).__name__}:{exc}"
    generated = None
    if isinstance(payload, dict):
        generated = str(payload.get("generated_at_utc") or "").strip() or None
    dates = _calendar_dates(payload)
    return dates, generated, None if dates else "calendar_dates_missing"


def resolve_slate_context(
    manual_date: str = "",
    timezone_name: str = DEFAULT_TZ,
    schedule_source: str | Path = DEFAULT_SCHEDULE_SOURCE,
    now: datetime | date | None = None,
) -> SlateContext:
    localized = _localized_now(now, timezone_name)
    current = localized.date()
    current_text = current.isoformat()
    manual = str(manual_date or "").strip()
    source_path = Path(schedule_source)
    source_label = _schedule_label(source_path)

    if manual:
        selected = date.fromisoformat(manual)
        delta = (selected - current).days
        return SlateContext(
            schema_version="wnba-slate-context-v1",
            current_date=current_text,
            target_date=manual,
            mode="manual",
            active_slate_date=manual,
            next_slate_date=manual,
            display_slate_date=manual,
            days_until_slate=delta,
            schedule_source=source_label,
            schedule_generated_at_utc=None,
            schedule_date_count=0,
            upcoming_slate_dates=[manual],
            schedule_evidence_available=False,
            current_market_refresh_allowed=True,
            maintenance_deploy_allowed=False,
            reason="manual_date_override",
            schedule_error=None,
        )

    schedule_dates, generated, schedule_error = load_schedule_evidence(source_path)
    parsed = [date.fromisoformat(value) for value in schedule_dates]
    upcoming = [value.isoformat() for value in parsed if value >= current]

    if current in parsed:
        mode = "active"
        active = current_text
        next_slate = current_text
        display = current_text
        days_until = 0
        reason = "scheduled_games_today"
        refresh_allowed = True
        maintenance_allowed = False
    else:
        future = next((value for value in parsed if value > current), None)
        active = None
        refresh_allowed = False
        if future is not None:
            mode = "break"
            next_slate = future.isoformat()
            display = next_slate
            days_until = (future - current).days
            reason = "no_games_today_next_slate_confirmed"
            maintenance_allowed = True
        elif parsed:
            mode = "offseason"
            next_slate = None
            display = current_text
            days_until = None
            reason = "no_remaining_dates_in_cached_calendar"
            maintenance_allowed = True
        else:
            mode = "schedule_unavailable"
            next_slate = None
            display = current_text
            days_until = None
            reason = "schedule_evidence_unavailable"
            maintenance_allowed = False

    return SlateContext(
        schema_version="wnba-slate-context-v1",
        current_date=current_text,
        # Preserve the legacy execution target. A break is a state attached to
        # today, not permission to manufacture future current-slate artifacts.
        target_date=current_text,
        mode=mode,
        active_slate_date=active,
        next_slate_date=next_slate,
        display_slate_date=display,
        days_until_slate=days_until,
        schedule_source=source_label,
        schedule_generated_at_utc=generated,
        schedule_date_count=len(schedule_dates),
        upcoming_slate_dates=upcoming[:12],
        schedule_evidence_available=bool(schedule_dates),
        current_market_refresh_allowed=refresh_allowed,
        maintenance_deploy_allowed=maintenance_allowed,
        reason=reason,
        schedule_error=schedule_error,
    )


def resolve_target_date(
    manual_date: str = "",
    timezone_name: str = DEFAULT_TZ,
    now: datetime | date | None = None,
) -> str:
    """Return the legacy Eastern execution date used by existing producers."""

    if manual_date:
        return date.fromisoformat(str(manual_date).strip()).isoformat()
    return _localized_now(now, timezone_name).date().isoformat()


def resolve_year(timezone_name: str = DEFAULT_TZ, now: datetime | date | None = None) -> str:
    return str(_localized_now(now, timezone_name).year)


def _print_field(context: SlateContext, field: str) -> None:
    values = context.to_dict()
    if field not in values:
        raise SystemExit(f"Unknown slate-context field: {field}")
    value = values[field]
    if value is None:
        print("")
    elif isinstance(value, (dict, list, bool)):
        print(json.dumps(value, separators=(",", ":")))
    else:
        print(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    parser.add_argument("--tz", default=DEFAULT_TZ)
    parser.add_argument("--year", action="store_true")
    parser.add_argument("--context", action="store_true")
    parser.add_argument("--field", default="")
    parser.add_argument("--schedule-source", default=str(DEFAULT_SCHEDULE_SOURCE))
    args = parser.parse_args()

    if args.year:
        print(resolve_year(args.tz))
        return

    context = resolve_slate_context(args.date, args.tz, args.schedule_source)
    if args.context:
        print(json.dumps(context.to_dict(), sort_keys=True))
    elif args.field:
        _print_field(context, args.field)
    else:
        print(context.target_date)


if __name__ == "__main__":
    main()
