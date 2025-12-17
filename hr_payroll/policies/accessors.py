from __future__ import annotations

from decimal import Decimal

from django.conf import settings

from .service import get_policy_document

_DAY_TO_WEEKDAY_INDEX = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}


def attendance_edit_window_days() -> int:
    """Max age (days) allowed to edit attendance via admin adjustment flows."""

    return int(getattr(settings, "ATTENDANCE_EDIT_WINDOW_DAYS", 31))


def standard_work_hours_per_day() -> int:
    """Standard work hours per day used by payroll calculations."""

    return int(getattr(settings, "STANDARD_WORK_HOURS_PER_DAY", 8))


def overtime_rate_multiplier() -> Decimal:
    """Overtime multiplier used by payroll (default: 1.5).

    Source of truth is the policy document (mirrors frontend `overtimePolicy`).
    """

    doc = get_policy_document()
    rate = doc.get("overtimePolicy", {}).get("overtimeRate", 1.5)
    return Decimal(str(rate))


def weekend_overtime_rate_multiplier() -> Decimal:
    """Weekend overtime multiplier (default: 2)."""

    doc = get_policy_document()
    rate = doc.get("overtimePolicy", {}).get("weekendRate", 2)
    return Decimal(str(rate))


def holiday_overtime_rate_multiplier() -> Decimal:
    """Holiday overtime multiplier (default: 2)."""

    doc = get_policy_document()
    rate = doc.get("overtimePolicy", {}).get("holidayRate", 2)
    return Decimal(str(rate))


def min_overtime_minutes() -> int:
    """Minimum overtime minutes before overtime pay applies (default: 30)."""

    doc = get_policy_document()
    minutes = doc.get("overtimePolicy", {}).get("minOvertimeMinutes", 30)
    try:
        return int(minutes)
    except (TypeError, ValueError):
        return 30


def weekly_off_weekday_indexes() -> set[int]:
    """Return the weekly off days as weekday indexes (Mon=0 ... Sun=6).

    Defaults to Saturday/Sunday to match the frontend defaults.
    """

    doc = get_policy_document()
    weekly_off = doc.get("shiftPolicy", {}).get("weeklyOff", ["Sat", "Sun"])
    if not isinstance(weekly_off, list):
        weekly_off = ["Sat", "Sun"]

    indexes: set[int] = set()
    for item in weekly_off:
        if not isinstance(item, str):
            continue
        idx = _DAY_TO_WEEKDAY_INDEX.get(item)
        if idx is not None:
            indexes.add(idx)

    return indexes or {5, 6}
