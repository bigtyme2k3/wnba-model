"""
active_slate_date.py
--------------------
Resolves the WNBA betting slate date using Eastern Time instead of UTC.

Why:
GitHub Actions runs on UTC. At 8:50 PM ET, UTC is already tomorrow, which caused
our dashboard to flip to the next day's slate while current games were still
active.

Default behavior:
- Use America/New_York date.
- Do not flip to tomorrow until after local midnight.
- If a manual --date is supplied, return it unchanged.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/New_York"


def resolve_target_date(manual_date: str = "", timezone_name: str = DEFAULT_TZ) -> str:
    manual_date = str(manual_date or "").strip()
    if manual_date:
        return manual_date
    return datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d")


def resolve_year(timezone_name: str = DEFAULT_TZ) -> str:
    return datetime.now(ZoneInfo(timezone_name)).strftime("%Y")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--tz", default=DEFAULT_TZ)
    ap.add_argument("--year", action="store_true")
    args = ap.parse_args()
    if args.year:
        print(resolve_year(args.tz))
    else:
        print(resolve_target_date(args.date, args.tz))


if __name__ == "__main__":
    main()
