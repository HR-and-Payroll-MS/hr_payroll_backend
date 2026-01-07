from __future__ import annotations

from datetime import time
from decimal import Decimal
from decimal import InvalidOperation

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
    # Check if rate is nested in 'rates' as per frontend schema
    if not rate or rate == 1.5:
        rate = doc.get("overtimePolicy", {}).get("rates", {}).get("standardRate", 1.5)
    return Decimal(str(rate))


def weekend_overtime_rate_multiplier() -> Decimal:
    """Weekend overtime multiplier (default: 2)."""

    doc = get_policy_document()
    rate = doc.get("overtimePolicy", {}).get("weekendRate", 2)
    if not rate or rate == 2:
        rate = doc.get("overtimePolicy", {}).get("rates", {}).get("weekendRate", 2)
    return Decimal(str(rate))


def holiday_overtime_rate_multiplier() -> Decimal:
    """Holiday overtime multiplier (default: 2)."""

    doc = get_policy_document()
    rate = doc.get("overtimePolicy", {}).get("holidayRate", 2)
    if not rate or rate == 2:
        rate = doc.get("overtimePolicy", {}).get("rates", {}).get("holidayRate", 2)
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


def default_shift() -> tuple[str, time, time]:
    doc = get_policy_document()
    shift_times = doc.get("attendancePolicy", {}).get("shiftTimes", []) or []

    if shift_times and isinstance(shift_times, list):
        shift = shift_times[0]
        name = shift.get("name") or "Day Shift"
        start_raw = shift.get("start") or "09:00"
        end_raw = shift.get("end") or "17:00"
    else:
        name, start_raw, end_raw = "Day Shift", "09:00", "17:00"

    start = _parse_time(start_raw, fallback=time(9, 0))
    end = _parse_time(end_raw, fallback=time(17, 0))
    return name, start, end


def get_shift_by_name(target_name: str) -> tuple[str, time, time] | None:
    """Return shift details (name, start, end) matching target_name, or None."""
    if not target_name:
        return None
    doc = get_policy_document()
    shift_times = doc.get("attendancePolicy", {}).get("shiftTimes", []) or []

    for shift in shift_times:
        if shift.get("name") == target_name:
            start_raw = shift.get("start") or "09:00"
            end_raw = shift.get("end") or "17:00"
            return (
                shift.get("name"),
                _parse_time(start_raw, fallback=time(9, 0)),
                _parse_time(end_raw, fallback=time(17, 0)),
            )
    return None


def grace_minutes() -> int:
    doc = get_policy_document()
    grace = doc.get("attendancePolicy", {}).get("gracePeriod", {})
    minutes = grace.get("minutesAllowed", 10)
    try:
        return int(minutes)
    except (TypeError, ValueError):
        return 10


def max_lateness_occurrences() -> int:
    doc = get_policy_document()
    grace = doc.get("attendancePolicy", {}).get("gracePeriod", {})
    limit = grace.get("allowedOccurrencesPerMonth", 3)
    try:
        return int(limit)
    except (TypeError, ValueError):
        return 3


# --- Pension & Tax ---


def pension_percentage() -> Decimal:
    """Return pension deduction percentage (e.g. 5.0)."""
    doc = get_policy_document()
    deductions = doc.get("salaryStructurePolicy", {}).get("deductions", {})
    percent = deductions.get("pensionPercent", 0)
    try:
        return Decimal(str(percent))
    except (ValueError, TypeError, InvalidOperation):
        return Decimal("0")


def tax_brackets() -> list[dict]:
    """Return list of tax brackets: {min, max, rate, appliedfor}."""
    doc = get_policy_document()
    deductions = doc.get("salaryStructurePolicy", {}).get("deductions", {})
    brackets = deductions.get("taxBracket", [])
    if isinstance(brackets, list):
        return brackets
    return []


# --- Loans ---


def loan_interest_rate() -> Decimal:
    doc = get_policy_document()
    rate = doc.get("loanPolicy", {}).get("interestRate", 0)
    return Decimal(str(rate))


def loan_max_multiplier() -> int:
    doc = get_policy_document()
    return int(doc.get("loanPolicy", {}).get("maxAmountMultiplier", 3))


def loan_max_term() -> int:
    doc = get_policy_document()
    return int(doc.get("loanPolicy", {}).get("maxRepaymentMonths", 12))


def _parse_time(value: str | None, fallback: time) -> time:
    if not value:
        return fallback
    try:
        parts = value.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return time(hour=hour, minute=minute)
    except (ValueError, IndexError):
        return fallback
