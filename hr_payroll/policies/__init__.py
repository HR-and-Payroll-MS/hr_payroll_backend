"""Standalone policy module.

This package centralizes org-wide policy defaults and helper accessors.
Backend apps (payroll, attendance, leaves, etc.) should import policy values
from here instead of embedding constants locally.
"""

from .accessors import attendance_edit_window_days
from .accessors import holiday_overtime_rate_multiplier
from .accessors import min_overtime_minutes
from .accessors import overtime_rate_multiplier
from .accessors import standard_work_hours_per_day
from .accessors import weekend_overtime_rate_multiplier
from .accessors import weekly_off_weekday_indexes
from .defaults import get_default_policy_document
from .service import get_policy_document

__all__ = [
    "attendance_edit_window_days",
    "get_default_policy_document",
    "get_policy_document",
    "holiday_overtime_rate_multiplier",
    "min_overtime_minutes",
    "overtime_rate_multiplier",
    "standard_work_hours_per_day",
    "weekend_overtime_rate_multiplier",
    "weekly_off_weekday_indexes",
]
