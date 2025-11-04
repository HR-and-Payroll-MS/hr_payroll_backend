from decimal import Decimal

from django.conf import settings
from django.db import transaction

from hr_payroll.attendance.models import Attendance
from hr_payroll.employees.models import Employee
from hr_payroll.payroll.models import PayrollCycle
from hr_payroll.payroll.models import PayrollRecord


def _get_standard_work_hours_per_day() -> int:
    return int(getattr(settings, "STANDARD_WORK_HOURS_PER_DAY", 8))


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
def generate_payroll_for_cycle(cycle_id: str) -> dict[str, int]:
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
    std_hours = _get_standard_work_hours_per_day()

    for emp in employees.iterator():
        # Aggregate attendance for the employee in the cycle window
        attendances = Attendance.objects.filter(
            employee=emp, date__gte=period_start, date__lte=period_end
        )
        total_work_seconds = 0
        total_ot_seconds = 0
        for a in attendances:
            total_work_seconds += int(a.paid_time.total_seconds()) if a.paid_time else 0
            total_ot_seconds += int(a.overtime_seconds or 0)

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
            Decimal(period_days * std_hours)
            if period_days * std_hours > 0
            else Decimal(1)
        )
        hourly_rate = (
            (base_salary / denom).quantize(Decimal("0.0001"))
            if base_salary
            else Decimal("0.00")
        )
        actual_pay = (hourly_rate * hours).quantize(Decimal("0.01"))

        ot_hours = Decimal(total_ot_seconds) / Decimal(3600)
        # Overtime premium: assume 1.5x hourly rate for OT
        ot_pay = (hourly_rate * Decimal("1.5") * ot_hours).quantize(Decimal("0.01"))

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
