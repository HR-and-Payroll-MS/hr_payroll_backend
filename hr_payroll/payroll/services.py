from decimal import Decimal

from django.db import transaction

from hr_payroll.attendance.models import Attendance
from hr_payroll.employees.models import Employee
from hr_payroll.leaves.models import PublicHoliday
from hr_payroll.payroll.models import PayrollCycle
from hr_payroll.payroll.models import PayrollRecord
from hr_payroll.policies import holiday_overtime_rate_multiplier
from hr_payroll.policies import min_overtime_minutes
from hr_payroll.policies import overtime_rate_multiplier
from hr_payroll.policies import standard_work_hours_per_day
from hr_payroll.policies import weekend_overtime_rate_multiplier
from hr_payroll.policies import weekly_off_weekday_indexes


def prorate_amount(base_salary: Decimal, worked_days: int, period_days: int) -> Decimal:
    """Prorate calculation used across the payroll module.

    Formula: (worked_days / period_days) * base_salary

    Notes:
    - If period_days is zero, returns 0.
    - Uses Decimal arithmetic and rounds to 2 decimal places.
    """
    if period_days <= 0:
        return Decimal("0.00")
    ratio = Decimal(worked_days) / Decimal(period_days)
    return (Decimal(base_salary) * ratio).quantize(Decimal("0.01"))


@transaction.atomic
def generate_payroll_for_cycle(cycle_id: str) -> dict[str, int]:  # noqa: C901, PLR0912, PLR0915
    """Generate payroll records for the given PayrollCycle.

    This will iterate eligible employees, compute attendance aggregates for the
    cycle period, compute prorated salary and actual (hourly) pay, and create or
    update PayrollRecord rows.

    Returns a summary dict with counts: {"created": int, "updated": int}
    """
    try:
        cycle = PayrollCycle.objects.get(pk=cycle_id)
    except PayrollCycle.DoesNotExist:
        msg = "PayrollCycle not found"
        raise ValueError(msg) from None

    # Determine eligible employees
    if cycle.eligibility_criteria == PayrollCycle.Eligibility.ALL:
        employees = Employee.objects.filter(is_active=True)
    else:
        employees = cycle.eligible_employees.all()

    created = 0
    updated = 0
    period_start = cycle.period_start
    period_end = cycle.period_end
    period_days = cycle.days_in_period
    # Policy value is centralized to avoid drift across modules.
    standard_hours_per_day = standard_work_hours_per_day()
    weekly_off = weekly_off_weekday_indexes()
    min_ot_seconds = min_overtime_minutes() * 60

    # Holidays overlapping this cycle window.
    holidays = list(
        PublicHoliday.objects.filter(
            start_date__lte=period_end, end_date__gte=period_start
        )
        .only("start_date", "end_date")
        .iterator()
    )

    for emp in employees.iterator():
        # Aggregate attendance for the employee in the cycle window
        attendances = Attendance.objects.filter(
            employee=emp, date__gte=period_start, date__lte=period_end
        )
        total_work_seconds = 0
        total_ot_seconds = 0
        weekday_ot_seconds = 0
        weekend_ot_seconds = 0
        holiday_ot_seconds = 0
        for a in attendances:
            total_work_seconds += int(a.paid_time.total_seconds()) if a.paid_time else 0

            ot_seconds = int(a.overtime_seconds or 0)
            if ot_seconds <= 0:
                continue
            total_ot_seconds += ot_seconds

            # Apply minimum overtime threshold per attendance day.
            if ot_seconds < min_ot_seconds:
                continue

            # Determine OT multiplier class based on attendance date.
            day = a.date
            is_holiday = any(h.start_date <= day <= h.end_date for h in holidays)
            if is_holiday:
                holiday_ot_seconds += ot_seconds
            elif day.weekday() in weekly_off:
                weekend_ot_seconds += ot_seconds
            else:
                weekday_ot_seconds += ot_seconds

        # Derive days worked by counting unique attendance days
        days_worked = attendances.values("date").distinct().count()

        # Base salary: try to find latest Compensation base component
        # Fallback: 0 if no compensation
        comp = getattr(emp, "compensations", None)
        base_salary = Decimal("0.00")
        if comp is not None:
            first_comp = comp.order_by("-created_at").first()
            if first_comp:
                # Sum components of kind BASE
                base_salary = sum(
                    (c.amount for c in first_comp.components.filter(kind="base")),
                    Decimal("0.00"),
                )

        # Prorate salary based on days worked
        prorated_salary = prorate_amount(base_salary, days_worked, period_days)

        # Actual (hours-based) pay: compute hourly rate from base salary
        hours = Decimal(total_work_seconds) / Decimal(3600)
        denom = (
            Decimal(period_days * standard_hours_per_day)
            if period_days * standard_hours_per_day > 0
            else Decimal(1)
        )
        hourly_rate = (
            (base_salary / denom).quantize(Decimal("0.0001"))
            if base_salary
            else Decimal("0.00")
        )
        actual_pay = (hourly_rate * hours).quantize(Decimal("0.01"))

        weekday_ot_hours = Decimal(weekday_ot_seconds) / Decimal(3600)
        weekend_ot_hours = Decimal(weekend_ot_seconds) / Decimal(3600)
        holiday_ot_hours = Decimal(holiday_ot_seconds) / Decimal(3600)
        ot_pay = (
            (hourly_rate * overtime_rate_multiplier() * weekday_ot_hours)
            + (hourly_rate * weekend_overtime_rate_multiplier() * weekend_ot_hours)
            + (hourly_rate * holiday_overtime_rate_multiplier() * holiday_ot_hours)
        ).quantize(Decimal("0.01"))

        # Create or update PayrollRecord
        record, created_flag = PayrollRecord.objects.update_or_create(
            cycle=cycle,
            employee=emp,
            defaults={
                "salary": prorated_salary,
                "actual": actual_pay,
                "recurring": Decimal("0.00"),
                "one_off": Decimal("0.00"),
                "offset": Decimal("0.00"),
                "ot": ot_pay,
                "period_start": period_start,
                "period_end": period_end,
                "actual_work_seconds": int(total_work_seconds),
                "overtime_seconds": int(total_ot_seconds),
                "deficit_seconds": 0,
                "carry_over_overtime_seconds": 0,
            },
        )
        # Recalc total
        record.recalc_total()
        if created_flag:
            created += 1
        else:
            updated += 1

    return {"created": created, "updated": updated}
