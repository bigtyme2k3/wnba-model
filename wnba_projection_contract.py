"""Shared integrity contract for WNBA single-player counting-stat projections.

The limits are deliberately generous plausibility ceilings, not model clamps.
Values outside the contract are quarantined so malformed or repeatedly adjusted
inputs cannot become probability, EV, simulation, or bet-selection evidence.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


STAT_ALIASES = {
    "POINT": "PTS",
    "POINTS": "PTS",
    "PLAYER_POINTS": "PTS",
    "REBOUND": "REB",
    "REBOUNDS": "REB",
    "PLAYER_REBOUNDS": "REB",
    "ASSIST": "AST",
    "ASSISTS": "AST",
    "PLAYER_ASSISTS": "AST",
    "THREE": "3PM",
    "THREES": "3PM",
    "FG3M": "3PM",
    "PLAYER_THREES": "3PM",
    "POINTS_REBOUNDS_ASSISTS": "PRA",
    "PLAYER_POINTS_REBOUNDS_ASSISTS": "PRA",
    "POINTS_REBOUNDS": "PR",
    "PLAYER_POINTS_REBOUNDS": "PR",
    "POINTS_ASSISTS": "PA",
    "PLAYER_POINTS_ASSISTS": "PA",
    "REBOUNDS_ASSISTS": "RA",
    "PLAYER_REBOUNDS_ASSISTS": "RA",
    "STEAL": "STL",
    "STEALS": "STL",
    "BLOCK": "BLK",
    "BLOCKS": "BLK",
    "TURNOVER": "TOV",
    "TURNOVERS": "TOV",
    "DOUBLE_DOUBLE": "DD",
    "TRIPLE_DOUBLE": "TD",
}

# These ceilings sit well above observed WNBA single-game records. They catch
# unit errors and runaway compounding without trimming a realistic model tail.
PROJECTION_CEILINGS = {
    "PTS": 80.0,
    "REB": 40.0,
    "AST": 30.0,
    "3PM": 20.0,
    "PRA": 140.0,
    "PR": 120.0,
    "PA": 110.0,
    "RA": 70.0,
    "STL": 20.0,
    "BLK": 20.0,
    "TOV": 25.0,
    "DD": 1.0,
    "TD": 1.0,
}
DEFAULT_PROJECTION_CEILING = 250.0
PROJECTION_FIELDS = (
    "model_projection",
    "projection",
    "projection_mean",
    "proj",
    "pred",
    "projected_value",
)


def canonical_stat(value: Any) -> str:
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return STAT_ALIASES.get(text, text)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def projection_ceiling(stat: Any) -> float:
    return PROJECTION_CEILINGS.get(canonical_stat(stat), DEFAULT_PROJECTION_CEILING)


def validate_projection(stat: Any, value: Any) -> tuple[float | None, str | None]:
    """Return a finite plausible value, or ``(None, reason)`` when unsafe."""
    number = finite_number(value)
    if number is None:
        return None, "missing_or_non_finite"
    if number < 0:
        return None, "negative_count_projection"
    ceiling = projection_ceiling(stat)
    if number > ceiling:
        return None, f"above_{canonical_stat(stat) or 'UNKNOWN'}_ceiling_{ceiling:g}"
    return number, None


def first_plausible_projection(
    row: Mapping[str, Any],
    stat: Any,
    fields: Iterable[str],
) -> tuple[float | None, str | None, list[dict[str, Any]]]:
    """Select the first plausible populated alias and retain rejection evidence."""
    rejected: list[dict[str, Any]] = []
    for field in fields:
        value = row.get(field)
        if value in (None, ""):
            continue
        projection, reason = validate_projection(stat, value)
        if projection is not None:
            return projection, field, rejected
        rejected.append({"field": field, "value": value, "reason": reason})
    return None, None, rejected


def projection_evidence(row: Mapping[str, Any]) -> tuple[str, Any] | None:
    """Return the first populated projection-like field for audit consumers."""
    for field in PROJECTION_FIELDS:
        value = row.get(field)
        if value not in (None, ""):
            return field, value
    return None


def projection_field_violations(row: Mapping[str, Any], stat: Any) -> list[dict[str, Any]]:
    """Validate every populated alias so a healthy field cannot hide a bad one."""
    violations: list[dict[str, Any]] = []
    for field in PROJECTION_FIELDS:
        value = row.get(field)
        if value in (None, ""):
            continue
        _, reason = validate_projection(stat, value)
        if reason:
            violations.append({"field": field, "value": value, "reason": reason})
    return violations
