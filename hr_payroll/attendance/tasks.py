from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from hr_payroll.attendance.models import Attendance


@shared_task(name="attendance.daily_overtime")
def daily_overtime(date_iso: str | None = None) -> int:
    """Compute and cache overtime_seconds for attendances on a given date.

    Args:
        date_iso: ISO date string (YYYY-MM-DD). Defaults to yesterday in TIME_ZONE.

    Returns:
        Number of attendance records updated.
    """
    if date_iso:
        target_date = timezone.datetime.fromisoformat(date_iso).date()
    else:
        today = timezone.now().date()
        target_date = today - timedelta(days=1)

    qs = Attendance.objects.filter(date=target_date)
    updated = 0
    for a in qs.iterator():
        scheduled = timezone.timedelta(hours=int(a.work_schedule_hours))
        paid = a.paid_time or timezone.timedelta(0)
        overtime = paid - scheduled
        seconds = int(overtime.total_seconds())
        if a.overtime_seconds != seconds:
            a.overtime_seconds = seconds
            a.save(update_fields=["overtime_seconds", "updated_at"])
            updated += 1
    return updated
